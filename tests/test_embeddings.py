import asyncio
import unittest

import httpx

from lexicon_search.embeddings import BailianEmbeddingClient


class EmbeddingClientTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
