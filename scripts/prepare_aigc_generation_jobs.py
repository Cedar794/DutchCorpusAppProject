#!/usr/bin/env python3
"""Build evidence-backed job chunks for AIGC lexicon completion.

The script prepares generation prompts/jobs only. It does not generate lexical
content and does not modify database tables. P0 ODWN targets are enriched with
WordNet evidence when NLTK WordNet is available.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "aigc_completion_v1"
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

        return wn, None
    except Exception as exc:  # pragma: no cover - environment dependent
        return None, str(exc)


def wordnet_evidence(external_synset_id: str, wn: Any | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "external_synset_id": external_synset_id,
        "wordnet_available": bool(wn),
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
    except Exception as exc:  # pragma: no cover - data dependent
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


def infer_pos_from_lemma(lemma_norm: str) -> str:
    if lemma_norm.endswith("en"):
        return "VERB_OR_NOUN"
    if lemma_norm.endswith(("ief", "eel", "isch", "aardig", "baar", "loos")):
        return "ADJ"
    return "UNKNOWN"


def p0_job(row: dict[str, str], evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": row["batch_id"],
        "job_id": f"p0:{row['source_key']}:{row['external_id']}",
        "priority": "P0",
        "target_type": "existing_empty_definition_sense",
        "action": "generate_missing_definition_and_zh_translation",
        "aigc_marker": MARKER,
        "candidate": row,
        "evidence": evidence,
        "output_contract": {
            "definition_file": "stg_aigc_sense_definitions.tsv",
            "translation_file": "stg_aigc_sense_translations.tsv",
            "required_generated_text_fields": [
                "definition_nl_aigc",
                "usage_note_aigc",
                "gloss",
                "explanation",
            ],
            "rule": "Every generated natural-language field must end with #aigc.",
            "confidence_max": 0.7,
            "review_status": "unreviewed",
        },
    }


def p1_job(row: dict[str, str]) -> dict[str, Any]:
    candidate = dict(row)
    candidate["suggested_app_pos"] = infer_pos_from_lemma(row["lemma_norm"])
    return {
        "batch_id": row["batch_id"],
        "job_id": f"p1:new_sense:{row['lemma_norm']}",
        "priority": "P1",
        "target_type": "new_sense_for_senseless_lemma",
        "action": "generate_new_sense_candidate_and_zh_translation",
        "aigc_marker": MARKER,
        "candidate": candidate,
        "evidence": {
            "level": row["level"],
            "word_family": row.get("word_family", ""),
            "is_academic": row.get("is_academic", ""),
            "academic_source": row.get("academic_source", ""),
            "popularity": row.get("popularity", ""),
        },
        "output_contract": {
            "new_sense_file": "stg_aigc_new_sense_candidates.tsv",
            "translation_file": "stg_aigc_new_sense_translations.tsv",
            "required_generated_text_fields": [
                "definition_nl",
                "usage_note",
                "gloss",
                "explanation",
            ],
            "rule": "Every generated natural-language field must end with #aigc.",
            "confidence_max": 0.65,
            "review_status": "unreviewed",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--p0-count", type=int, default=24)
    parser.add_argument("--p1-count", type=int, default=12)
    parser.add_argument("--chunk-size", type=int, default=12)
    parser.add_argument("--allow-p0-without-wordnet", action="store_true")
    args = parser.parse_args()

    wn, wn_error = load_wordnet()
    p0_rows = read_tsv(args.output_dir / "candidates" / "p0_empty_definition_senses.tsv")
    p1_rows = read_tsv(args.output_dir / "candidates" / "p1_senseless_lemmas.tsv")

    jobs: list[dict[str, Any]] = []
    skipped_p0 = 0
    for row in p0_rows:
        evidence = wordnet_evidence(row.get("external_synset_id", ""), wn)
        if evidence["wordnet_status"] != "ok" and not args.allow_p0_without_wordnet:
            skipped_p0 += 1
            continue
        jobs.append(p0_job(row, evidence))
        if sum(1 for job in jobs if job["priority"] == "P0") >= args.p0_count:
            break

    for row in p1_rows[: args.p1_count]:
        jobs.append(p1_job(row))

    jobs_dir = args.output_dir / "jobs"
    write_jsonl(jobs_dir / "content_generation_batch_001.jsonl", jobs)
    chunk_paths = []
    for idx in range(0, len(jobs), args.chunk_size):
        chunk = jobs[idx : idx + args.chunk_size]
        chunk_path = jobs_dir / "chunks" / f"chunk_{idx // args.chunk_size + 1:03d}.jsonl"
        write_jsonl(chunk_path, chunk)
        chunk_paths.append(str(chunk_path.relative_to(ROOT)))

    manifest = {
        "batch_id": "aigc_completion_v1",
        "job_file": str((jobs_dir / "content_generation_batch_001.jsonl").relative_to(ROOT)),
        "chunk_paths": chunk_paths,
        "jobs": len(jobs),
        "p0_jobs": sum(1 for job in jobs if job["priority"] == "P0"),
        "p1_jobs": sum(1 for job in jobs if job["priority"] == "P1"),
        "p0_skipped_without_wordnet": skipped_p0,
        "wordnet_available": bool(wn),
        "wordnet_error": wn_error,
        "aigc_marker_required": MARKER,
    }
    (jobs_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
