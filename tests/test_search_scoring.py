import unittest

from lexicon_search.scoring import (
    dictionary_score,
    edit_distance,
    normalized_similarity,
    semantic_score,
)


class SearchScoringTests(unittest.TestCase):
    def test_edit_distance(self):
        self.assertEqual(edit_distance("lopen", "lopen"), 0)
        self.assertEqual(edit_distance("lopen", "lopem"), 1)
        self.assertEqual(edit_distance("lopen", "lopenen"), 2)

    def test_normalized_similarity(self):
        self.assertEqual(normalized_similarity("lopen", "lopen"), 1.0)
        self.assertGreater(normalized_similarity("lopen", "lopem"), 0.7)

    def test_dictionary_score_prefers_exact_match(self):
        exact = dictionary_score(
            exact_match=True,
            normalized_similarity_value=1.0,
            frequency=100,
            is_canonical=True,
            level=1,
        )
        fuzzy = dictionary_score(
            exact_match=False,
            normalized_similarity_value=0.85,
            frequency=100,
            is_canonical=True,
            level=1,
        )
        self.assertGreater(exact.score, fuzzy.score)
        self.assertIn("exact_match", exact.reasons)

    def test_semantic_score_uses_similarity_as_main_signal(self):
        high = semantic_score(vector_similarity=0.9, frequency=10, level=4)
        low = semantic_score(vector_similarity=0.7, frequency=100000, level=1)
        self.assertGreater(high.score, low.score)


if __name__ == "__main__":
    unittest.main()
