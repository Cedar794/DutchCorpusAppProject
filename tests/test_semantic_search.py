import asyncio
import unittest

from lexicon_search.models import SemanticCandidate
from lexicon_search.semantic import SemanticSearchEngine, candidate_count_for_limit


class FakeEmbedder:
    async def embed_text(self, text):
        return [0.1] * 1024


class FakeRepository:
    async def match_senses(self, embedding, candidate_count, index_version):
        return [
            SemanticCandidate(10, 1, "lopen", 1, "def1", "zh1", "en1", 0.82, 1200),
            SemanticCandidate(11, 1, "lopen", 1, "def2", "zh2", "en2", 0.75, 1200),
            SemanticCandidate(20, 2, "wandelen", 2, "def3", "zh3", "en3", 0.80, 800),
        ]


class SemanticSearchTests(unittest.TestCase):
    def test_candidate_count_for_limit(self):
        self.assertEqual(candidate_count_for_limit(10), 50)
        self.assertEqual(candidate_count_for_limit(50), 250)

    def test_search_aggregates_senses_to_lemmas(self):
        async def run_test():
            engine = SemanticSearchEngine(FakeEmbedder(), FakeRepository(), index_version="search-test")
            result = await engine.search("walk", limit=10)
            self.assertEqual([item["lemma"] for item in result["results"]], ["lopen", "wandelen"])
            self.assertEqual(result["results"][0]["matched_sense"]["sense_id"], 10)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
