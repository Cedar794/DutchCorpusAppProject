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

class ResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_failure_resumes_only_unwritten_and_changed_rows(self):
        from lexicon_search.index_builder import rebuild_embeddings
        rows = [SenseEmbeddingInput(i, 'definition', '释义 #aigc', '', lemma=f'word{i}') for i in range(3)]
        class Repo:
            hashes = {}
            async def load_senses_for_embedding(self, limit=None): return rows
            async def load_embedding_hashes(self, *args): return self.hashes
            async def upsert_sense_embeddings(self, batch):
                for row in batch: self.hashes[row[0]] = row[4]
        class Client:
            calls = 0
            fail = True
            async def embed_texts(self, texts):
                self.calls += 1
                if self.calls == 2 and self.fail: raise RuntimeError('interrupted')
                return [[0.1] * 1024 for _ in texts]
        repo, client = Repo(), Client()
        options = dict(repository=repo, embedding_client=client, embedding_model='test',
                       embedding_dim=1024, index_version='test', batch_size=1)
        with self.assertRaises(RuntimeError): await rebuild_embeddings(**options)
        self.assertEqual(len(repo.hashes), 1)
        client.fail = False
        result = await rebuild_embeddings(**options)
        self.assertEqual(result['embedded'], 2)
        self.assertEqual(result['unchanged'], 1)
        result = await rebuild_embeddings(**options)
        self.assertEqual(result['embedded'], 0)
        rows[0] = SenseEmbeddingInput(0, 'changed', '', '')
        result = await rebuild_embeddings(**options)
        self.assertEqual(result['embedded'], 1)
        self.assertNotIn('#aigc', build_embedding_text(rows[1]))


if __name__ == "__main__":
    unittest.main()
