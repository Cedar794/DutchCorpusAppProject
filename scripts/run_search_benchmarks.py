#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def recall_at_k(predicted_ids: list[int], expected_ids: list[int], k: int) -> float:
    expected = set(expected_ids)
    if not expected:
        return 0.0
    predicted = set(predicted_ids[:k])
    return len(predicted & expected) / len(expected)


def reciprocal_rank(predicted_ids: list[int], expected_ids: list[int]) -> float:
    expected = set(expected_ids)
    for index, predicted_id in enumerate(predicted_ids, start=1):
        if predicted_id in expected:
            return 1.0 / index
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="outputs/search_benchmark_metrics.json")
    args = parser.parse_args()

    metrics = {
        "recall_at_10": 0.0,
        "mrr": 0.0,
        "query_count": 0,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
