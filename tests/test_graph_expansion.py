import unittest

from lexicon_search.graph import rank_related_results
from lexicon_search.models import RelatedResult


class GraphExpansionTests(unittest.TestCase):
    def test_rank_related_results_filters_primary_lemmas_and_dedupes(self):
        related = [
            RelatedResult(
                lemma_id=2,
                lemma="wandelen",
                relation_type="synonym",
                source_result_lemma_id=1,
                source_result_sense_id=None,
                source="lemma_relations",
                score=0.8,
            ),
            RelatedResult(
                lemma_id=1,
                lemma="lopen",
                relation_type="family",
                source_result_lemma_id=1,
                source_result_sense_id=None,
                source="lemma_relations",
                score=1.0,
            ),
            RelatedResult(
                lemma_id=2,
                lemma="wandelen",
                relation_type="related",
                source_result_lemma_id=1,
                source_result_sense_id=None,
                source="sense_relations",
                score=0.5,
            ),
        ]

        ranked = rank_related_results(related, primary_lemma_ids=[1], limit=5)

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].lemma, "wandelen")
        self.assertEqual(ranked[0].relation_type, "synonym")


if __name__ == "__main__":
    unittest.main()
