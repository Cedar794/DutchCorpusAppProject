#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "vocabulary_levels.json"
CC100_DB = ROOT / "outputs" / "annotated_batches" / "annotated_full_live_w8_b4000" / "merged_annotated_counts.sqlite"


FROG_POS_DESCRIPTIONS = {
    "ADJ": ("Adjective", "Bijvoeglijk naamwoord", "形容词"),
    "BW": ("Adverb", "Bijwoord", "副词"),
    "LET": ("Punctuation", "Leesteken", "标点"),
    "LID": ("Article", "Lidwoord", "冠词"),
    "N": ("Noun", "Zelfstandig naamwoord", "名词"),
    "SPEC": ("Special", "Speciaal", "特殊类"),
    "TSW": ("Interjection", "Tussenwerpsel", "感叹词"),
    "TW": ("Numeral", "Telwoord", "数词"),
    "VG": ("Conjunction", "Voegwoord", "连词"),
    "VNW": ("Pronoun", "Voornaamwoord", "代词"),
    "VZ": ("Preposition", "Voorzetsel", "介词"),
    "WW": ("Verb", "Werkwoord", "动词"),
}


def norm(value: object) -> str:
    return unicodedata.normalize("NFC", ("" if value is None else str(value)).strip().lower())


def raw_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_tsv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def pos_tag_row(tag: str) -> dict[str, object]:
    english, dutch, zh = FROG_POS_DESCRIPTIONS.get(tag, (tag, tag, "CC100/Frog POS 标签"))
    return {
        "tag": tag,
        "english": english,
        "dutch": dutch,
        "description_zh": zh,
        "example": "",
        "sort_order": 2000,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=CC100_DB)
    args = parser.parse_args()

    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    target_lemmas = sorted({norm(row["lemma"]) for row in vocab})

    start = time.time()
    conn = sqlite3.connect(str(args.db))
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("CREATE TEMP TABLE target_lemmas (lemma TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO target_lemmas (lemma) VALUES (?)", [(lemma,) for lemma in target_lemmas])

    sql = """
        SELECT
            w.lemma,
            w.pos,
            w.word,
            w.freq,
            wc.doc_freq,
            wc.low_freq,
            wc.low_doc_freq
        FROM word_pos_lemma_counts AS w
        JOIN target_lemmas AS t ON t.lemma = w.lemma
        LEFT JOIN word_counts AS wc ON wc.word = w.word
    """

    forms: dict[tuple[str, str, str], dict[str, object]] = {}
    stats: dict[tuple[str, str, str], dict[str, object]] = {}
    pos_entries: dict[tuple[str, str], dict[str, object]] = {}
    pos_tags: set[str] = set()
    matched = 0
    for lemma_norm, pos, word, freq, doc_freq, low_freq, low_doc_freq in conn.execute(sql):
        matched += 1
        form_norm = norm(word)
        pos = str(pos or "X")
        key = (lemma_norm, pos, form_norm)
        pos_tags.add(pos)
        pos_entries[(lemma_norm, pos)] = {
            "lemma_norm": lemma_norm,
            "pos": pos,
            "pos_source": "cc100_nl_local_20260525",
            "pos_confidence": "0.800",
            "gender": "",
            "article": "",
            "external_entry_id": "",
            "is_primary": "false",
            "needs_review": "false",
            "notes": "",
        }
        if key not in forms:
            forms[key] = {
                "lemma_norm": lemma_norm,
                "pos": pos,
                "form": word,
                "form_norm": form_norm,
                "form_type": "cc100_observed",
                "source_key": "cc100_nl_local_20260525",
                "external_id": f"cc100:{lemma_norm}:{pos}:{form_norm}",
                "is_canonical": "false",
                "confidence": "0.800",
                "raw_payload": raw_json({}),
            }
        stats[key] = {
            "lemma_norm": lemma_norm,
            "pos": pos,
            "form_norm": form_norm,
            "form_type": "cc100_observed",
            "corpus_key": "cc100_nl_local_20260525",
            "freq_count": int(freq or 0),
            "doc_count": int(doc_freq or 0),
            "freq_low": int(low_freq or 0),
            "doc_low": int(low_doc_freq or 0),
            "zipf": "",
            "rank": "",
            "metadata": raw_json({}),
        }

    counts = {
        "cc100_pos_tags_extra.tsv": write_tsv(
            args.output_dir / "cc100_pos_tags_extra.tsv",
            ["tag", "english", "dutch", "description_zh", "example", "sort_order"],
            [pos_tag_row(tag) for tag in sorted(pos_tags)],
        ),
        "cc100_lemma_pos_entries.tsv": write_tsv(
            args.output_dir / "cc100_lemma_pos_entries.tsv",
            [
                "lemma_norm",
                "pos",
                "pos_source",
                "pos_confidence",
                "gender",
                "article",
                "external_entry_id",
                "is_primary",
                "needs_review",
                "notes",
            ],
            sorted(pos_entries.values(), key=lambda row: (row["lemma_norm"], row["pos"])),
        ),
        "cc100_forms.tsv": write_tsv(
            args.output_dir / "cc100_forms.tsv",
            [
                "lemma_norm",
                "pos",
                "form",
                "form_norm",
                "form_type",
                "source_key",
                "external_id",
                "is_canonical",
                "confidence",
                "raw_payload",
            ],
            sorted(forms.values(), key=lambda row: (row["lemma_norm"], row["pos"], row["form_norm"])),
        ),
        "cc100_form_corpus_stats.tsv": write_tsv(
            args.output_dir / "cc100_form_corpus_stats.tsv",
            [
                "lemma_norm",
                "pos",
                "form_norm",
                "form_type",
                "corpus_key",
                "freq_count",
                "doc_count",
                "freq_low",
                "doc_low",
                "zipf",
                "rank",
                "metadata",
            ],
            sorted(stats.values(), key=lambda row: (row["lemma_norm"], row["pos"], row["form_norm"])),
        ),
    }
    (args.output_dir / "cc100_extract_metadata.json").write_text(
        json.dumps(
            {
                "target_lemmas": len(target_lemmas),
                "matched_word_pos_lemma_rows": matched,
                "elapsed_seconds": round(time.time() - start, 3),
                "counts": counts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    for name, count in counts.items():
        print(f"{name}\t{count}")
    print(f"matched_word_pos_lemma_rows\t{matched}")
    print(f"elapsed_seconds\t{time.time() - start:.3f}")


if __name__ == "__main__":
    main()
