import math
import unittest

from cc100_subtlex.core import (
    count_token_lines,
    count_rows,
    dot_join,
    is_lowercase_token,
    iter_word_tokens,
    subtlex_cd,
    subtlex_wf,
    zipf_frequency,
)


class CoreTests(unittest.TestCase):
    def test_iter_word_tokens_keeps_dutch_letters_and_internal_separators(self):
        text = "Gevelreiniging, cafe, café, auto-ongeluk en opa's fiets."
        self.assertEqual(
            list(iter_word_tokens(text)),
            ["Gevelreiniging", "cafe", "café", "auto-ongeluk", "en", "opa's", "fiets"],
        )

    def test_is_lowercase_token_tracks_original_case(self):
        self.assertFalse(is_lowercase_token("Amsterdam"))
        self.assertTrue(is_lowercase_token("amsterdam"))
        self.assertTrue(is_lowercase_token("café"))

    def test_subtlex_frequency_formulas(self):
        self.assertAlmostEqual(subtlex_wf(25, 1_000), 25_000.0)
        self.assertAlmostEqual(zipf_frequency(25, 1_000), math.log10(25_000_000.0))
        self.assertAlmostEqual(subtlex_cd(5, 200), 2.5)

    def test_dot_join_matches_subtlex_style(self):
        self.assertEqual(dot_join(["VNW", "N", "WW"]), ".VNW.N.WW.")
        self.assertEqual(dot_join([10, 2, 1]), ".10.2.1.")

    def test_count_token_lines_tracks_frequency_and_document_frequency(self):
        result = count_token_lines(["Ik ben ik", "ik Amsterdam"])

        self.assertEqual(result.total_documents, 2)
        self.assertEqual(result.total_tokens, 5)
        self.assertEqual(result.word_freq["ik"], 3)
        self.assertEqual(result.word_low_freq["ik"], 2)
        self.assertEqual(result.word_doc_freq["ik"], 2)
        self.assertEqual(result.word_low_doc_freq["ik"], 2)
        self.assertEqual(result.word_freq["amsterdam"], 1)
        self.assertEqual(result.word_low_freq["amsterdam"], 0)
        self.assertEqual(result.word_doc_freq["amsterdam"], 1)
        self.assertEqual(result.word_low_doc_freq["amsterdam"], 0)

    def test_count_rows_emit_deterministic_word_sorted_rows(self):
        result = count_token_lines(["b a a", "B"])
        self.assertEqual(
            list(count_rows(result)),
            [
                ("a", 2, 2, 1, 1),
                ("b", 2, 1, 2, 1),
            ],
        )


if __name__ == "__main__":
    unittest.main()
