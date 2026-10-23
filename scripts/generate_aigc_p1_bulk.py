#!/usr/bin/env python3
"""Generate AIGC new-sense staging rows for all remaining senseless lemmas."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKLOG = ROOT / "outputs" / "aigc_full_backlog_v1"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "aigc_full_completion_batches"
MARKER = "#aigc"

FIELDS = {
    "p1_new_senses.tsv": [
        "batch_id",
        "lemma_id",
        "lemma_norm",
        "display_lemma",
        "pos",
        "definition_nl",
        "usage_note",
        "confidence",
        "review_status",
        "source_key",
        "external_id",
        "raw_payload",
    ],
    "p1_sense_translations.tsv": [
        "batch_id",
        "sense_external_id",
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
    "p1_sense_examples.tsv": [
        "batch_id",
        "sense_external_id",
        "lemma_norm",
        "pos",
        "ex_nl",
        "source_key",
        "external_id",
        "confidence",
        "review_status",
        "raw_payload",
    ],
    "p1_generated_example_translations.tsv": [
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

POS_PRIORITY = [
    "NOUN",
    "N",
    "WW",
    "VERB",
    "ADJ",
    "BW",
    "ADV",
    "PRONOM-POS",
    "PRONOM-DEM",
    "PRONOM-INDEF",
    "VNW",
    "VZ",
    "ADP",
    "INTJ",
    "TSW",
    "LID",
    "TW",
    "VG",
    "ABBR",
    "SPEC",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: str, limit: int = 160) -> str:
    value = re.sub(r"\s+", " ", (value or "").replace("\t", " ")).strip()
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def marked(value: str) -> str:
    value = clean(value, 260)
    if not value.endswith(MARKER):
        value = f"{value}{MARKER}"
    return value


def choose_pos(row: dict[str, str]) -> str:
    tags = [tag for tag in row.get("observed_pos_tags", "").split(",") if tag]
    lemma = row["lemma_norm"]
    if "'" in lemma:
        for tag in ["PRONOM-POS", "PRONOM-DEM", "VNW"]:
            if tag in tags:
                return tag
    if "_" in lemma:
        for tag in ["BW", "VZ", "ADP", "VNW", "SPEC", "N"]:
            if tag in tags:
                return tag
    for tag in POS_PRIORITY:
        if tag in tags:
            return tag
    return tags[0] if tags else "SPEC"


def definition(row: dict[str, str], pos: str) -> tuple[str, str, str, str]:
    lemma = row["lemma_norm"]
    display = row.get("display_lemma") or lemma
    readable = display.replace("_", " ")
    if pos in {"N", "NOUN"}:
        nl = f"een naamwoordelijke betekenis of vaste leeseenheid bij {readable}"
        zh = f"{readable}（名词性义项）"
        note = f"Automatisch aangemaakt voor lemma zonder bestaande sense; inhoud vereist menselijke controle"
    elif pos in {"WW", "VERB"}:
        nl = f"een werkwoordelijke betekenis of gebruiksvorm bij {readable}"
        zh = f"{readable}（动词性义项）"
        note = f"Automatisch aangemaakt voor werkwoordelijk gebruik; controle van vervoeging en betekenis vereist"
    elif pos in {"ADJ"}:
        nl = f"een beschrijvende of bijvoeglijke betekenis bij {readable}"
        zh = f"{readable}（形容词性义项）"
        note = f"Automatisch aangemaakt voor beschrijvend gebruik; betekenis vereist menselijke controle"
    elif pos in {"BW", "ADV"}:
        nl = f"een bijwoordelijke of zinsmodificerende betekenis bij {readable}"
        zh = f"{readable}（副词性义项）"
        note = f"Automatisch aangemaakt voor bijwoordelijk gebruik; contextcontrole vereist"
    elif pos.startswith("PRONOM") or pos == "VNW":
        nl = f"een voornaamwoordelijke betekenis of verwijzende vorm bij {readable}"
        zh = f"{readable}（代词性形式）"
        note = f"Automatisch aangemaakt voor voornaamwoordelijk gebruik; grammaticale functie vereist controle"
    elif pos in {"VZ", "ADP"}:
        nl = f"een voorzetselachtige of vaste uitdrukkingsvorm bij {readable}"
        zh = f"{readable}（介词或固定表达）"
        note = f"Automatisch aangemaakt voor uitdrukking of voorzetselgroep; betekenis vereist controle"
    elif pos in {"INTJ", "TSW"}:
        nl = f"een uitroepende of gesprekssignaalbetekenis bij {readable}"
        zh = f"{readable}（感叹或话语标记）"
        note = f"Automatisch aangemaakt voor spreektaalgebruik; register vereist controle"
    elif pos == "ABBR":
        nl = f"een afkorting of verkorte vorm bij {readable}"
        zh = f"{readable}（缩写形式）"
        note = f"Automatisch aangemaakt voor afkorting; volledige vorm vereist controle"
    else:
        nl = f"een speciale of vaste vorm bij {readable}"
        zh = f"{readable}（特殊词形）"
        note = f"Automatisch aangemaakt voor lemma zonder sense; classificatie vereist controle"
    example = f"Het woord {readable} wordt hier als aparte betekenis behandeld"
    return marked(nl), marked(note), marked(zh), marked(example)


def raw_payload(job_id: str, generator: str, evidence: str) -> str:
    return json.dumps(
        {
            "job_id": job_id,
            "generator": generator,
            "aigc": True,
            "marker": MARKER,
            "evidence_summary": marked(evidence),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="aigc_p1_bulk_remaining_0003")
    parser.add_argument("--backlog-dir", type=Path, default=DEFAULT_BACKLOG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    rows = read_tsv(args.backlog_dir / "p1_senseless_lemmas.tsv")
    staging_dir = args.output_root / args.batch_id / "staging"
    reports_dir = args.output_root / args.batch_id / "reports"

    new_senses: list[dict[str, str]] = []
    translations: list[dict[str, str]] = []
    examples: list[dict[str, str]] = []
    example_translations: list[dict[str, str]] = []

    for idx, row in enumerate(rows, start=1):
        pos = choose_pos(row)
        def_nl, usage_note, gloss, ex_nl = definition(row, pos)
        sense_external_id = f"{args.batch_id}_sense_{idx:05d}"
        ex_external_id = f"{args.batch_id}_ex_{idx:05d}"
        confidence = "0.42"
        evidence = f"lemma_id={row['lemma_id']}; observed_pos_tags={row.get('observed_pos_tags','')}; chosen_pos={pos}"
        new_senses.append(
            {
                "batch_id": args.batch_id,
                "lemma_id": row["lemma_id"],
                "lemma_norm": row["lemma_norm"],
                "display_lemma": row.get("display_lemma", ""),
                "pos": pos,
                "definition_nl": def_nl,
                "usage_note": usage_note,
                "confidence": confidence,
                "review_status": "unreviewed",
                "source_key": "aigc_missing_sense_v2",
                "external_id": sense_external_id,
                "raw_payload": raw_payload(f"{args.batch_id}:p1:{row['lemma_id']}", args.batch_id, evidence),
            }
        )
        translations.append(
            {
                "batch_id": args.batch_id,
                "sense_external_id": sense_external_id,
                "lemma_norm": row["lemma_norm"],
                "pos": pos,
                "lang": "zh",
                "gloss": gloss,
                "explanation": marked(f"为无 sense 词条 {row['lemma_norm']} 生成的低置信度中文学习释义，需人工复核"),
                "translation_style": "learner_dictionary",
                "confidence": confidence,
                "review_status": "unreviewed",
                "source_key": "aigc_sense_translation_v3",
                "external_id": f"{args.batch_id}_tr_{idx:05d}",
                "raw_payload": raw_payload(f"{args.batch_id}:p1tr:{row['lemma_id']}", args.batch_id, evidence),
            }
        )
        examples.append(
            {
                "batch_id": args.batch_id,
                "sense_external_id": sense_external_id,
                "lemma_norm": row["lemma_norm"],
                "pos": pos,
                "ex_nl": ex_nl,
                "source_key": "aigc_sense_examples_v2",
                "external_id": ex_external_id,
                "confidence": confidence,
                "review_status": "unreviewed",
                "raw_payload": raw_payload(f"{args.batch_id}:p1ex:{row['lemma_id']}", args.batch_id, evidence),
            }
        )
        example_translations.append(
            {
                "batch_id": args.batch_id,
                "example_external_id": ex_external_id,
                "lang": "zh",
                "translation": marked(f"这个例句把 {row['lemma_norm']} 作为一个独立义项来展示，需人工复核"),
                "source_key": "aigc_example_translation_v2",
                "external_id": f"{args.batch_id}_extr_{idx:05d}",
                "confidence": confidence,
                "review_status": "unreviewed",
                "raw_payload": raw_payload(f"{args.batch_id}:p1extr:{row['lemma_id']}", args.batch_id, evidence),
            }
        )

    outputs = {
        "p1_new_senses.tsv": new_senses,
        "p1_sense_translations.tsv": translations,
        "p1_sense_examples.tsv": examples,
        "p1_generated_example_translations.tsv": example_translations,
    }
    for filename, out_rows in outputs.items():
        write_tsv(staging_dir / filename, out_rows, FIELDS[filename])

    report = {"batch_id": args.batch_id, "rows": {name: len(out_rows) for name, out_rows in outputs.items()}}
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "generation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
