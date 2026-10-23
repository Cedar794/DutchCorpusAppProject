import unittest

from lexicon_search.models import LemmaSummary, LookupCandidate, SemanticCandidate


class SearchModelTests(unittest.TestCase):
    def test_lookup_candidate_to_public_dict(self):
        lemma = LemmaSummary(lemma_id=1, lemma="lopen", lemma_norm="lopen", level=1, frequency=1200)
        candidate = LookupCandidate(
            lemma=lemma,
            form_id=5,
            form="gelopen",
            match_type="form_exact",
            score=0.96,
            confidence=0.96,
        )

        self.assertEqual(
            candidate.to_public_dict(),
            {
                "lemma_id": 1,
                "entry_url": "/entries/1",
                "lemma": "lopen",
                "level": 1,
                "form_id": 5,
                "form": "gelopen",
                "match_type": "form_exact",
                "score": 0.96,
                "confidence": 0.96,
            },
        )

    def test_semantic_candidate_similarity(self):
        candidate = SemanticCandidate(
            sense_id=10,
            lemma_id=1,
            lemma="lopen",
            level=1,
            definition_nl="zich te voet voortbewegen",
            translation_zh="步行",
            translation_en="to walk",
            vector_similarity=0.82,
            frequency=1200,
        )

        self.assertEqual(candidate.best_sense_id, 10)
        self.assertEqual(candidate.lemma, "lopen")


if __name__ == "__main__":
    unittest.main()
