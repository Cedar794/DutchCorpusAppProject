import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from lexicon_search.config import load_config
from lexicon_search.models import FormSummary, LemmaSummary
from lexicon_search.query_rewrite import BailianQueryRewriter, constraints_preserved
from tests.test_semantic_search import FakeRepository


def completion(query, **updates):
    body = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'query':query},ensure_ascii=False)}}],
            'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}
    body.update(updates)
    return body


class RewriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_rewrite_uses_one_non_thinking_schema_request(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200,json=completion('不依赖电力的形容词'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='https://example.test/v1/') as client:
            result = await BailianQueryRewriter(api_key='test-flash-key',http_client=client).rewrite('请找一个不依赖电力的形容词')
        self.assertEqual(result.status,'rewritten')
        self.assertEqual(result.query,'不依赖电力的形容词')
        self.assertEqual(len(calls),1)
        body = json.loads(calls[0].content)
        self.assertEqual(body['model'],'qwen3.7-flash')
        self.assertFalse(body['enable_thinking'])
        self.assertFalse(body['stream'])
        self.assertEqual(body['max_completion_tokens'],256)
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertIn('subject',body['messages'][0]['content'])
        self.assertEqual(body['messages'][1]['content'],'请找一个不依赖电力的形容词')

    async def test_malformed_truncated_or_extra_fields_fall_back(self):
        invalid = [completion('x',choices=[]), completion('x',choices=[{'finish_reason':'length','message':{'content':'{}'}}]),
                   completion('x',choices=[{'finish_reason':'stop','message':{'content':'{"query":"x","sql":"drop table"}'}}]),
                   completion(''),completion('x'*513),completion('a\x00b'),
                   completion('x',choices=[{'finish_reason':'stop','message':{'content':'not JSON'}}])]
        for body in invalid:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=body)),base_url='https://example.test/v1/') as client:
                result = await BailianQueryRewriter(api_key='test',http_client=client).rewrite('original query')
                self.assertEqual(result.query,'original query')
                self.assertEqual(result.status,'invalid_or_unavailable')

    async def test_lost_negation_pos_numbers_or_quotes_fall_back(self):
        cases = [('not a verb','a verb'),('不是动词','动词'),('zonder water','met water'),
                 ("doesn’t use electricity","uses electricity"),('costs 20 euros','costs 10 euros'),
                 ('a noun about "Alice"','a noun about Bob')]
        for original, rewritten in cases:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=completion(rewritten))),base_url='https://example.test/v1/') as client:
                result = await BailianQueryRewriter(api_key='test',http_client=client).rewrite(original)
                self.assertEqual(result.query,original)
                self.assertEqual(result.status,'constraint_fallback')
        self.assertTrue(constraints_preserved('not a verb about "Alice", 20 euros','20 euros about "Alice", not a verb'))
        self.assertFalse(constraints_preserved('通过网址访问的一组网页','via URL toegankelijke webpaginas'))

    async def test_timeout_is_bounded_and_does_not_retry(self):
        calls = []
        async def handler(request):
            calls.append(request)
            await asyncio.sleep(.2)
            return httpx.Response(200,json=completion('rewritten'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='https://example.test/v1/') as client:
            rewriter = BailianQueryRewriter(api_key='test',http_client=client,timeout_seconds=.01)
            result = await rewriter.rewrite('original')
            self.assertEqual(result.status,'timeout')
            self.assertEqual((await rewriter.rewrite('original')).status,'circuit_open')
            self.assertEqual(result.query,'original')
            self.assertEqual(len(calls),1)

    async def test_missing_key_disabled_and_permission_quota_failures(self):
        for status in (401,403,429,500):
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status,json={'error':'private provider detail'})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='https://example.test/v1/') as client:
                rewriter = BailianQueryRewriter(api_key='',http_client=client)
                self.assertEqual((await rewriter.rewrite('original')).status,'unconfigured')
                rewriter.api_key = 'test'
                rewriter.enabled = False
                self.assertEqual((await rewriter.rewrite('original')).status,'disabled')
                rewriter.enabled = True
                self.assertEqual((await rewriter.rewrite('original')).status,'provider_error')
                self.assertEqual((await rewriter.rewrite('original')).status,'circuit_open')
                self.assertEqual(len(calls),1)

    async def test_busy_rewriter_falls_back_without_queueing(self):
        release = asyncio.Event()
        started = asyncio.Event()
        count = 0
        async def handler(request):
            nonlocal count
            count += 1
            if count == 2:
                started.set()
            await release.wait()
            return httpx.Response(200,json=completion('original'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='https://example.test/v1/') as client:
            rewriter = BailianQueryRewriter(api_key='test',http_client=client)
            tasks = [asyncio.create_task(rewriter.rewrite('original')) for _ in range(2)]
            await asyncio.wait_for(started.wait(),1)
            self.assertEqual((await rewriter.rewrite('original')).status,'busy')
            release.set()
            self.assertEqual([r.status for r in await asyncio.gather(*tasks)],['unchanged','unchanged'])

    async def test_runtime_lookup_skips_flash_and_semantic_embeds_rewrite(self):
        from scripts.run_search_service import service_context
        from lexicon_search.api import create_app
        calls = []
        def handler(request):
            body = json.loads(request.content)
            calls.append((request.url.path,body,request.headers['Authorization']))
            if body['model'] == 'qwen3.7-flash':
                return httpx.Response(200,json=completion('不依赖电力的形容词'))
            return httpx.Response(200,json={'data':[{'index':0,'embedding':[.1]*1024}],
                'usage':{'prompt_tokens':20,'total_tokens':20}})
        lemma = LemmaSummary(1,'huis','huis',1,100)
        class Repository(FakeRepository):
            async def load_dictionary_rows(self):
                return [lemma],[FormSummary(1,'huizen','huizen',lemma,False,10)]
            async def embedding_count(self,*args): return 46073
        original_client = httpx.AsyncClient
        def http_factory(**kwargs):
            return original_client(transport=httpx.MockTransport(handler),**kwargs)
        with tempfile.TemporaryDirectory() as directory:
            config = load_config({'DATABASE_URL':'postgresql://example','SEARCH_SEMANTIC_ENABLED':'true',
                'BAILIAN_API_KEY':'test-embedding-key','BAILIAN_REWRITE_API_KEY':'test-flash-key',
                'SEARCH_LOG_QUERIES':'false','SEARCH_API_BUDGET_TOTAL_CNY':'0.1',
                'SEARCH_API_BUDGET_DAILY_CNY':'0.1','SEARCH_API_BUDGET_LEDGER':str(Path(directory)/'ledger.sqlite3')})
            with patch('scripts.run_search_service.Database') as database, \
                 patch('scripts.run_search_service.SearchRepository',return_value=Repository()), \
                 patch('scripts.run_search_service.httpx.AsyncClient',side_effect=http_factory):
                database.return_value.connect = AsyncMock()
                database.return_value.close = AsyncMock()
                async with service_context(config) as service:
                    async with original_client(transport=httpx.ASGITransport(app=create_app(service)),base_url='http://test') as client:
                        self.assertEqual((await client.get('/lookup?q=huizen')).json()['best_match']['lemma'],'huis')
                        self.assertEqual(calls,[])
                        response = await client.post('/semantic-search',json={
                            'query':'请找一个不依赖电力的形容词','include_related':False})
                        self.assertEqual(response.status_code,200)
                        self.assertEqual(response.json()['query'],'请找一个不依赖电力的形容词')
                        self.assertEqual(response.json()['query_rewrite']['status'],'rewritten')
                        self.assertEqual(response.json()['results'][0]['entry_url'],'/entries/1')
                database.return_value.close.assert_awaited_once()
        self.assertEqual([body['model'] for _,body,_ in calls],['qwen3.7-flash','text-embedding-v4'])
        self.assertEqual(calls[1][1]['input'],['不依赖电力的形容词'])
        self.assertEqual(calls[0][2],'Bearer test-flash-key')
        self.assertEqual(calls[1][2],'Bearer test-embedding-key')

    async def test_engine_fallback_embeds_original_query(self):
        from lexicon_search.semantic import SemanticSearchEngine
        from lexicon_search.query_rewrite import RewriteResult
        embedder = AsyncMock()
        embedder.embed_text.return_value = [.1]*1024
        rewriter = AsyncMock()
        rewriter.model = 'qwen3.7-flash'
        rewriter.rewrite.return_value = RewriteResult('original','timeout')
        result = await SemanticSearchEngine(embedder,FakeRepository(),'search-test',rewriter=rewriter).search('original',10)
        embedder.embed_text.assert_awaited_once_with('original')
        self.assertEqual(result['query_rewrite']['status'],'timeout')
