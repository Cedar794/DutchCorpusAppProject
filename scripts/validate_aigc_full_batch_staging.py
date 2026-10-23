#!/usr/bin/env python3
"""Validate AIGC full-batch staging TSV files before database import."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "aigc_full_completion_batches"
MARKER = "#aigc"

CONTRACTS = {
    "sense_definitions.tsv": {
        "generated": ["definition_nl_aigc", "usage_note_aigc"],
        "forbidden": ["batch_id", "sense_id", "lemma_norm", "pos", "source_key", "external_id", "review_status"],
    },
    "sense_translations.tsv": {
        "generated": ["gloss", "explanation"],
        "forbidden": ["batch_id", "sense_id", "lemma_norm", "pos", "lang", "source_key", "external_id", "translation_style", "review_status"],
    },
    "sense_examples.tsv": {
        "generated": ["ex_nl"],
        "forbidden": ["batch_id", "sense_id", "lemma_norm", "pos", "source_key", "external_id", "review_status"],
    },
    "example_translations.tsv": {
        "generated": ["translation"],
        "forbidden": ["batch_id", "example_id", "lang", "source_key", "external_id", "review_status"],
    },
    "generated_example_translations.tsv": {
        "generated": ["translation"],
        "forbidden": ["batch_id", "example_external_id", "lang", "source_key", "external_id", "review_status"],
    },
}


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def validate_file(path: Path, contract: dict[str, list[str]]) -> dict[str, Any]:
    if not path.exists():
        return {"file": str(path.relative_to(ROOT)), "exists": False, "rows": 0, "errors": []}
    fields, rows = read_rows(path)
    errors: list[dict[str, Any]] = []
    for line_no, row in enumerate(rows, start=2):
        for field in contract["generated"]:
            if field not in fields:
                continue
            value = (row.get(field) or "").strip()
            if value and not value.endswith(MARKER):
                errors.append({"line": line_no, "field": field, "error": "missing_terminal_aigc_marker", "value": value})
        for field in contract["forbidden"]:
            if field in fields and MARKER in (row.get(field) or ""):
                errors.append({"line": line_no, "field": field, "error": "marker_in_non_generated_field", "value": row.get(field)})
        confidence_value = (row.get("confidence") or "").strip()
        if confidence_value:
            try:
                confidence = float(confidence_value)
            except ValueError:
                errors.append({"line": line_no, "field": "confidence", "error": "not_numeric"})
            else:
                if not 0 <= confidence <= 0.75:
                    errors.append({"line": line_no, "field": "confidence", "error": "out_of_range", "value": confidence_value})
        review_status = (row.get("review_status") or "").strip()
        if review_status and review_status not in {"unreviewed", "needs_review"}:
            errors.append({"line": line_no, "field": "review_status", "error": "unexpected_status", "value": review_status})
        raw_payload = (row.get("raw_payload") or "").strip()
        if raw_payload:
            try:
                json.loads(raw_payload)
            except json.JSONDecodeError as exc:
                errors.append({"line": line_no, "field": "raw_payload", "error": f"invalid_json:{exc.msg}"})
    return {"file": str(path.relative_to(ROOT)), "exists": True, "rows": len(rows), "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="aigc_full_batch_0001")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    batch_dir = args.output_root / args.batch_id
    staging_dir = batch_dir / "staging"
    file_reports = [validate_file(staging_dir / filename, contract) for filename, contract in CONTRACTS.items()]
    total_errors = sum(len(report["errors"]) for report in file_reports)
    result = {
        "batch_id": args.batch_id,
        "status": "pass" if total_errors == 0 else "fail",
        "marker_required": MARKER,
        "files": file_reports,
        "total_rows": sum(report["rows"] for report in file_reports),
        "total_errors": total_errors,
    }
    report_path = batch_dir / "reports" / "validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
