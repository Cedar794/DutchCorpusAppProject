import unittest

from fastapi.testclient import TestClient

from lexicon_search.api import create_app


class FakeService:
    async def lookup(self, query, limit):
        return {"query": query, "mode": "lookup", "best_match": None, "did_you_mean": []}

    async def suggest(self, query, limit):
        return {"query": query, "mode": "suggest", "suggestions": []}

    async def semantic_search(self, query, limit, include_related):
        return {"query": query, "language": "unknown", "results": [], "related_results": []}


class SearchApiTests(unittest.TestCase):
    def test_health(self):
        client = TestClient(create_app(FakeService()))
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_lookup_endpoint(self):
        client = TestClient(create_app(FakeService()))
        response = client.get("/lookup", params={"q": "gelopen"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "lookup")

    def test_semantic_limit_is_capped(self):
        client = TestClient(create_app(FakeService()))
        response = client.post("/semantic-search", json={"query": "walk", "limit": 500})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
