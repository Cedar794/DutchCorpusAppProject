import unittest

from scripts.run_search_benchmarks import reciprocal_rank, recall_at_k


class SearchBenchmarkTests(unittest.TestCase):
    def test_recall_at_k(self):
        self.assertEqual(recall_at_k([1, 2, 3], [2, 4], 3), 0.5)
        self.assertEqual(recall_at_k([1, 2, 3], [4, 5], 3), 0.0)

    def test_reciprocal_rank(self):
        self.assertEqual(reciprocal_rank([3, 2, 1], [2]), 0.5)
        self.assertEqual(reciprocal_rank([3, 2, 1], [5]), 0.0)


if __name__ == "__main__":
    unittest.main()
