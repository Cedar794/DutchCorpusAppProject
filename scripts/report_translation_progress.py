#!/usr/bin/env python3
"""Report sense translation chunk progress against local output files and DB rows."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOBS = ROOT / "outputs" / "app_enrichment" / "translation_jobs" / "manifest.json"
DEFAULT_RESULTS = ROOT / "outputs" / "app_enrichment" / "translation_results"


def run_psql_csv(container: str, sql: str) -> list[dict[str, str]]:
    command = [
        "docker",
        "exec",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-c",
        f"copy ({sql}) to stdout with csv header",
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    return list(csv.DictReader(result.stdout.splitlines()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_JOBS)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--container", default="supabase_db_dutch-corpus-database")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    completed = sorted(args.results_dir.glob("chunk_*.translated.jsonl"))
    chunks: list[dict[str, object]] = []
    complete_chunks: list[int] = []
    partial_chunks: list[dict[str, object]] = []
    for path in completed:
        chunk_no = int(path.name.split("_")[1].split(".")[0])
        input_path = ROOT / "outputs" / "app_enrichment" / "translation_jobs" / "chunks" / f"chunk_{chunk_no:05d}.jsonl"
        output_rows = sum(1 for line in path.open("r", encoding="utf-8") if line.strip())
        expected_rows = sum(1 for line in input_path.open("r", encoding="utf-8") if line.strip()) if input_path.exists() else None
        item = {
            "chunk": chunk_no,
            "output_rows": output_rows,
            "expected_rows": expected_rows,
            "is_complete": expected_rows is not None and output_rows == expected_rows,
        }
        chunks.append(item)
        if item["is_complete"]:
            complete_chunks.append(chunk_no)
        else:
            partial_chunks.append(item)
    db_rows = run_psql_csv(
        args.container,
        """
select lang, count(*)::text as rows
from public.sense_translations t
join public.sources s on s.id = t.source_id
where s.source_key = 'llm_sense_translation_v1'
group by lang
order by lang
""".strip(),
    )
    distinct_senses = run_psql_csv(
        args.container,
        """
select count(distinct sense_id)::text as rows
from public.sense_translations t
join public.sources s on s.id = t.source_id
where s.source_key = 'llm_sense_translation_v1'
""".strip(),
    )[0]["rows"]
    missing = [n for n in range(1, manifest["chunk_count"] + 1) if n not in complete_chunks]
    report = {
        "total_senses": manifest["total_senses"],
        "chunk_count": manifest["chunk_count"],
        "completed_chunk_count": len(complete_chunks),
        "completed_chunks": complete_chunks,
        "partial_chunks": partial_chunks,
        "next_missing_chunks": missing[:20],
        "db_distinct_translated_senses": int(distinct_senses),
        "db_translation_rows_by_lang": db_rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
