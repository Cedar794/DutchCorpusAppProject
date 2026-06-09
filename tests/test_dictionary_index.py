import unittest

from lexicon_search.dictionary import DictionaryIndex
from lexicon_search.models import FormSummary, LemmaSummary


class DictionaryIndexTests(unittest.TestCase):
    def setUp(self):
        self.lopen = LemmaSummary(lemma_id=1, lemma="lopen", lemma_norm="lopen", level=1, frequency=1200)
        self.lezen = LemmaSummary(lemma_id=2, lemma="lezen", lemma_norm="lezen", level=1, frequency=900)
        self.index = DictionaryIndex.from_rows(
            lemmas=[self.lopen, self.lezen],
            forms=[
                FormSummary(
                    form_id=10,
                    form="gelopen",
                    form_norm="gelopen",
                    lemma=self.lopen,
                    is_canonical=False,
                    frequency=300,
                ),
                FormSummary(
                    form_id=11,
                    form="lopen",
                    form_norm="lopen",
                    lemma=self.lopen,
                    is_canonical=True,
                    frequency=1200,
                ),
            ],
        )

    def test_lookup_exact_form_returns_lemma(self):
        candidates = self.index.lookup("gelopen", limit=5)

        self.assertEqual(candidates[0].lemma.lemma, "lopen")
        self.assertEqual(candidates[0].match_type, "form_exact")

    def test_lookup_exact_lemma_returns_lemma(self):
        candidates = self.index.lookup("lezen", limit=5)

        self.assertEqual(candidates[0].lemma.lemma, "lezen")
        self.assertEqual(candidates[0].match_type, "lemma_exact")

    def test_suggest_prefix_returns_ranked_candidates(self):
        suggestions = self.index.suggest("lo", limit=5)

        self.assertEqual(suggestions[0].lemma.lemma, "lopen")


if __name__ == "__main__":
    unittest.main()
