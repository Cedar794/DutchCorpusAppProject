import asyncio
import unittest

from lexicon_search.dictionary import DictionaryIndex
from lexicon_search.models import FormSummary, LemmaSummary
from lexicon_search.service import SearchService


class FakeSemanticEngine:
    async def search(self, query, limit):
        return {
            "results": [
                {
                    "lemma_id": 1,
                    "lemma": "lopen",
                    "level": 1,
                    "score": 0.9,
                    "matched_sense": {"sense_id": 10},
                    "matched_reason": {"semantic_score": 0.9},
                }
            ],
            "candidate_count": 50,
        }


class FakeRepository:
    async def fuzzy_lookup(self, query_norm, limit):
        return []

    async def fuzzy_suggest(self, query_norm, limit):
        return []

    async def load_related_results(self, lemma_ids, sense_ids):
        return []

    async def write_query_log(self, record, request_metadata):
        self.last_log = record


class SearchServiceTests(unittest.TestCase):
    def test_lookup_returns_best_match(self):
        async def run_test():
            lemma = LemmaSummary(1, "lopen", "lopen", 1, 1200)
            dictionary = DictionaryIndex.from_rows(
                [lemma],
                [FormSummary(10, "gelopen", "gelopen", lemma, False, 300)],
            )
            service = SearchService(
                dictionary,
                FakeSemanticEngine(),
                FakeRepository(),
                log_queries=True,
                embedding_model="text-embedding-v4",
                index_version="search-test",
            )
            result = await service.lookup("gelopen", limit=5)
            self.assertEqual(result["best_match"]["lemma"], "lopen")
            self.assertEqual(result["did_you_mean"], [])

        asyncio.run(run_test())

    def test_semantic_search_returns_related_results_key(self):
        async def run_test():
            dictionary = DictionaryIndex.from_rows([], [])
            service = SearchService(
                dictionary,
                FakeSemanticEngine(),
                FakeRepository(),
                log_queries=True,
                embedding_model="text-embedding-v4",
                index_version="search-test",
            )
            result = await service.semantic_search("walk", limit=10, include_related=True)
            self.assertEqual(result["results"][0]["lemma"], "lopen")
            self.assertEqual(result["related_results"], [])

        asyncio.run(run_test())

    def test_lookup_uses_fuzzy_fallback_when_dictionary_misses(self):
        async def run_test():
            lemma = LemmaSummary(2, "wandelen", "wandelen", 2, 800)

            class FuzzyRepository(FakeRepository):
                async def fuzzy_lookup(self, query_norm, limit):
                    from lexicon_search.models import LookupCandidate

                    return [LookupCandidate(lemma, None, None, "lemma_fuzzy", 0.7, 0.7)]

            dictionary = DictionaryIndex.from_rows([], [])
            service = SearchService(
                dictionary,
                FakeSemanticEngine(),
                FuzzyRepository(),
                log_queries=True,
                embedding_model="text-embedding-v4",
                index_version="search-test",
            )
            result = await service.lookup("wandele", limit=5)
            self.assertIsNone(result["best_match"])
            self.assertEqual(result["did_you_mean"][0]["lemma"], "wandelen")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
