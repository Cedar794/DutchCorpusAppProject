import unittest

from lexicon_search.config import SearchConfig, load_config


class SearchPackageTests(unittest.TestCase):
    def test_package_imports(self):
        import lexicon_search

        self.assertEqual(lexicon_search.__version__, "0.1.0")


class SearchConfigTests(unittest.TestCase):
    def test_load_config_from_mapping(self):
        config = load_config(
            {
                "DATABASE_URL": "postgresql://user:pass@example.com:5432/postgres",
                "BAILIAN_API_KEY": "sk-test",
                "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "SEARCH_INDEX_VERSION": "search-2026-06-05",
                "SEARCH_LOG_QUERIES": "false",
                "SEARCH_MAX_LIMIT": "50",
                "SEARCH_EMBEDDING_DIM": "1024",
            }
        )

        self.assertIsInstance(config, SearchConfig)
        self.assertEqual(config.database_url, "postgresql://user:pass@example.com:5432/postgres")
        self.assertEqual(config.bailian_api_key, "sk-test")
        self.assertEqual(config.bailian_base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(config.index_version, "search-2026-06-05")
        self.assertFalse(config.log_queries)
        self.assertEqual(config.max_limit, 50)
        self.assertEqual(config.embedding_dim, 1024)

    def test_missing_required_values_raise(self):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            load_config({"BAILIAN_API_KEY": "sk-test"})

        with self.assertRaisesRegex(ValueError, "BAILIAN_API_KEY"):
            load_config({"DATABASE_URL": "postgresql://example"})

    def test_limit_and_dimension_are_validated(self):
        with self.assertRaisesRegex(ValueError, "SEARCH_MAX_LIMIT"):
            load_config(
                {
                    "DATABASE_URL": "postgresql://example",
                    "BAILIAN_API_KEY": "sk-test",
                    "SEARCH_MAX_LIMIT": "500",
                }
            )

        with self.assertRaisesRegex(ValueError, "SEARCH_EMBEDDING_DIM"):
            load_config(
                {
                    "DATABASE_URL": "postgresql://example",
                    "BAILIAN_API_KEY": "sk-test",
                    "SEARCH_EMBEDDING_DIM": "1536",
                }
            )


if __name__ == "__main__":
    unittest.main()
