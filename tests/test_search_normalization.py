import unittest

from lexicon_search.normalization import accent_key, normalize_query, punctuation_key


class SearchNormalizationTests(unittest.TestCase):
    def test_normalize_query_uses_nfc_casefold_and_trim(self):
        self.assertEqual(normalize_query("  CAFÉ  "), "café")

    def test_accent_key_removes_combining_marks(self):
        self.assertEqual(accent_key("café"), "cafe")
        self.assertEqual(accent_key("e\u0301én"), "een")

    def test_punctuation_key_normalizes_apostrophes_and_hyphens(self):
        self.assertEqual(punctuation_key("opa's fiets"), "opa s fiets")
        self.assertEqual(punctuation_key("auto-ongeluk"), "auto ongeluk")


if __name__ == "__main__":
    unittest.main()
