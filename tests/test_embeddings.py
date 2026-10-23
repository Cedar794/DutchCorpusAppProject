import asyncio
import unittest

import httpx

from lexicon_search.embeddings import BailianEmbeddingClient, DemoEmbeddingClient


class EmbeddingClientTests(unittest.TestCase):
    def test_demo_embedding_client_is_deterministic(self):
        async def run_test():
            client = DemoEmbeddingClient(dimension=1024)
            first = await client.embed_text("house huis")
            second = await client.embed_text("house huis")
            other = await client.embed_text("read lezen")

            self.assertEqual(first, second)
            self.assertEqual(len(first), 1024)
            self.assertNotEqual(first, other)

        asyncio.run(run_test())

    def test_embed_texts_posts_openai_compatible_request(self):
        async def run_test():
            requests = []

            def handler(request: httpx.Request) -> httpx.Response:
                requests.append(request)
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"index": 0, "embedding": [0.1] * 1024},
                            {"index": 1, "embedding": [0.2] * 1024},
                        ]
                    },
                )

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as http_client:
                client = BailianEmbeddingClient(
                    api_key="sk-test",
                    base_url="https://example.test",
                    model="text-embedding-v4",
                    dimension=1024,
                    http_client=http_client,
                )
                vectors = await client.embed_texts(["lopen", "lezen"])

            self.assertEqual(len(vectors), 2)
            self.assertEqual(len(vectors[0]), 1024)
            self.assertEqual(requests[0].url.path, "/embeddings")
            self.assertIn("Bearer sk-test", requests[0].headers["Authorization"])

        asyncio.run(run_test())

    def test_wrong_vector_dimension_raises(self):
        async def run_test():
            def handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as http_client:
                client = BailianEmbeddingClient(
                    api_key="sk-test",
                    base_url="https://example.test",
                    model="text-embedding-v4",
                    dimension=1024,
                    http_client=http_client,
                )
                with self.assertRaisesRegex(ValueError, "1024"):
                    await client.embed_texts(["lopen"])

        asyncio.run(run_test())

class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_429_then_success_and_no_retry_401(self):
        from unittest.mock import AsyncMock
        for first_status, expected_calls in [(429, 2), (401, 1)]:
            calls = []
            def handler(request):
                calls.append(request)
                return (httpx.Response(first_status, headers={'Retry-After': '2'}) if len(calls) == 1 else
                        httpx.Response(200, json={'data': [{'index': 0, 'embedding': [0.1]*1024}]}))
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='https://example.test') as http:
                client = BailianEmbeddingClient(api_key='test', base_url='https://example.test',
                    model='text-embedding-v4', dimension=1024, http_client=http, sleep=AsyncMock())
                if first_status == 401:
                    with self.assertRaises(httpx.HTTPStatusError): await client.embed_text('test')
                else:
                    self.assertEqual(len(await client.embed_text('test')), 1024)
                    self.assertGreaterEqual(client.sleep.call_args.args[0], 2)
                self.assertEqual(len(calls), expected_calls)

    async def test_missing_duplicate_and_nonfinite_vectors_rejected(self):
        for data in [[], [{'index': 1, 'embedding': [0.1]*1024}],
                     [{'index': 0, 'embedding': ['nan']*1024}]]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'data': data})), base_url='https://example.test') as http:
                client = BailianEmbeddingClient(api_key='test', base_url='https://example.test', model='test', dimension=1024, http_client=http)
                with self.assertRaises(ValueError): await client.embed_text('test')


if __name__ == "__main__":
    unittest.main()
