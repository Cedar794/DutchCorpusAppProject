import os
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import asyncpg
from fastapi.testclient import TestClient

from lexicon_search.api import create_app
from lexicon_search.entry_details import EntryReader
from lexicon_search.rate_limit import IPRateLimiter
from tests.test_search_api import FakeService


class EntryApiTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.service.entry = AsyncMock(return_value={"lemma_id": 138, "lemma": "huis"})
        self.service.sense_examples = AsyncMock(return_value={"sense_id": 1, "examples": {"items": []}})
        self.client = TestClient(create_app(self.service))

    def test_entry_and_examples_forward_pagination(self):
        response = self.client.get('/entries/138?sense_offset=2&sense_limit=3&form_limit=4')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.service.entry.await_args.args, (138,))
        self.assertEqual(self.service.entry.await_args.kwargs['sense_offset'], 2)
        self.assertEqual(self.service.entry.await_args.kwargs['sense_limit'], 3)
        self.assertEqual(self.service.entry.await_args.kwargs['form_limit'], 4)
        self.assertEqual(self.client.get('/senses/1/examples?offset=2&limit=3').status_code, 200)
        self.service.sense_examples.assert_awaited_once_with(1, offset=2, limit=3)

    def test_invalid_ids_and_unbounded_pages_are_rejected(self):
        paths = ['/entries/0', '/entries/-1', '/entries/9223372036854775808',
                 '/entries/1?sense_limit=51', '/entries/1?form_limit=101',
                 '/entries/1?example_limit=21', '/entries/1?expression_limit=51',
                 '/entries/1?sense_offset=-1', '/senses/1/examples?limit=21']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 422)
        self.service.entry.assert_not_awaited()
        self.service.sense_examples.assert_not_awaited()

    def test_not_found_and_database_errors_do_not_expose_internals(self):
        for name, path in [('entry', '/entries/1'), ('sense_examples', '/senses/1/examples')]:
            method = getattr(self.service, name)
            method.return_value = None
            self.assertEqual(self.client.get(path).status_code, 404)
            method.side_effect = asyncpg.PostgresError('private SQL and password')
            response = self.client.get(path)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private', response.text)

    def test_details_share_query_quota_even_for_invalid_or_missing_ids(self):
        self.service.entry.return_value = None
        client = TestClient(create_app(self.service, limiter=IPRateLimiter(3, 1, 10)))
        self.assertEqual(client.get('/lookup?q=huis').status_code, 200)
        self.assertEqual(client.get('/entries/1').status_code, 404)
        self.assertEqual(client.get('/entries/no-id').status_code, 422)
        response = client.get('/senses/1/examples', headers={'X-Forwarded-For': '203.0.113.7'})
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers['Retry-After']), 0)
        self.service.sense_examples.assert_not_awaited()


