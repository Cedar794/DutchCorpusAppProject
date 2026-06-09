import unittest

from lexicon_search.index_builder import SenseEmbeddingInput, build_embedding_text, hash_embedding_text


class IndexBuilderTests(unittest.TestCase):
    def test_build_embedding_text_uses_only_sense_text(self):
        row = SenseEmbeddingInput(
            sense_id=1,
            definition_nl="zich te voet voortbewegen",
            translation_zh="步行",
            translation_en="to walk",
        )

        text = build_embedding_text(row)

        self.assertIn("definition_nl: zich te voet voortbewegen", text)
        self.assertIn("translation_zh:", text)
        self.assertIn("translation_en: to walk", text)
        self.assertNotIn("lemma", text)

    def test_hash_embedding_text_is_stable(self):
        self.assertEqual(hash_embedding_text("abc"), hash_embedding_text("abc"))
        self.assertNotEqual(hash_embedding_text("abc"), hash_embedding_text("abcd"))


if __name__ == "__main__":
    unittest.main()
