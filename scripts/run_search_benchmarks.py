#!/usr/bin/env python3
"""Run labeled HTTP queries; empty input and request failures must never look like success."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import time

import httpx


def recall_at_k(predicted_ids: list[int], expected_ids: list[int], k: int) -> float:
    expected = set(expected_ids)
    return len(set(predicted_ids[:k]) & expected) / len(expected) if expected else 0.0


def reciprocal_rank(predicted_ids: list[int], expected_ids: list[int]) -> float:
    for index, predicted_id in enumerate(predicted_ids, start=1):
        if predicted_id in set(expected_ids):
            return 1.0 / index
    return 0.0


def run_benchmark(client, queries, *, interval=6.1, sleep=time.sleep):
    if not queries:
        raise ValueError('Benchmark input must not be empty')
    rows = []
    for index, item in enumerate(queries):
        if not item.get('expected_lemma_ids'):
            raise ValueError('Each query needs expected_lemma_ids')
        mode = item.get('mode', 'lookup')
        if mode not in {'lookup', 'suggest', 'semantic'}:
            raise ValueError('Unknown query mode')
        if index:
            sleep(interval)
        start = time.perf_counter()
        result = {'query': item['query'], 'mode': mode, 'expected_lemma_ids': item['expected_lemma_ids']}
        try:
            response = (client.post('/semantic-search', json={'query': item['query'], 'limit': 10})
                        if mode == 'semantic' else client.get('/' + mode, params={'q': item['query']}))
            result['http_status'] = response.status_code
            response.raise_for_status()
            body = response.json()
            candidates = (body.get('results', []) if mode == 'semantic' else
                          body.get('suggestions', []) if mode == 'suggest' else
                          [body['best_match']] if body.get('best_match') else body.get('did_you_mean', []))
            predicted = [int(row['lemma_id']) for row in candidates]
            result.update(predicted_lemma_ids=predicted,
                          recall_at_10=recall_at_k(predicted, item['expected_lemma_ids'], 10),
                          reciprocal_rank=reciprocal_rank(predicted, item['expected_lemma_ids']), success=True)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            result.update(success=False, error_type=type(exc).__name__, recall_at_10=0, reciprocal_rank=0)
        result['latency_ms'] = round((time.perf_counter() - start) * 1000, 2)
        rows.append(result)
    times = sorted(row['latency_ms'] for row in rows)
    return {'query_count': len(rows), 'success_count': sum(r['success'] for r in rows),
            'error_count': sum(not r['success'] for r in rows),
            'recall_at_10': statistics.mean(r['recall_at_10'] for r in rows),
            'mrr': statistics.mean(r['reciprocal_rank'] for r in rows),
            'latency_p50_ms': statistics.median(times),
            'latency_p95_ms': times[max(0, math.ceil(len(times)*.95)-1)],
            'results': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='JSON list of query/mode/expected_lemma_ids')
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--interval', type=float, default=6.1, help='Seconds between requests; respects default semantic quota')
    parser.add_argument('--output', default='outputs/search_benchmark_metrics.json')
    args = parser.parse_args()
    if args.interval < 0:
        parser.error('interval must be nonnegative')
    queries = json.loads(Path(args.input).read_text(encoding='utf-8'))
    with httpx.Client(base_url=args.base_url, timeout=120, trust_env=False) as client:
        metrics = run_benchmark(client, queries, interval=args.interval)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
    if metrics['error_count']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
