#!/usr/bin/env python3
"""Validate subagent-generated replacement chunk outputs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = ROOT / "outputs" / "aigc_agent_replacement_v1"
MANIFEST_PATH = BASE_DIR / "chunk_manifest.json"
MARKER = "#aigc"

SENSE_FIELDS = [
    "batch_id",
    "sense_id",
    "translation_id",
    "example_id",
    "example_translation_id",
    "lemma_norm",
    "pos",
    "definition_nl",
    "usage_note",
    "gloss_zh",
    "explanation_zh",
    "ex_nl",
    "ex_zh",
    "confidence",
    "quality_note",
]

EXAMPLE_FIELDS = [
    "batch_id",
    "translation_id",
    "example_id",
    "sense_id",
    "lemma_norm",
    "pos",
    "translation_zh",
    "confidence",
    "quality_note",
]

SENSE_NL_FIELDS = ["definition_nl", "usage_note", "ex_nl"]
SENSE_ZH_FIELDS = ["gloss_zh", "explanation_zh", "ex_zh", "quality_note"]
EXAMPLE_ZH_FIELDS = ["translation_zh", "quality_note"]

BAD_PATTERNS = [
    re.compile(r"Dit voorbeeld gaat over", re.I),
    re.compile(r"We gebruiken .+ in deze betekenis", re.I),
    re.compile(r"in een eenvoudige zin", re.I),
    re.compile(r"该例句表达"),
    re.compile(r"这个例句用于展示"),
    re.compile(r"基于词形"),
    re.compile(r"手工|人工复核|需人工复核"),
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def chunk_for_id(chunk_id: str) -> dict[str, str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for chunk in manifest["chunks"]:
        if chunk["chunk_id"] == chunk_id:
            return chunk
    raise SystemExit(f"Unknown chunk_id: {chunk_id}")


def marker_ok(value: str) -> bool:
    return bool(re.search(r"#aigc\s*$", value or ""))


def base(value: str) -> str:
    return re.sub(r"#aigc\s*$", "", value or "").strip()


def validate_confidence(value: str) -> bool:
    try:
        score = float(value)
    except ValueError:
        return False
    return 0.0 <= score <= 1.0


def validate_chunk(chunk: dict[str, str]) -> dict[str, object]:
    kind = chunk["kind"]
    input_rows = read_tsv(Path(chunk["input"]))
    output_path = Path(chunk["output"])
    errors: list[str] = []
    warnings: list[str] = []

    if not output_path.exists():
        return {"chunk_id": chunk["chunk_id"], "kind": kind, "status": "missing", "errors": ["output.tsv missing"], "warnings": warnings}

    output_rows = read_tsv(output_path)
    fields = SENSE_FIELDS if kind == "sense" else EXAMPLE_FIELDS
    natural_fields = SENSE_NL_FIELDS + SENSE_ZH_FIELDS if kind == "sense" else EXAMPLE_ZH_FIELDS

    with output_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, [])
    if header != fields:
        errors.append(f"header mismatch: expected {fields}, got {header}")

    if len(output_rows) != len(input_rows):
        errors.append(f"row count mismatch: expected {len(input_rows)}, got {len(output_rows)}")

    key_field = "sense_id" if kind == "sense" else "translation_id"
    expected_ids = [row[key_field] for row in input_rows]
    actual_ids = [row.get(key_field, "") for row in output_rows]
    if sorted(actual_ids) != sorted(expected_ids):
        errors.append(f"{key_field} set mismatch")
    if len(actual_ids) != len(set(actual_ids)):
        errors.append(f"duplicate {key_field} values")

    input_by_key = {row[key_field]: row for row in input_rows}
    for row_index, row in enumerate(output_rows, start=2):
        row_key = row.get(key_field, "")
        src = input_by_key.get(row_key)
        for field in fields:
            if field not in row:
                errors.append(f"line {row_index}: missing field {field}")
        if row.get("batch_id") != chunk["chunk_id"]:
            errors.append(f"line {row_index}: batch_id must equal {chunk['chunk_id']}")
        if not validate_confidence(row.get("confidence", "")):
            errors.append(f"line {row_index}: invalid confidence {row.get('confidence', '')!r}")
        if src:
            for id_field in ["sense_id", "translation_id", "example_id", "example_translation_id", "lemma_norm", "pos"]:
                if id_field in row and id_field in src and row.get(id_field, "") != src.get(id_field, ""):
                    errors.append(f"line {row_index}: {id_field} changed from input")
        for field in natural_fields:
            value = row.get(field, "")
            if not marker_ok(value):
                errors.append(f"line {row_index}: {field} missing terminal #aigc")
            plain = base(value)
            if not plain:
                errors.append(f"line {row_index}: {field} empty before marker")
            if "\t" in value or "\n" in value or "\r" in value:
                errors.append(f"line {row_index}: {field} contains tab/newline")
            for pattern in BAD_PATTERNS:
                if pattern.search(plain):
                    warnings.append(f"line {row_index}: {field} contains suspicious template/review phrase")
        if kind == "sense":
            ex_plain = base(row.get("ex_nl", ""))
            lemma = row.get("lemma_norm", "")
            if lemma and lemma.replace("_", " ") not in ex_plain and lemma not in ex_plain:
                warnings.append(f"line {row_index}: ex_nl may not contain lemma {lemma}")

    status = "pass" if not errors else "fail"
    return {"chunk_id": chunk["chunk_id"], "kind": kind, "status": status, "errors": errors[:200], "warnings": warnings[:200]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-id")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--report", type=Path, default=BASE_DIR / "validation_report.json")
    args = parser.parse_args()

    if args.chunk_id:
        chunks = [chunk_for_id(args.chunk_id)]
    else:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        chunks = manifest["chunks"]
        if not args.all:
            chunks = [chunk for chunk in chunks if Path(chunk["output"]).exists()]

    results = [validate_chunk(chunk) for chunk in chunks]
    summary = {
        "checked_chunks": len(results),
        "pass": sum(1 for result in results if result["status"] == "pass"),
        "fail": sum(1 for result in results if result["status"] == "fail"),
        "missing": sum(1 for result in results if result["status"] == "missing"),
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    if summary["fail"] or summary["missing"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
