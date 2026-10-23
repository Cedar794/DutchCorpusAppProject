#!/usr/bin/env python3
"""Generate one bulk AIGC staging batch for the current remaining backlog.

This is a high-throughput fallback for clearing the full backlog. All generated
natural-language fields are explicitly marked with #aigc and imported as
unreviewed, low-confidence AIGC content.
"""

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


FIELDS = {
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
    "generated_example_translations.tsv": [
        "batch_id",
        "example_external_id",
        "lang",
        "translation",
        "source_key",
        "external_id",
        "confidence",
        "review_status",
        "raw_payload",
    ],
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_wordnet():
    try:
        from nltk.corpus import wordnet as wn  # type: ignore

        return wn
    except Exception:
        return None


def synset_for(external_synset_id: str, wn: Any | None):
    if not wn:
        return None
    match = re.fullmatch(r"eng-30-(\d{8})-([nvar])", external_synset_id or "")
    if not match:
        return None
    offset, pos = match.groups()
    try:
        return wn.synset_from_pos_and_offset(pos, int(offset))
    except Exception:
        return None


def lemmas_for(synset: Any | None, lang: str) -> list[str]:
    if not synset:
        return []
    try:
        return [lemma.replace("_", " ") for lemma in synset.lemma_names(lang=lang)]
    except Exception:
        return []


def clean_text(value: str, limit: int = 140) -> str:
    value = re.sub(r"\s+", " ", (value or "").replace("\t", " ")).strip()
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def raw_payload(job_id: str, generator: str, evidence_summary: str, extra: dict[str, Any] | None = None) -> str:
    payload = {
        "job_id": job_id,
        "generator": generator,
        "aigc": True,
        "marker": MARKER,
        "evidence_summary": ensure_marker(evidence_summary),
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def ensure_marker(value: str) -> str:
    value = clean_text(value, 280)
    if not value.endswith(MARKER):
        value = f"{value}{MARKER}"
    return value


def zh_terms(row: dict[str, str], synset: Any | None) -> list[str]:
    terms = lemmas_for(synset, "cmn")
    if terms:
        return terms[:3]
    definition = clean_text(row.get("definition_nl", ""), 60)
    lemma = row.get("lemma_norm", "")
    if definition:
        return [lemma, "见荷兰语释义"]
    return [lemma]


def nl_terms(row: dict[str, str], synset: Any | None) -> list[str]:
    terms = lemmas_for(synset, "nld")
    if terms:
        return terms[:4]
    lemma = row.get("lemma_norm", "")
    return [lemma] if lemma else []


def definition_for(row: dict[str, str], synset: Any | None) -> tuple[str, str, str]:
    lemma = row["lemma_norm"]
    pos = row.get("pos", "")
    terms = [term for term in nl_terms(row, synset) if term and term != lemma]
    en_def = clean_text(synset.definition(), 120) if synset else ""
    if pos in {"VERB", "WW"}:
        if terms:
            definition = f"een handeling of toestand die verwant is aan {', '.join(terms[:3])}"
        else:
            definition = f"een werkwoordelijke betekenis van {lemma} die handmatig gecontroleerd moet worden"
        note = f"Automatisch aangevuld op basis van synset- of lemma-informatie voor {lemma}"
    elif pos in {"ADJ", "ADJ_FROG"}:
        if terms:
            definition = f"een eigenschap die verwant is aan {', '.join(terms[:3])}"
        else:
            definition = f"een bijvoeglijke betekenis van {lemma} die handmatig gecontroleerd moet worden"
        note = f"Gebruik als eigenschap of beschrijving; controle aanbevolen voor {lemma}"
    elif pos in {"ADV", "BW"}:
        definition = f"een bijwoordelijke betekenis van {lemma} in deze context"
        note = f"Automatisch aangevuld; controleer de precieze gebruikscontext van {lemma}"
    else:
        if terms:
            definition = f"een begrip, persoon of zaak die verwant is aan {', '.join(terms[:3])}"
        else:
            definition = f"een naamwoordelijke betekenis van {lemma} die handmatig gecontroleerd moet worden"
        note = f"Automatisch aangevuld op basis van synset- of lemma-informatie voor {lemma}"
    evidence = en_def or f"lemma={lemma}, pos={pos}"
    return ensure_marker(definition), ensure_marker(note), evidence


def translation_for(row: dict[str, str], synset: Any | None) -> tuple[str, str, str]:
    lemma = row.get("lemma_norm", "")
    terms = zh_terms(row, synset)
    gloss = "；".join(dict.fromkeys(clean_text(term, 20) for term in terms if term)) or lemma
    definition = clean_text(row.get("definition_nl", ""), 80)
    if definition:
        explanation = f"对应荷兰语释义“{definition}”，需人工复核具体义项"
    elif synset:
        explanation = f"基于 WordNet/OMW 义项生成，表示与“{gloss}”相关的意思，需人工复核"
    else:
        explanation = f"基于词形 {lemma} 和词性生成的保守中文释义，需人工复核"
    evidence = definition or (clean_text(synset.definition(), 120) if synset else f"lemma={lemma}")
    return ensure_marker(gloss), ensure_marker(explanation), evidence


def example_for(row: dict[str, str]) -> tuple[str, str]:
    lemma = row.get("lemma_norm", "")
    pos = row.get("pos", "")
    definition = clean_text(row.get("definition_nl", ""), 80)
    if pos in {"VERB", "WW"}:
        ex = f"We gebruiken {lemma} in deze betekenis in een eenvoudige zin"
    elif pos in {"ADJ", "ADJ_FROG"}:
        ex = f"Dit is een {lemma} voorbeeld in deze betekenis"
    elif pos in {"ADV", "BW"}:
        ex = f"Hij gebruikt {lemma} in deze zin"
    else:
        ex = f"Dit voorbeeld gaat over {lemma} in deze betekenis"
    zh = f"这个例句用于展示 {lemma} 的该义项"
    if definition:
        zh = f"这个例句用于展示 {lemma} 的义项：{definition}"
    return ensure_marker(ex), ensure_marker(zh)


def example_translation_for(row: dict[str, str]) -> tuple[str, str]:
    ex_nl = clean_text(row.get("ex_nl", ""), 160)
    lemma = row.get("lemma_norm", "")
    definition = clean_text(row.get("definition_nl", ""), 70)
    if definition:
        translation = f"该例句表达与 {lemma} 的义项“{definition}”相关的意思：{ex_nl}"
    else:
        translation = f"该例句表达与 {lemma} 相关的意思：{ex_nl}"
    return ensure_marker(translation), ex_nl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="aigc_full_bulk_remaining_0002")
    parser.add_argument("--backlog-dir", type=Path, default=DEFAULT_BACKLOG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    wn = load_wordnet()
    batch_dir = args.output_root / args.batch_id
    staging_dir = batch_dir / "staging"
    reports_dir = batch_dir / "reports"

    p0 = read_tsv(args.backlog_dir / "p0_missing_definitions.tsv")
    p2 = read_tsv(args.backlog_dir / "p2_missing_zh_translations.tsv")
    p3 = read_tsv(args.backlog_dir / "p3_missing_sense_examples.tsv")
    p4 = read_tsv(args.backlog_dir / "p4_missing_example_zh_translations.tsv")

    p0_sense_ids = {row["sense_id"] for row in p0}
    sense_definitions: list[dict[str, str]] = []
    sense_translations: list[dict[str, str]] = []
    sense_examples: list[dict[str, str]] = []
    generated_example_translations: list[dict[str, str]] = []
    example_translations: list[dict[str, str]] = []

    translation_seen: set[tuple[str, str, str]] = set()
    example_seen: set[str] = set()

    for idx, row in enumerate(p0, start=1):
        synset = synset_for(row.get("external_synset_id", ""), wn)
        definition, usage_note, evidence = definition_for(row, synset)
        confidence = "0.56" if synset else "0.45"
        sense_definitions.append(
            {
                "batch_id": args.batch_id,
                "sense_id": row["sense_id"],
                "lemma_norm": row["lemma_norm"],
                "pos": row.get("pos", ""),
                "definition_nl_aigc": definition,
                "usage_note_aigc": usage_note,
                "confidence": confidence,
                "review_status": "unreviewed",
                "source_key": "aigc_missing_definition_v2",
                "external_id": f"{args.batch_id}_p0_def_{idx:05d}",
                "raw_payload": raw_payload(f"{args.batch_id}:p0:{row['sense_id']}", args.batch_id, evidence, {"task_type": "P0"}),
            }
        )
        gloss, explanation, tr_evidence = translation_for(row, synset)
        key = (row["sense_id"], "zh", "aigc_sense_translation_v3")
        if key not in translation_seen:
            translation_seen.add(key)
            sense_translations.append(
                {
                    "batch_id": args.batch_id,
                    "sense_id": row["sense_id"],
                    "lemma_norm": row["lemma_norm"],
                    "pos": row.get("pos", ""),
                    "lang": "zh",
                    "gloss": gloss,
                    "explanation": explanation,
                    "translation_style": "learner_dictionary",
                    "confidence": confidence,
                    "review_status": "unreviewed",
                    "source_key": "aigc_sense_translation_v3",
                    "external_id": f"{args.batch_id}_p0_tr_{idx:05d}",
                    "raw_payload": raw_payload(f"{args.batch_id}:p0tr:{row['sense_id']}", args.batch_id, tr_evidence, {"task_type": "P0_TRANSLATION"}),
                }
            )
        ex_nl, ex_zh = example_for(row)
        ex_external_id = f"{args.batch_id}_p0_ex_{idx:05d}"
        sense_examples.append(
            {
                "batch_id": args.batch_id,
                "sense_id": row["sense_id"],
                "lemma_norm": row["lemma_norm"],
                "pos": row.get("pos", ""),
                "ex_nl": ex_nl,
                "source_key": "aigc_sense_examples_v2",
                "external_id": ex_external_id,
                "confidence": "0.46",
                "review_status": "unreviewed",
                "raw_payload": raw_payload(f"{args.batch_id}:p0ex:{row['sense_id']}", args.batch_id, "Generated learner example from lemma/POS context", {"task_type": "P0_EXAMPLE"}),
            }
        )
        generated_example_translations.append(
            {
                "batch_id": args.batch_id,
                "example_external_id": ex_external_id,
                "lang": "zh",
                "translation": ex_zh,
                "source_key": "aigc_example_translation_v2",
                "external_id": f"{args.batch_id}_p0_extr_{idx:05d}",
                "confidence": "0.46",
                "review_status": "unreviewed",
                "raw_payload": raw_payload(f"{args.batch_id}:p0extr:{row['sense_id']}", args.batch_id, "Generated translation for generated learner example", {"task_type": "P0_EXAMPLE_TRANSLATION"}),
            }
        )
        example_seen.add(row["sense_id"])

    for idx, row in enumerate(p2, start=1):
        synset = synset_for(row.get("external_synset_id", ""), wn)
        key = (row["sense_id"], "zh", "aigc_sense_translation_v3")
        if key in translation_seen:
            continue
        translation_seen.add(key)
        gloss, explanation, evidence = translation_for(row, synset)
        sense_translations.append(
            {
                "batch_id": args.batch_id,
                "sense_id": row["sense_id"],
                "lemma_norm": row["lemma_norm"],
                "pos": row.get("pos", ""),
                "lang": "zh",
                "gloss": gloss,
                "explanation": explanation,
                "translation_style": "learner_dictionary",
                "confidence": "0.58" if row.get("definition_nl") else "0.45",
                "review_status": "unreviewed",
                "source_key": "aigc_sense_translation_v3",
                "external_id": f"{args.batch_id}_p2_tr_{idx:05d}",
                "raw_payload": raw_payload(f"{args.batch_id}:p2:{row['sense_id']}", args.batch_id, evidence, {"task_type": "P2"}),
            }
        )

    for idx, row in enumerate(p3, start=1):
        if row["sense_id"] in example_seen:
            continue
        ex_nl, ex_zh = example_for(row)
        ex_external_id = f"{args.batch_id}_p3_ex_{idx:05d}"
        sense_examples.append(
            {
                "batch_id": args.batch_id,
                "sense_id": row["sense_id"],
                "lemma_norm": row["lemma_norm"],
                "pos": row.get("pos", ""),
                "ex_nl": ex_nl,
                "source_key": "aigc_sense_examples_v2",
                "external_id": ex_external_id,
                "confidence": "0.46",
                "review_status": "unreviewed",
                "raw_payload": raw_payload(f"{args.batch_id}:p3:{row['sense_id']}", args.batch_id, "Generated learner example from lemma/POS/definition context", {"task_type": "P3"}),
            }
        )
        generated_example_translations.append(
            {
                "batch_id": args.batch_id,
                "example_external_id": ex_external_id,
                "lang": "zh",
                "translation": ex_zh,
                "source_key": "aigc_example_translation_v2",
                "external_id": f"{args.batch_id}_p3_extr_{idx:05d}",
                "confidence": "0.46",
                "review_status": "unreviewed",
                "raw_payload": raw_payload(f"{args.batch_id}:p3tr:{row['sense_id']}", args.batch_id, "Generated translation for generated learner example", {"task_type": "P3_TRANSLATION"}),
            }
        )

    for idx, row in enumerate(p4, start=1):
        translation, evidence = example_translation_for(row)
        example_translations.append(
            {
                "batch_id": args.batch_id,
                "example_id": row["example_id"],
                "lang": "zh",
                "translation": translation,
                "source_key": "aigc_example_translation_v2",
                "external_id": f"{args.batch_id}_p4_extr_{idx:05d}",
                "confidence": "0.48",
                "review_status": "unreviewed",
                "raw_payload": raw_payload(f"{args.batch_id}:p4:{row['example_id']}", args.batch_id, evidence, {"task_type": "P4"}),
            }
        )

    outputs = {
        "sense_definitions.tsv": sense_definitions,
        "sense_translations.tsv": sense_translations,
        "sense_examples.tsv": sense_examples,
        "example_translations.tsv": example_translations,
        "generated_example_translations.tsv": generated_example_translations,
    }
    for filename, rows in outputs.items():
        write_tsv(staging_dir / filename, rows, FIELDS[filename])

    report = {
        "batch_id": args.batch_id,
        "rows": {filename: len(rows) for filename, rows in outputs.items()},
        "inputs": {"p0": len(p0), "p2": len(p2), "p3": len(p3), "p4": len(p4)},
        "translation_deduped": len(p0) + len(p2) - len(sense_translations),
        "p3_examples_skipped_due_to_p0": len(p0_sense_ids & {row["sense_id"] for row in p3}),
        "marker_required": MARKER,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "generation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
