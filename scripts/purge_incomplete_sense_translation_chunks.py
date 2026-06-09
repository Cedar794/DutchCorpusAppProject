#!/usr/bin/env python3
"""Purge LLM translations for chunks whose output files are incomplete."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "outputs" / "app_enrichment" / "translation_jobs" / "chunks"
RESULTS = ROOT / "outputs" / "app_enrichment" / "translation_results"


def line_count(path: Path) -> int:
    return sum(1 for line in path.open("r", encoding="utf-8") if line.strip())


def sense_ids(path: Path) -> list[int]:
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.append(int(json.loads(line)["sense_id"]))
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="supabase_db_dutch-corpus-database")
    parser.add_argument("--jobs-dir", type=Path, default=JOBS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS)
    args = parser.parse_args()

    incomplete_ids: set[int] = set()
    incomplete_chunks: list[str] = []
    for output_path in sorted(args.results_dir.glob("chunk_*.translated.jsonl")):
        chunk_no = output_path.name.split("_")[1].split(".")[0]
        input_path = args.jobs_dir / f"chunk_{chunk_no}.jsonl"
        if not input_path.exists():
            continue
        expected = line_count(input_path)
        actual = line_count(output_path)
        if actual != expected:
            incomplete_chunks.append(f"chunk_{chunk_no}:{actual}/{expected}")
            incomplete_ids.update(sense_ids(input_path))

    if not incomplete_ids:
        print(json.dumps({"purged_sense_ids": 0, "incomplete_chunks": []}, indent=2))
        return

    values = ",".join(f"({sense_id})" for sense_id in sorted(incomplete_ids))
    sql = f"""
with bad_senses(sense_id) as (values {values})
delete from public.sense_translations t
using public.sources src, bad_senses b
where t.source_id = src.id
  and src.source_key = 'llm_sense_translation_v1'
  and t.sense_id = b.sense_id;
"""
    command = [
        "docker",
        "exec",
        args.container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    subprocess.run(command, check=True)
    print(
        json.dumps(
            {
                "purged_sense_ids": len(incomplete_ids),
                "incomplete_chunks": incomplete_chunks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
