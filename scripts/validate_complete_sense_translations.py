#!/usr/bin/env python3
"""Validate only complete translated chunks and emit an import TSV."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_sense_translations.py"
JOBS = ROOT / "outputs" / "app_enrichment" / "translation_jobs" / "chunks"
RESULTS = ROOT / "outputs" / "app_enrichment" / "translation_results"


def line_count(path: Path) -> int:
    return sum(1 for line in path.open("r", encoding="utf-8") if line.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=RESULTS)
    parser.add_argument("--jobs-dir", type=Path, default=JOBS)
    args = parser.parse_args()

    complete: list[Path] = []
    partial: list[str] = []
    for output_path in sorted(args.results_dir.glob("chunk_*.translated.jsonl")):
        chunk_no = output_path.name.split("_")[1].split(".")[0]
        input_path = args.jobs_dir / f"chunk_{chunk_no}.jsonl"
        if not input_path.exists():
            partial.append(f"{output_path.name}: missing input")
            continue
        expected = line_count(input_path)
        actual = line_count(output_path)
        if expected == actual:
            complete.append(output_path)
        else:
            partial.append(f"{output_path.name}: {actual}/{expected} rows")

    if not complete:
        raise SystemExit("no complete translation chunks found")

    command = [
        "/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3",
        str(VALIDATOR),
        *[str(path) for path in complete],
    ]
    subprocess.run(command, check=True)
    print("complete_chunks", len(complete))
    if partial:
        print("partial_chunks")
        for item in partial:
            print(item)


if __name__ == "__main__":
    main()
