#!/usr/bin/env python3
"""Validate staged AIGC lexicon completion files before any import step."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGE = ROOT / "outputs" / "aigc_completion_v1" / "staging"
DEFAULT_REPORT = ROOT / "outputs" / "aigc_completion_v1" / "reports" / "aigc_validation_report.json"
MARKER = "#aigc"

CONTRACTS: dict[str, dict[str, list[str]]] = {
    "stg_aigc_sense_definitions.tsv": {
        "generated": ["definition_nl_aigc", "usage_note_aigc"],
        "forbidden": [
            "batch_id",
            "priority",
            "target_source_key",
            "target_external_id",
            "external_synset_id",
            "lemma_norm",
            "pos",
            "sense_no",
            "source_key",
            "external_id",
            "review_status",
        ],
    },
    "stg_aigc_sense_translations.tsv": {
        "generated": ["gloss", "explanation"],
        "forbidden": [
            "batch_id",
            "priority",
            "target_source_key",
            "target_external_id",
            "lang",
            "source_key",
            "external_id",
            "translation_style",
            "review_status",
        ],
    },
    "stg_aigc_new_sense_candidates.tsv": {
        "generated": ["definition_nl", "usage_note"],
        "forbidden": [
            "batch_id",
            "priority",
            "lemma_norm",
            "pos",
            "source_key",
            "external_id",
            "review_status",
        ],
    },
    "stg_aigc_new_sense_translations.tsv": {
        "generated": ["gloss", "explanation"],
        "forbidden": [
            "batch_id",
            "priority",
            "candidate_external_id",
            "lang",
            "source_key",
            "external_id",
            "translation_style",
            "review_status",
        ],
    },
    "stg_aigc_examples.tsv": {
        "generated": ["ex_nl"],
        "forbidden": ["batch_id", "lemma_norm", "pos", "source_key", "external_id", "review_status"],
    },
    "stg_aigc_example_translations.tsv": {
        "generated": ["translation"],
        "forbidden": ["batch_id", "example_external_id", "lang", "source_key", "external_id", "review_status"],
    },
    "stg_aigc_relations.tsv": {
        "generated": ["notes", "target_text_nl"],
        "forbidden": [
            "batch_id",
            "source_lemma_norm",
            "target_lemma_norm",
            "relation_type",
            "source_key",
            "external_id",
            "review_status",
        ],
    },
}


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def validate_file(path: Path, contract: dict[str, list[str]]) -> dict[str, Any]:
    fields, rows = read_rows(path)
    errors: list[dict[str, Any]] = []
    generated_fields = [field for field in contract["generated"] if field in fields]
    forbidden_fields = [field for field in contract["forbidden"] if field in fields]

    for row_idx, row in enumerate(rows, start=2):
        for field in generated_fields:
            value = (row.get(field) or "").strip()
            if value and not value.endswith(MARKER):
                errors.append(
                    {
                        "line": row_idx,
                        "field": field,
                        "error": "generated_text_missing_terminal_aigc_marker",
                        "value": value,
                    }
                )
        for field in forbidden_fields:
            value = row.get(field) or ""
            if MARKER in value:
                errors.append(
                    {
                        "line": row_idx,
                        "field": field,
                        "error": "marker_in_non_generated_field",
                        "value": value,
                    }
                )
        confidence_value = (row.get("confidence") or "").strip()
        if confidence_value:
            try:
                confidence = float(confidence_value)
            except ValueError:
                errors.append({"line": row_idx, "field": "confidence", "error": "confidence_not_numeric"})
            else:
                if not 0 <= confidence <= 0.75:
                    errors.append(
                        {
                            "line": row_idx,
                            "field": "confidence",
                            "error": "confidence_outside_aigc_staging_range",
                            "value": confidence_value,
                        }
                    )
        review_status = (row.get("review_status") or "").strip()
        if review_status and review_status not in {"unreviewed", "needs_review"}:
            errors.append(
                {
                    "line": row_idx,
                    "field": "review_status",
                    "error": "unexpected_review_status_for_aigc_staging",
                    "value": review_status,
                }
            )

    return {
        "file": str(path.relative_to(ROOT)),
        "exists": True,
        "rows": len(rows),
        "generated_fields_checked": generated_fields,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    file_reports: list[dict[str, Any]] = []
    for filename, contract in CONTRACTS.items():
        path = args.stage_dir / filename
        if not path.exists():
            file_reports.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "exists": False,
                    "rows": 0,
                    "generated_fields_checked": [],
                    "errors": [],
                }
            )
            continue
        file_reports.append(validate_file(path, contract))

    total_rows = sum(report["rows"] for report in file_reports)
    total_errors = sum(len(report["errors"]) for report in file_reports)
    result = {
        "status": "pass" if total_errors == 0 else "fail",
        "marker_required": MARKER,
        "stage_dir": str(args.stage_dir.relative_to(ROOT)),
        "files": file_reports,
        "total_rows": total_rows,
        "total_errors": total_errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
