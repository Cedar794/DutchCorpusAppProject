import asyncio
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from lexicon_search.api import create_app
from lexicon_search.rate_limit import IPRateLimiter
from tests.test_search_api import FakeService


class RateLimitTests(unittest.TestCase):
    def test_shared_quota_across_lookup_and_suggest_and_header_spoofing(self):
        client = TestClient(create_app(FakeService(), limiter=IPRateLimiter(2, 1, 10)))
        self.assertEqual(client.get('/lookup?q=huis').status_code, 200)
        self.assertEqual(client.get('/suggest?q=hu').status_code, 200)
        r = client.get('/lookup?q=huis', headers={'X-Forwarded-For': '203.0.113.77'})
        self.assertEqual(r.status_code, 429)
        self.assertGreater(int(r.headers['Retry-After']), 0)
        self.assertEqual(client.get('/health').status_code, 200)

    def test_semantic_quota_is_additional_and_does_not_disable_lookup(self):
        client = TestClient(create_app(FakeService(), limiter=IPRateLimiter(60, 1, 10)))
        self.assertEqual(client.post('/semantic-search', json={'query': 'walk'}).status_code, 200)
        self.assertEqual(client.post('/semantic-search', json={'query': 'home'}).status_code, 429)
        self.assertEqual(client.get('/lookup?q=huis').status_code, 200)

    def test_window_expiry_and_client_isolation(self):
        now = [0.0]
        limiter = IPRateLimiter(2, 1, 10, clock=lambda: now[0])
        self.assertEqual(limiter.check('192.0.2.1'), 0)
        self.assertEqual(limiter.check('::ffff:192.0.2.1'), 0)
        self.assertEqual(limiter.check('192.0.2.1'), 60)
        self.assertEqual(limiter.check('192.0.2.2'), 0)
        now[0] = 60
        self.assertEqual(limiter.check('192.0.2.1'), 0)

    def test_burst_and_capacity_fail_closed(self):
        now = [0.0]
        limiter = IPRateLimiter(60, 10, 2, max_clients=1, clock=lambda: now[0])
        limiter.check('192.0.2.1'); limiter.check('192.0.2.1')
        self.assertEqual(limiter.check('192.0.2.1'), 10)
        self.assertEqual(limiter.check('192.0.2.2'), 60)
        self.assertEqual(limiter.check('192.0.2.1'), 10)
        now[0] = 60
        self.assertEqual(limiter.check('192.0.2.2'), 0)

    def test_only_trusted_proxy_can_select_client_ip(self):
        async def run():
            app = ProxyHeadersMiddleware(create_app(FakeService(), limiter=IPRateLimiter(1, 1, 10)),
                                         trusted_hosts=['127.0.0.1'])
            for peer, expected in [('198.51.100.2', [200, 429]), ('127.0.0.1', [200, 200])]:
                transport = httpx.ASGITransport(app=app, client=(peer, 1234))
                async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
                    statuses = []
                    for ip in ['203.0.113.5', '203.0.113.6']:
                        r = await client.get('/lookup?q=huis', headers={'X-Forwarded-For': ip})
                        statuses.append(r.status_code)
                    self.assertEqual(statuses, expected)
        asyncio.run(run())

    def test_input_and_chunked_body_bounds(self):
        client = TestClient(create_app(FakeService()))
        self.assertEqual(client.get('/lookup', params={'q': ' '}).status_code, 422)
        self.assertEqual(client.get('/lookup', params={'q': 'x' * 129}).status_code, 422)
        self.assertEqual(client.post('/semantic-search', content=b'x' * 8193).status_code, 413)
        async def run():
            transport = httpx.ASGITransport(app=create_app(FakeService()))
            async def chunks():
                yield b'x' * 4096
                yield b'x' * 4097
            async with httpx.AsyncClient(transport=transport, base_url='http://test') as c:
                self.assertEqual((await c.post('/semantic-search', content=chunks())).status_code, 413)
        asyncio.run(run())


class LifespanTests(unittest.TestCase):
    def test_initialize_query_and_close_on_same_loop(self):
        events = []
        class LoopBoundService(FakeService):
            async def lookup(self, q, limit):
                events.append(('query', asyncio.get_running_loop()))
                return await super().lookup(q, limit)
        @asynccontextmanager
        async def resource():
            events.append(('start', asyncio.get_running_loop()))
            try:
                yield LoopBoundService()
            finally:
                events.append(('close', asyncio.get_running_loop()))
        app = create_app(service_context=resource)
        with TestClient(app) as c:
            self.assertEqual(c.get('/lookup?q=huis').status_code, 200)
        self.assertEqual([e[0] for e in events], ['start', 'query', 'close'])
        self.assertTrue(all(e[1] is events[0][1] for e in events))
        self.assertIsNone(app.state.service)

    def test_uninitialized_or_failed_database_is_not_healthy(self):
        self.assertEqual(TestClient(create_app()).get('/health').status_code, 503)
        service = FakeService()
        service.ready = AsyncMock(side_effect=RuntimeError('private database error'))
        r = TestClient(create_app(service)).get('/health')
        self.assertEqual(r.status_code, 503)
        self.assertNotIn('private', r.text)

    def test_lookup_only_mode_and_provider_errors_are_controlled(self):
        service = FakeService()
        service.semantic_engine = None
        c = TestClient(create_app(service))
        self.assertEqual(c.get('/lookup?q=huis').status_code, 200)
        self.assertEqual(c.post('/semantic-search', json={'query': 'house'}).status_code, 503)
        service.semantic_engine = True
        service.semantic_search = AsyncMock(side_effect=httpx.ConnectError('sensitive'))
        self.assertEqual(c.post('/semantic-search', json={'query': 'house'}).status_code, 503)

    def test_initialization_failure_closes_pool(self):
        from scripts.run_search_service import service_context
        from lexicon_search.config import load_config
        async def run():
            with patch('scripts.run_search_service.Database') as db, patch('scripts.run_search_service.SearchRepository') as repo:
                db.return_value.connect = AsyncMock()
                db.return_value.close = AsyncMock()
                repo.return_value.load_dictionary_rows = AsyncMock(return_value=([], []))
                with self.assertRaisesRegex(RuntimeError, 'empty'):
                    async with service_context(load_config({'DATABASE_URL': 'postgresql://example'})):
                        pass
                db.return_value.close.assert_awaited_once()
        asyncio.run(run())

class FailureBoundaryTests(unittest.TestCase):
    def test_database_outage_returns_503_without_internal_details(self):
        import asyncpg
        service = FakeService()
        for endpoint in ('lookup', 'suggest'):
            setattr(service, endpoint, AsyncMock(side_effect=asyncpg.PostgresError('private SQL')))
        with TestClient(create_app(service)) as client:
            for endpoint in ('lookup', 'suggest'):
                response = client.get('/' + endpoint, params={'q': 'huis'})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('private SQL', response.text)

    def test_configured_semantic_result_cap_is_enforced(self):
        with TestClient(create_app(FakeService(), max_semantic_limit=3)) as client:
            self.assertEqual(client.post('/semantic-search', json={'query': 'house', 'limit': 4}).status_code, 422)
            self.assertEqual(client.post('/semantic-search', json={'query': 'house', 'limit': 3}).status_code, 200)
