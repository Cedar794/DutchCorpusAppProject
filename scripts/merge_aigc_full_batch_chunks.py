#!/usr/bin/env python3
"""Merge AIGC full-batch per-chunk TSV outputs into staging TSV files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "aigc_full_completion_batches"

FILES = {
    "sense_definitions.tsv": [
        "batch_id",
        "sense_id",
        "lemma_norm",
        "pos",
        "definition_nl_aigc",
        "usage_note_aigc",
        "confidence",
        "review_status",
        "source_key",
        "external_id",
        "raw_payload",
    ],
    "sense_translations.tsv": [
        "batch_id",
        "sense_id",
        "lemma_norm",
        "pos",
        "lang",
        "gloss",
        "explanation",
        "translation_style",
        "confidence",
        "review_status",
        "source_key",
        "external_id",
        "raw_payload",
    ],
    "sense_examples.tsv": [
        "batch_id",
        "sense_id",
        "lemma_norm",
        "pos",
        "ex_nl",
        "source_key",
        "external_id",
        "confidence",
        "review_status",
        "raw_payload",
    ],
    "example_translations.tsv": [
        "batch_id",
        "example_id",
        "lang",
        "translation",
        "source_key",
        "external_id",
        "confidence",
        "review_status",
        "raw_payload",
    ],
}

NORMALIZE_NON_GENERATED = {
    "sense_translations.tsv": ["translation_style"],
}


def read_rows(path: Path, expected_fields: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = list(reader.fieldnames or [])
        errors = []
        if fields != expected_fields:
            errors.append(f"header_mismatch:{path}")
        return list(reader), errors


def write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def normalize(filename: str, rows: list[dict[str, str]]) -> int:
    normalized = 0
    for row in rows:
        for field in NORMALIZE_NON_GENERATED.get(filename, []):
            value = row.get(field, "")
            if "#aigc" in value:
                row[field] = value.replace("#aigc", "").strip()
                normalized += 1
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="aigc_full_batch_0001")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    batch_dir = args.output_root / args.batch_id
    generated_dir = batch_dir / "generated"
    staging_dir = batch_dir / "staging"
    report: dict[str, Any] = {
        "batch_id": args.batch_id,
        "chunk_dirs": [],
        "files": {},
        "normalizations": {},
        "errors": [],
    }

    chunk_dirs = sorted(path for path in generated_dir.glob("chunk_*") if path.is_dir())
    report["chunk_dirs"] = [str(path.relative_to(ROOT)) for path in chunk_dirs]

    for filename, fieldnames in FILES.items():
        merged: list[dict[str, str]] = []
        for chunk_dir in chunk_dirs:
            rows, errors = read_rows(chunk_dir / filename, fieldnames)
            report["errors"].extend(errors)
            merged.extend(rows)
        normalized = normalize(filename, merged)
        if normalized:
            report["normalizations"][filename] = normalized
        write_rows(staging_dir / filename, merged, fieldnames)
        report["files"][filename] = len(merged)

    report_path = batch_dir / "reports" / "merge_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not report["errors"] else 1)


if __name__ == "__main__":
    main()
