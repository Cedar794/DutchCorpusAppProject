import unittest

from scripts.run_search_benchmarks import reciprocal_rank, recall_at_k


class SearchBenchmarkTests(unittest.TestCase):
    def test_recall_at_k(self):
        self.assertEqual(recall_at_k([1, 2, 3], [2, 4], 3), 0.5)
        self.assertEqual(recall_at_k([1, 2, 3], [4, 5], 3), 0.0)

    def test_reciprocal_rank(self):
        self.assertEqual(reciprocal_rank([3, 2, 1], [2]), 0.5)
        self.assertEqual(reciprocal_rank([3, 2, 1], [5]), 0.0)

class BenchmarkRunnerTests(unittest.TestCase):
    def test_real_response_ranking_and_failure_are_recorded(self):
        import httpx
        from scripts.run_search_benchmarks import run_benchmark
        def handler(request):
            if request.url.params['q'] == 'fail': return httpx.Response(429)
            return httpx.Response(200, json={'best_match': {'lemma_id': 2}})
        with httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test') as client:
            report = run_benchmark(client, [{'query': 'ok', 'expected_lemma_ids': [2]},
                                           {'query': 'fail', 'expected_lemma_ids': [3]}], interval=0)
            self.assertEqual(report['error_count'], 1)
            self.assertEqual(report['mrr'], 0.5)
            self.assertEqual(report['results'][1]['http_status'], 429)
            with self.assertRaises(ValueError): run_benchmark(client, [])


if __name__ == "__main__":
    unittest.main()