@unittest.skipUnless(os.environ.get('SEARCH_TEST_DATABASE_URL'), 'Set SEARCH_TEST_DATABASE_URL for PostgreSQL integration')
class EntryDatabaseTests(unittest.IsolatedAsyncioTestCase):
    """Temporary fixture rows are always rolled back; no sequence values change."""
    base = 8000000000

    async def asyncSetUp(self):
        self.connection = await asyncpg.connect(os.environ['SEARCH_TEST_DATABASE_URL'])
        self.transaction = self.connection.transaction(isolation='repeatable_read')
        await self.transaction.start()
        self.addAsyncCleanup(self.cleanup_database)
        connection = self.connection
        base = self.base
        await connection.execute("""
            insert into public.sources(id,source_key,name,source_type,license,attribution)
              values($1,'entry_detail_test','Entry test','llm_derived','test license','Test attribution');
        """, base)
        await connection.execute("""
            insert into public.lemmas(id,lemma,lemma_norm,level,source_id,review_status)
            values($1,'testwoord','__entry_detail_test__',1,$3,'accepted'),
                  ($2,'hidden','__entry_detail_hidden__',1,$3,'needs_review')
        """, base+1, base+2, base)
        await connection.execute("""
            insert into public.lemma_pos_entries(id,lemma_id,pos,is_primary)
            values($1,$2,'NOUN',true)
        """, base+3, base+1)
        for index, status, merged in [(10,'needs_review',None), (11,'accepted',None),
                                       (12,'rejected',None), (13,'accepted',base+10)]:
            await connection.execute("""
                insert into public.senses(id,lemma_id,lemma_pos_entry_id,source_id,
                  definition_nl,review_status,merged_into_sense_id,app_sense_order)
                values($1,$2,$3,$4,'Een testbetekenis#aigc',$5,$6,$7)
            """, base+index, base+1, base+3, base, status, merged, index)
        await connection.execute("""
            insert into public.senses(id,lemma_id,source_id,definition_nl,review_status)
            values($1,$2,$3,'Hidden sense','accepted')
        """, base+14, base+2, base)
        for index, lang, gloss, status in [(20,'zh','测试词义#aigc','accepted'),
                                           (21,'zh','旧译义','needs_review'),
                                           (22,'en','test meaning','needs_review'),
                                           (23,'en','rejected meaning','rejected')]:
            # Distinct null sources permit historical alternatives for one language.
            await connection.execute("""
                insert into public.sense_translations(id,sense_id,lang,gloss,review_status)
                values($1,$2,$3,$4,$5)
            """, base+index, base+10, lang, gloss, status)
        for index in range(30,35):
            await connection.execute("""
                insert into public.examples(id,sense_id,ex_nl,source_id,is_active)
                values($1,$2,'Dit is een test.#aigc',$3,$4)
            """, base+index, base+10, base, index!=34)
            await connection.execute("""
                insert into public.example_translations(id,example_id,lang,translation,source_id)
                values($1,$2,'zh','这是测试。#aigc',$3)
            """, base+index+100, base+index, base)
        for index in range(40,43):
            await connection.execute("""
                insert into public.forms(id,lemma_id,lemma_pos_entry_id,form,form_norm,source_id,is_active,morph_features)
                values($1,$2,$3,$4,$4,$5,$6,'{"number":"plural"}')
            """, base+index, base+1, base+3, f'testform{index}', base, index!=42)
        for index in range(50,52):
            await connection.execute("""
                insert into public.lemma_examples(id,lemma_id,ex_nl,source_id,is_active)
                values($1,$2,$3,$4,$5)
            """, base+index, base+1, f'Corpus example {index}', base, index==50)
        for index, kind, status, sid in [(60,'lexical_expression','needs_review',base+10),
                                          (61,'usage_construction','accepted',base+10),
                                          (62,'definition_note','rejected',base+10),
                                          (63,'usage_example','accepted',base+12)]:
            await connection.execute("""
                insert into public.lexical_expressions(id,lemma_id,lemma_pos_entry_id,sense_id,entry_kind,
                  expression_type,expression_nl,expression_norm,definition_nl,usage_note,gloss_en,explanation_en,
                  gloss_zh,explanation_zh,example_nl,example_zh,source_id,external_id,confidence,review_status)
                values($1,$2,$3,$4,$5,'test','test uitdrukking#aigc','test uitdrukking','def','note','gloss','explanation',
                  '译义','说明','Voorbeeld.','例句。',$6,$7,0.8,$8)
            """, base+index, base+1, base+3, sid, kind, base, f'entry-test-{index}', status)

        class SingleConnectionDatabase:
            @asynccontextmanager
            async def acquire(self):
                yield connection

        self.reader = EntryReader(SingleConnectionDatabase())

    async def cleanup_database(self):
        try:
            await self.transaction.rollback()
        finally:
            await self.connection.close()

    async def test_visibility_translations_provenance_and_example_boundaries(self):
        entry = await self.reader.load_entry(self.base+1)
        self.assertEqual(entry['senses']['total'], 2)
        self.assertEqual(entry['forms']['total'], 2)
        self.assertEqual(entry['corpus_examples']['total'], 1)
        self.assertFalse(entry['corpus_examples']['sense_disambiguated'])
        self.assertEqual(entry['expressions']['total'], 2)
        self.assertEqual({e['entry_kind'] for e in entry['expressions']['items']},
                         {'lexical_expression','usage_construction'})
        sense = entry['senses']['items'][0]
        self.assertEqual(sense['definition_nl'], 'Een testbetekenis')
        self.assertEqual(sense['review_status'], 'needs_review')
        self.assertEqual(sense['translation_zh'], '测试词义')
        self.assertEqual(sense['translation_en'], 'test meaning')
        self.assertEqual(len(sense['translations']), 3)
        self.assertEqual(sense['examples']['total'], 4)
        self.assertEqual(len(sense['examples']['items']), 3)
        self.assertTrue(sense['examples']['has_more'])
        self.assertEqual(sense['examples']['items'][0]['translations'][0]['translation'], '这是测试。')
        self.assertEqual(entry['forms']['items'][0]['morph_features'], {'number':'plural'})
        self.assertEqual(entry['sources'][0]['attribution'], 'Test attribution')
        self.assertNotIn('raw_payload', str(entry))

    async def test_all_pages_have_consistent_totals_and_no_duplicates(self):
        first = await self.reader.load_entry(self.base+1, sense_limit=1, form_limit=1,
                                              expression_limit=1, example_limit=1)
        second = await self.reader.load_entry(self.base+1, sense_limit=1, sense_offset=1,
                                               form_limit=1, form_offset=1, expression_limit=1,
                                               expression_offset=1)
        for group, key in [('senses','sense_id'), ('forms','form_id'), ('expressions','expression_id')]:
            self.assertEqual(first[group]['total'], 2)
            self.assertEqual(first[group]['next_offset'], 1)
            self.assertFalse(second[group]['has_more'])
            self.assertNotEqual(first[group]['items'][0][key], second[group]['items'][0][key])
        empty = await self.reader.load_entry(self.base+1, sense_offset=99)
        self.assertEqual(empty['senses']['total'], 2)
        self.assertEqual(empty['senses']['items'], [])
        self.assertFalse(empty['senses']['has_more'])

    async def test_example_pages_and_rejected_merged_or_held_records(self):
        examples = await self.reader.load_sense_examples(self.base+10, offset=3, limit=2)
        self.assertEqual(examples['examples']['total'], 4)
        self.assertEqual(len(examples['examples']['items']), 1)
        self.assertFalse(examples['examples']['has_more'])
        self.assertEqual(examples['examples']['items'][0]['example_id'], self.base+33)
        self.assertIsNone(await self.reader.load_entry(self.base+2))
        self.assertIsNone(await self.reader.load_entry(self.base+99))
        for index in (12,13,14,99):
            self.assertIsNone(await self.reader.load_sense_examples(self.base+index))

    async def test_deployment_reader_permissions_without_committing_role_changes(self):
        sql = (Path(__file__).resolve().parents[1] / 'deploy/search-db-permissions.sql').read_text()
        await self.connection.execute(sql)
        await self.connection.execute("""do $$ begin
            execute format('grant search_service_user to %I', current_user);
        end $$""")
        await self.connection.execute('set local role search_service_user')
        entry = await self.reader.load_entry(self.base+1)
        self.assertEqual(entry['senses']['total'], 2)
        self.assertEqual(entry['sources'][0]['source_id'], self.base)
        self.assertIsNotNone(await self.reader.load_sense_examples(self.base+10))
        for table in ('lemmas', 'senses', 'sense_embeddings', 'examples'):
            self.assertFalse(await self.connection.fetchval(
                "select has_table_privilege(current_user, $1, 'UPDATE')", 'public.'+table))
        self.assertFalse(await self.connection.fetchval(
            "select has_table_privilege(current_user,'public.extreme_record_archives','SELECT')"))
