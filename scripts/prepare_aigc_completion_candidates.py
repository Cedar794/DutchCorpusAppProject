#!/usr/bin/env python3
"""Prepare staged candidates for AIGC lexicon completion.

This script does not generate content and does not modify the database. It
selects conservative, high-value targets from the full 20260529 export so that
subagents can generate marked `#aigc` content into staging files.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMPORT = ROOT / "outputs" / "supabase_import" / "full_20260529"
DEFAULT_OUTPUT = ROOT / "outputs" / "aigc_completion_v1"

CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "N", "WW", "BW"}

STOP_LEMMAS = {
    "zijn",
    "ik",
    "je",
    "jij",
    "u",
    "hij",
    "zij",
    "we",
    "wij",
    "ze",
    "het",
    "de",
    "een",
    "dat",
    "dit",
    "die",
    "wat",
    "wie",
    "waar",
    "wanneer",
    "hoe",
    "niet",
    "en",
    "of",
    "maar",
    "als",
    "dan",
    "van",
    "voor",
    "met",
    "op",
    "in",
    "aan",
    "om",
    "te",
    "er",
    "hier",
    "daar",
    "naar",
    "bij",
    "door",
    "over",
    "onder",
}

P1_NOISE_LEMMAS = {
    "aan_het",
    "allison",
    "brad",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def is_alphaish_lemma(lemma: str) -> bool:
    if not lemma or lemma in STOP_LEMMAS:
        return False
    if len(lemma) < 4:
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]", lemma):
        return False
    if re.fullmatch(r"[\W_0-9]+", lemma):
        return False
    if re.fullmatch(r"[a-z]+'?[a-z]?", lemma) and len(lemma) <= 3:
        return False
    return True


def is_singleword_generation_candidate(lemma: str) -> bool:
    if not is_alphaish_lemma(lemma):
        return False
    if lemma in P1_NOISE_LEMMAS:
        return False
    if "_" in lemma or "'" in lemma or "/" in lemma:
        return False
    if re.search(r"\d", lemma):
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-dir", type=Path, default=DEFAULT_IMPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--p0-limit", type=int, default=80)
    parser.add_argument("--p1-limit", type=int, default=40)
    parser.add_argument("--p0-max-per-lemma", type=int, default=1)
    args = parser.parse_args()

    lemmas = {row["lemma_norm"]: row for row in read_tsv(args.import_dir / "lemmas.tsv")}
    senses = read_tsv(args.import_dir / "senses.tsv")
    missing_lemmas = read_tsv(args.import_dir / "reports" / "lemmas_missing_external_senses.tsv")

    p0_candidates: list[dict[str, object]] = []
    for sense in senses:
        lemma_norm = sense.get("lemma_norm", "")
        lemma = lemmas.get(lemma_norm)
        if not lemma:
            continue
        if sense.get("source_key") != "odwn_1_3":
            continue
        if (sense.get("definition_nl") or "").strip():
            continue
        if sense.get("pos") not in {"NOUN", "VERB"}:
            continue
        if not is_alphaish_lemma(lemma_norm):
            continue
        level = int(lemma["level"])
        if level > 2:
            continue
        p0_candidates.append(
            {
                "batch_id": "aigc_completion_v1",
                "priority": "P0",
                "target_type": "existing_empty_definition_sense",
                "lemma_norm": lemma_norm,
                "display_lemma": lemma.get("display_lemma") or lemma_norm,
                "level": level,
                "popularity": int(lemma.get("popularity") or 0),
                "pos": sense.get("pos", ""),
                "source_key": sense.get("source_key", ""),
                "external_id": sense.get("external_id", ""),
                "external_synset_id": sense.get("external_synset_id", ""),
                "sense_no": sense.get("sense_no", ""),
                "is_academic": lemma.get("is_academic", ""),
                "academic_source": lemma.get("academic_source", ""),
            }
        )

    p0_candidates.sort(key=lambda r: (int(r["level"]), -int(r["popularity"]), str(r["lemma_norm"]), str(r["pos"])))
    if args.p0_max_per_lemma > 0:
        lemma_counts: dict[str, int] = {}
        diverse_p0: list[dict[str, object]] = []
        for candidate in p0_candidates:
            lemma_norm = str(candidate["lemma_norm"])
            if lemma_counts.get(lemma_norm, 0) >= args.p0_max_per_lemma:
                continue
            lemma_counts[lemma_norm] = lemma_counts.get(lemma_norm, 0) + 1
            diverse_p0.append(candidate)
            if len(diverse_p0) >= args.p0_limit:
                break
        p0_candidates = diverse_p0
    else:
        p0_candidates = p0_candidates[: args.p0_limit]

    p1_candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    missing_sorted = []
    for row in missing_lemmas:
        lemma_norm = row.get("lemma", "")
        lemma = lemmas.get(lemma_norm)
        if not lemma:
            continue
        missing_sorted.append(lemma)
    missing_sorted.sort(
        key=lambda r: (
            0 if r.get("is_academic") == "true" else 1,
            int(r["level"]),
            -int(r.get("popularity") or 0),
            r["lemma_norm"],
        )
    )

    academic_pool = [lemma for lemma in missing_sorted if lemma.get("is_academic") == "true"]
    fallback_pool = [lemma for lemma in missing_sorted if lemma.get("is_academic") != "true"]
    fallback_pool.sort(key=lambda r: (int(r["level"]), -int(r.get("popularity") or 0), r["lemma_norm"]))

    for lemma in academic_pool + fallback_pool:
        lemma_norm = lemma["lemma_norm"]
        if lemma_norm in seen:
            continue
        if not is_singleword_generation_candidate(lemma_norm):
            continue
        level = int(lemma["level"])
        if level > 3:
            continue
        seen.add(lemma_norm)
        # Conservative default: one core noun-like candidate unless a better POS
        # is known later by a generator/reviewer.
        p1_candidates.append(
            {
                "batch_id": "aigc_completion_v1",
                "priority": "P1",
                "target_type": "new_sense_for_senseless_lemma",
                "lemma_norm": lemma_norm,
                "display_lemma": lemma.get("display_lemma") or lemma_norm,
                "level": level,
                "popularity": int(lemma.get("popularity") or 0),
                "suggested_app_pos": "unknown",
                "word_family": lemma.get("word_family", ""),
                "is_academic": lemma.get("is_academic", ""),
                "academic_source": lemma.get("academic_source", ""),
            }
        )
        if len(p1_candidates) >= args.p1_limit:
            break

    p0_fields = [
        "batch_id",
        "priority",
        "target_type",
        "lemma_norm",
        "display_lemma",
        "level",
        "popularity",
        "pos",
        "source_key",
        "external_id",
        "external_synset_id",
        "sense_no",
        "is_academic",
        "academic_source",
    ]
    p1_fields = [
        "batch_id",
        "priority",
        "target_type",
        "lemma_norm",
        "display_lemma",
        "level",
        "popularity",
        "suggested_app_pos",
        "word_family",
        "is_academic",
        "academic_source",
    ]
    write_tsv(args.output_dir / "candidates" / "p0_empty_definition_senses.tsv", p0_candidates, p0_fields)
    write_tsv(args.output_dir / "candidates" / "p1_senseless_lemmas.tsv", p1_candidates, p1_fields)

    manifest = {
        "batch_id": "aigc_completion_v1",
        "p0_candidates": len(p0_candidates),
        "p1_candidates": len(p1_candidates),
        "p0_rule": "ODWN empty definition, NOUN/VERB, level<=2, alphaish lemma, stop/function words excluded",
        "p0_max_per_lemma": args.p0_max_per_lemma,
        "p1_rule": "lemma has no external sense, level<=3, academic candidates first, single-word alphaish lemma, stop/noise words excluded",
        "aigc_marker_required": "#aigc",
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
