#!/usr/bin/env python3
"""Validate LLM sense translation JSONL and emit an import TSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lexicon_search.quality import translation_blockers, translation_signals
DEFAULT_RESULTS = ROOT / "outputs" / "app_enrichment" / "translation_results"


def iter_jsonl(paths: list[Path]):
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield path, line_no, json.loads(line)
                except json.JSONDecodeError as exc:
                    yield path, line_no, {"_error": f"invalid_json: {exc}"}


def normalize_records(obj: dict[str, Any]) -> list[dict[str, Any]]:
    if "_error" in obj:
        return [obj]
    if "translations" in obj:
        records = []
        for lang in ("zh", "en"):
            item = (obj.get("translations") or {}).get(lang) or {}
            records.append(
                {
                    "sense_id": obj.get("sense_id"),
                    "lang": lang,
                    "gloss": item.get("gloss"),
                    "explanation": item.get("explanation"),
                    "raw_payload": obj,
                }
            )
        return records
    return [
        {
            "sense_id": obj.get("sense_id"),
            "lang": obj.get("lang"),
            "gloss": obj.get("gloss"),
            "explanation": obj.get("explanation"),
            "raw_payload": obj,
        }
    ]


def validate_record(record: dict[str, Any]) -> str | None:
    if "_error" in record:
        return str(record["_error"])
    try:
        sense_id = int(record.get("sense_id"))
        if sense_id <= 0:
            return "sense_id_must_be_positive"
    except (TypeError, ValueError):
        return "missing_or_invalid_sense_id"
    if record.get("lang") not in {"zh", "en"}:
        return "invalid_lang"
    if not str(record.get("gloss") or "").strip():
        return "empty_gloss"
    if not str(record.get("explanation") or "").strip():
        return "empty_explanation"
    blockers = translation_blockers(record['lang'], str(record['gloss']), str(record['explanation']))
    if blockers:
        return blockers[0]
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    valid_rows: list[dict[str, str]] = []
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    seen: set[tuple[int, str]] = set()

    for path, line_no, obj in iter_jsonl(args.inputs):
        for record in normalize_records(obj):
            error = validate_record(record)
            if error is None:
                key = (int(record["sense_id"]), str(record["lang"]))
                if key in seen:
                    error = "duplicate_sense_lang"
                else:
                    seen.add(key)
            if error:
                errors.append({"file": str(path), "line": line_no, "error": error, "record": record})
                continue
            signals = translation_signals(record['lang'], str(record['gloss']), str(record['explanation']))
            if signals:
                warnings.append({'sense_id': int(record['sense_id']), 'lang': record['lang'], 'signals': signals})
            valid_rows.append(
                {
                    "sense_id": str(int(record["sense_id"])),
                    "lang": str(record["lang"]),
                    "gloss": str(record["gloss"]).strip(),
                    "explanation": str(record["explanation"]).strip(),
                    "source_key": "llm_sense_translation_v1",
                    "external_id": f"llm-v1:{int(record['sense_id'])}:{record['lang']}",
                    "confidence": "0.700",
                    "review_status": "needs_review" if signals else "unreviewed",
                    "translation_style": "learner_dictionary",
                    "raw_payload": json.dumps(record["raw_payload"], ensure_ascii=False, sort_keys=True),
                }
            )

    tsv_path = args.output_dir / "sense_translations_valid.tsv"
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "sense_id",
                "lang",
                "gloss",
                "explanation",
                "source_key",
                "external_id",
                "confidence",
                "review_status",
                "translation_style",
                "raw_payload",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(valid_rows)

    report = {
        "valid_rows": len(valid_rows),
        "invalid_rows": len(errors),
        "warning_rows": len(warnings),
        "warnings": warnings,
        "input_files": [str(path) for path in args.inputs],
        "output_tsv": str(tsv_path),
        "errors": errors[:200],
    }
    report_path = args.output_dir / "sense_translation_validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"errors", "warnings"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
