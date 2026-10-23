#!/usr/bin/env python3
"""Merge per-chunk AIGC TSV outputs into staging TSV files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GENERATED = ROOT / "outputs" / "aigc_completion_v1" / "generated"
DEFAULT_STAGE = ROOT / "outputs" / "aigc_completion_v1" / "staging"
DEFAULT_REPORT = ROOT / "outputs" / "aigc_completion_v1" / "reports" / "aigc_merge_report.json"

FILES = {
    "stg_aigc_sense_definitions.tsv": [
        "batch_id",
        "priority",
        "target_source_key",
        "target_external_id",
        "external_synset_id",
        "lemma_norm",
        "pos",
        "sense_no",
        "definition_nl_aigc",
        "usage_note_aigc",
        "confidence",
        "review_status",
        "source_key",
        "external_id",
        "raw_payload",
    ],
    "stg_aigc_sense_translations.tsv": [
        "batch_id",
        "priority",
        "target_source_key",
        "target_external_id",
        "external_synset_id",
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
    "stg_aigc_new_sense_candidates.tsv": [
        "batch_id",
        "priority",
        "lemma_norm",
        "display_lemma",
        "pos",
        "word_family",
        "definition_nl",
        "usage_note",
        "domain",
        "register",
        "confidence",
        "review_status",
        "source_key",
        "external_id",
        "raw_payload",
    ],
    "stg_aigc_new_sense_translations.tsv": [
        "batch_id",
        "priority",
        "candidate_external_id",
        "lemma_norm",
        "display_lemma",
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
    "stg_aigc_examples.tsv": [
        "batch_id",
        "priority",
        "target_kind",
        "target_external_id",
        "lemma_norm",
        "pos",
        "ex_nl",
        "source_key",
        "external_id",
        "confidence",
        "review_status",
        "raw_payload",
    ],
    "stg_aigc_example_translations.tsv": [
        "batch_id",
        "priority",
        "example_external_id",
        "lang",
        "translation",
        "source_key",
        "external_id",
        "confidence",
        "review_status",
        "raw_payload",
    ],
    "stg_aigc_relations.tsv": [
        "batch_id",
        "source_lemma_norm",
        "target_lemma_norm",
        "target_text_nl",
        "relation_type",
        "notes",
        "source_key",
        "external_id",
        "confidence",
        "review_status",
        "raw_payload",
    ],
}

NORMALIZE_NON_GENERATED = {
    "stg_aigc_sense_translations.tsv": ["translation_style"],
    "stg_aigc_new_sense_translations.tsv": ["translation_style"],
}


def read_rows(path: Path, expected_fields: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], [f"missing:{path}"]
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


def normalize_rows(filename: str, rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    normalized = 0
    fields = NORMALIZE_NON_GENERATED.get(filename, [])
    for row in rows:
        for field in fields:
            value = row.get(field, "")
            if "#aigc" in value:
                row[field] = value.replace("#aigc", "").strip()
                normalized += 1
    return rows, normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-dir", type=Path, default=DEFAULT_GENERATED)
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    chunk_dirs = sorted(path for path in args.generated_dir.glob("chunk_*") if path.is_dir())
    report: dict[str, Any] = {
        "generated_dir": str(args.generated_dir.relative_to(ROOT)),
        "stage_dir": str(args.stage_dir.relative_to(ROOT)),
        "chunk_dirs": [str(path.relative_to(ROOT)) for path in chunk_dirs],
        "files": {},
        "normalizations": {},
        "errors": [],
    }

    for filename, fieldnames in FILES.items():
        merged_rows: list[dict[str, str]] = []
        for chunk_dir in chunk_dirs:
            rows, errors = read_rows(chunk_dir / filename, fieldnames)
            report["errors"].extend(errors)
            merged_rows.extend(rows)
        merged_rows, normalized = normalize_rows(filename, merged_rows)
        write_rows(args.stage_dir / filename, merged_rows, fieldnames)
        report["files"][filename] = len(merged_rows)
        if normalized:
            report["normalizations"][filename] = {
                "non_generated_aigc_markers_removed": normalized,
                "fields": NORMALIZE_NON_GENERATED.get(filename, []),
            }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not report["errors"] else 1)


if __name__ == "__main__":
    main()
