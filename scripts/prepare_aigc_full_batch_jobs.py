#!/usr/bin/env python3
"""Prepare production AIGC completion jobs from the full backlog exports."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKLOG = ROOT / "outputs" / "aigc_full_backlog_v1"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "aigc_full_completion_batches"
MARKER = "#aigc"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_wordnet():
    try:
        from nltk.corpus import wordnet as wn  # type: ignore

        return wn
    except Exception:
        return None


def wordnet_evidence(external_synset_id: str, wn: Any | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "external_synset_id": external_synset_id,
        "wordnet_status": "unavailable",
        "wordnet_synset_name": "",
        "wordnet_definition_en": "",
        "wordnet_lemmas_en": [],
        "wordnet_examples_en": [],
    }
    if not wn:
        return evidence
    match = re.fullmatch(r"eng-30-(\d{8})-([nvar])", external_synset_id or "")
    if not match:
        evidence["wordnet_status"] = "not_eng30"
        return evidence
    offset, pos = match.groups()
    try:
        synset = wn.synset_from_pos_and_offset(pos, int(offset))
    except Exception as exc:
        evidence["wordnet_status"] = f"lookup_error:{type(exc).__name__}"
        return evidence
    evidence.update(
        {
            "wordnet_status": "ok",
            "wordnet_synset_name": synset.name(),
            "wordnet_definition_en": synset.definition(),
            "wordnet_lemmas_en": synset.lemma_names(),
            "wordnet_examples_en": synset.examples(),
        }
    )
    return evidence


def pick_rows(rows: list[dict[str, str]], count: int, skip_noise: bool = False) -> list[dict[str, str]]:
    if count <= 0:
        return []
    picked: list[dict[str, str]] = []
    for row in rows:
        lemma = row.get("lemma_norm", "")
        if skip_noise and (len(lemma) <= 2 or re.search(r"[_'0-9]", lemma)):
            continue
        picked.append(row)
        if len(picked) >= count:
            break
    return picked


def p0_job(row: dict[str, str], batch_id: str, sequence: int, wn: Any | None) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "job_id": f"{batch_id}:p0:{row['sense_id']}",
        "job_sequence": sequence,
        "priority": "P0",
        "task_type": "missing_definition_existing_sense",
        "aigc_marker": MARKER,
        "candidate": row,
        "evidence": wordnet_evidence(row.get("external_synset_id", ""), wn),
        "output_files": ["sense_definitions.tsv", "sense_translations.tsv", "sense_examples.tsv"],
        "required_text_fields": ["definition_nl_aigc", "usage_note_aigc", "gloss", "explanation", "ex_nl"],
    }


def p2_job(row: dict[str, str], batch_id: str, sequence: int) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "job_id": f"{batch_id}:p2:{row['sense_id']}",
        "job_sequence": sequence,
        "priority": "P2",
        "task_type": "missing_zh_translation",
        "aigc_marker": MARKER,
        "candidate": row,
        "output_files": ["sense_translations.tsv"],
        "required_text_fields": ["gloss", "explanation"],
    }


def p4_job(row: dict[str, str], batch_id: str, sequence: int) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "job_id": f"{batch_id}:p4:{row['example_id']}",
        "job_sequence": sequence,
        "priority": "P4",
        "task_type": "missing_example_zh_translation",
        "aigc_marker": MARKER,
        "candidate": row,
        "output_files": ["example_translations.tsv"],
        "required_text_fields": ["translation"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="aigc_full_batch_0001")
    parser.add_argument("--backlog-dir", type=Path, default=DEFAULT_BACKLOG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--p0-count", type=int, default=50)
    parser.add_argument("--p2-count", type=int, default=160)
    parser.add_argument("--p4-count", type=int, default=300)
    parser.add_argument("--p0-chunk-size", type=int, default=50)
    parser.add_argument("--p2-chunk-size", type=int, default=80)
    parser.add_argument("--p4-chunk-size", type=int, default=100)
    args = parser.parse_args()

    wn = load_wordnet()
    batch_dir = args.output_root / args.batch_id
    jobs_dir = batch_dir / "jobs"

    p0_rows = pick_rows(read_tsv(args.backlog_dir / "p0_missing_definitions.tsv"), args.p0_count)
    p2_rows = pick_rows(read_tsv(args.backlog_dir / "p2_missing_zh_translations.tsv"), args.p2_count)
    p4_rows = pick_rows(read_tsv(args.backlog_dir / "p4_missing_example_zh_translations.tsv"), args.p4_count)

    jobs: list[dict[str, Any]] = []
    sequence = 1
    for row in p0_rows:
        jobs.append(p0_job(row, args.batch_id, sequence, wn))
        sequence += 1
    for row in p2_rows:
        jobs.append(p2_job(row, args.batch_id, sequence))
        sequence += 1
    for row in p4_rows:
        jobs.append(p4_job(row, args.batch_id, sequence))
        sequence += 1

    write_jsonl(jobs_dir / "all_jobs.jsonl", jobs)

    chunk_paths: list[str] = []
    chunk_index = 1
    for priority, chunk_size in [("P0", args.p0_chunk_size), ("P2", args.p2_chunk_size), ("P4", args.p4_chunk_size)]:
        priority_jobs = [job for job in jobs if job["priority"] == priority]
        for offset in range(0, len(priority_jobs), chunk_size):
            chunk = priority_jobs[offset : offset + chunk_size]
            if not chunk:
                continue
            chunk_path = jobs_dir / "chunks" / f"chunk_{chunk_index:03d}_{priority.lower()}.jsonl"
            write_jsonl(chunk_path, chunk)
            chunk_paths.append(str(chunk_path.relative_to(ROOT)))
            chunk_index += 1

    manifest = {
        "batch_id": args.batch_id,
        "jobs": len(jobs),
        "p0_jobs": len(p0_rows),
        "p2_jobs": len(p2_rows),
        "p4_jobs": len(p4_rows),
        "chunk_paths": chunk_paths,
        "aigc_marker_required": MARKER,
        "wordnet_available": bool(wn),
    }
    (batch_dir / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (batch_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
