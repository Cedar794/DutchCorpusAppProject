import unittest

from lexicon_search.db import vector_literal


class SearchDbTests(unittest.TestCase):
    def test_vector_literal_serializes_1024_dimension_vectors(self):
        value = vector_literal([0.1] * 1024)

        self.assertTrue(value.startswith("[0.1,"))
        self.assertTrue(value.endswith("]"))

    def test_vector_literal_rejects_wrong_dimension(self):
        with self.assertRaisesRegex(ValueError, "1024"):
            vector_literal([0.1, 0.2])


if __name__ == "__main__":
    unittest.main()
