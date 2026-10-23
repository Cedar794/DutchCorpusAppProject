#!/usr/bin/env python3
"""Merge validated subagent replacement outputs into import staging files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from validate_aigc_agent_replacement_outputs import EXAMPLE_FIELDS, SENSE_FIELDS, validate_chunk


ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = ROOT / "outputs" / "aigc_agent_replacement_v1"
MANIFEST_PATH = BASE_DIR / "chunk_manifest.json"
STAGING_DIR = BASE_DIR / "import" / "staging"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-id", action="append", default=[])
    parser.add_argument("--include-warnings", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    chunks = manifest["chunks"]
    if args.chunk_id:
        wanted = set(args.chunk_id)
        chunks = [chunk for chunk in chunks if chunk["chunk_id"] in wanted]

    sense_rows: list[dict[str, str]] = []
    example_rows: list[dict[str, str]] = []
    results = []
    for chunk in chunks:
        output_path = Path(chunk["output"])
        if not output_path.exists():
            continue
        result = validate_chunk(chunk)
        results.append(result)
        if result["status"] != "pass":
            continue
        if result["warnings"] and not args.include_warnings:
            continue
        rows = read_tsv(output_path)
        if chunk["kind"] == "sense":
            sense_rows.extend(rows)
        else:
            example_rows.extend(rows)

    write_tsv(STAGING_DIR / "sense_replacements.tsv", sense_rows, SENSE_FIELDS)
    write_tsv(STAGING_DIR / "example_translation_replacements.tsv", example_rows, EXAMPLE_FIELDS)

    report = {
        "checked_outputs": len(results),
        "merged_sense_rows": len(sense_rows),
        "merged_example_translation_rows": len(example_rows),
        "skipped_with_warnings": sum(1 for result in results if result["status"] == "pass" and result["warnings"] and not args.include_warnings),
        "failed_outputs": sum(1 for result in results if result["status"] == "fail"),
        "staging_dir": str(STAGING_DIR),
    }
    (BASE_DIR / "import" / "merge_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
