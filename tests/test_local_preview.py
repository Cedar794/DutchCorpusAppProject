import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from scripts.run_local_preview import TEST_LEDGER, create_preview_app, preview_config


class PreviewService:
    async def lookup(self, q, limit):
        return {'query': q, 'mode': 'lookup', 'best_match': None, 'did_you_mean': []}


class LocalPreviewTests(unittest.TestCase):
    def setUp(self):
        with patch.dict('os.environ', {}, clear=True):
            self.config = preview_config()

    def test_static_and_real_api_routes_coexist_without_exposing_project_files(self):
        with TestClient(create_preview_app(self.config, service=PreviewService())) as client:
            page = client.get('/')
            self.assertEqual(page.status_code, 200)
            self.assertIn('woordhuis', page.text.lower())
            self.assertEqual(page.headers['Cache-Control'], 'no-cache')
            self.assertEqual(client.get('/js/test-console.js').status_code, 200)
            self.assertEqual(client.get('/lookup?q=unrecorded-word').json()['query'], 'unrecorded-word')
            self.assertEqual(client.get('/lookup?q= ').status_code, 422)
            for path in ('/local/secrets/embedding-pilot.env', '/README.md', '/docs/DATA.md',
                         '/api-contract/openapi.json', '/%2e%2e/%2e%2e/local/secrets/embedding-pilot.env'):
                self.assertEqual(client.get(path).status_code, 404, path)

    def test_static_requests_do_not_spend_query_quota_and_forwarding_headers_cannot_bypass_it(self):
        with TestClient(create_preview_app(self.config, service=PreviewService())) as client:
            for _ in range(15):
                self.assertEqual(client.get('/css/console.css').status_code, 200)
            for i in range(10):
                self.assertEqual(client.get('/lookup?q=huis',
                    headers={'X-Forwarded-For': f'192.0.2.{i}'}).status_code, 200)
            response = client.get('/lookup?q=huis', headers={'X-Forwarded-For': '192.0.2.111'})
            self.assertEqual(response.status_code, 429)
            self.assertGreater(int(response.headers['Retry-After']), 0)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_semantic_is_opt_in_and_reuses_existing_budget(self):
        self.assertFalse(self.config.semantic_enabled)
        self.assertEqual(self.config.api_budget_total_cny, '0')
        with patch.dict('os.environ', {}, clear=True), patch('scripts.run_local_preview.dotenv_values',
                return_value={'BAILIAN_API_KEY': 'test', 'BAILIAN_REWRITE_API_KEY': 'test'}), \
                patch('pathlib.Path.is_file', return_value=True):
            enabled = preview_config(semantic=True)
        self.assertTrue(enabled.semantic_enabled)
        self.assertEqual(enabled.api_budget_ledger, str(TEST_LEDGER))
        self.assertEqual(enabled.api_budget_total_cny, '1')
        with patch('pathlib.Path.is_file', return_value=False):
            with self.assertRaisesRegex(ValueError, 'Existing approved'):
                preview_config(semantic=True)


if __name__ == '__main__':
    unittest.main()
