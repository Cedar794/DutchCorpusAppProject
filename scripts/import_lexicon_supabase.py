#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bz2
import csv
import gzip
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lxml import etree
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
PY_RUNTIME = ROOT / ".unused"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "supabase_import"
SUBTLEX_PATH = ROOT / "SUBTLEX-NL with pos and Zipf.xlsx"
VOCAB_PATH = ROOT / "vocabulary_levels.json"
FORM_LEVELS_PATH = ROOT / "word_forms_levels.xlsx"
ODWN_PATH = Path("/tmp/dutch-lex-sources/odwn.xml.gz")
DBNARY_PATH = Path("/tmp/dutch-lex-sources/nl_dbnary_ontolex.ttl.bz2")


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

DBNARY_POS_MAP = {
    "adj": "ADJ",
    "adjc": "ADJ",
    "adjective": "ADJ",
    "adverb": "ADV",
    "adv": "ADV",
    "art": "DET",
    "article": "DET",
    "conj": "CONJ",
    "conjunction": "CONJ",
    "interj": "INTJ",
    "interjection": "INTJ",
    "name": "PROPN",
    "noun": "NOUN",
    "num": "NUM",
    "number": "NUM",
    "phrase": "X",
    "prep": "ADP",
    "preposition": "ADP",
    "pronom": "PRON",
    "pronomdem": "PRON",
    "pronomindef": "PRON",
    "pronominter": "PRON",
    "pronompers": "PRON",
    "pronomrel": "PRON",
    "verb": "VERB",
}

ODWN_POS_MAP = {
    "adjective": "ADJ",
    "adverb": "ADV",
    "noun": "NOUN",
    "verb": "VERB",
    "propernoun": "PROPN",
    "proper_noun": "PROPN",
}


def norm(value: object) -> str:
    text = "" if value is None else str(value)
    return unicodedata.normalize("NFC", text.strip().lower())


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    text = value.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")
    return unicodedata.normalize("NFC", text.strip())


def raw_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_tsv(path: Path, headers: list[str], rows: Iterable[dict[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})
            count += 1
    return count


def load_vocab(path: Path) -> tuple[list[dict], dict[str, dict]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        row["lemma_norm"] = norm(row["lemma"])
    by_norm = {row["lemma_norm"]: row for row in rows}
    return rows, by_norm


def load_curated_form_levels(path: Path) -> list[dict[str, object]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for index, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if index == 1:
            continue
        form, level = row[:2]
        if form is None or level is None:
            continue
        rows.append(
            {
                "form": str(form),
                "form_norm": norm(form),
                "level": int(level),
                "source_name": "manual_vocab_levels_v1",
                "note": "",
                "raw_payload": raw_json({"source_file": path.name}),
            }
        )
    return rows


def map_odwn_pos(pos: str | None) -> str:
    key = norm(pos).replace(" ", "_")
    return ODWN_POS_MAP.get(key, key.upper() if key else "X")


def map_dbnary_pos(pos: str | None) -> str:
    key = norm(pos)
    return DBNARY_POS_MAP.get(key, key.upper() if key else "X")


def pos_tag_row(tag: str, source: str) -> dict[str, object]:
    if tag in FROG_POS_DESCRIPTIONS:
        english, dutch, zh = FROG_POS_DESCRIPTIONS[tag]
    else:
        english, dutch, zh = tag, tag, f"{source} POS 标签"
    return {
        "tag": tag,
        "english": english,
        "dutch": dutch,
        "description_zh": zh,
        "example": "",
        "sort_order": 1000,
    }


def add_pos_entry(
    store: dict[tuple[str, str], dict[str, object]],
    lemma_norm: str,
    pos: str,
    source: str,
    confidence: float,
    external_entry_id: str = "",
    is_primary: bool = False,
    gender: str = "",
    article: str = "",
) -> None:
    if not lemma_norm or not pos:
        return
    key = (lemma_norm, pos)
    existing = store.get(key)
    if existing is None or confidence > float(existing["pos_confidence"]):
        store[key] = {
            "lemma_norm": lemma_norm,
            "pos": pos,
            "pos_source": source,
            "pos_confidence": f"{confidence:.3f}",
            "gender": gender,
            "article": article,
            "external_entry_id": external_entry_id,
            "is_primary": "true" if is_primary else "false",
            "needs_review": "false",
            "notes": "",
        }


def add_form(
    store: dict[tuple[str, str, str, str], dict[str, object]],
    lemma_norm: str,
    pos: str,
    form: str,
    form_type: str,
    source_key: str,
    external_id: str,
    is_canonical: bool,
    confidence: float,
    raw_payload_dict: dict,
) -> None:
    form_norm = norm(form)
    if not lemma_norm or not pos or not form_norm:
        return
    key = (lemma_norm, pos, form_norm, form_type)
    if key in store:
        return
    store[key] = {
        "lemma_norm": lemma_norm,
        "pos": pos,
        "form": form,
        "form_norm": form_norm,
        "form_type": form_type,
        "source_key": source_key,
        "external_id": external_id,
        "is_canonical": "true" if is_canonical else "false",
        "confidence": f"{confidence:.3f}",
        "raw_payload": raw_json(raw_payload_dict),
    }


def scan_subtlex(
    path: Path,
    target_lemmas: set[str],
    pos_entries: dict[tuple[str, str], dict[str, object]],
    forms: dict[tuple[str, str, str, str], dict[str, object]],
) -> list[dict[str, object]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    index = {name: idx for idx, name in enumerate(headers)}
    stats = []
    rank = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        rank += 1
        lemma_norm = norm(row[index["dominant.pos.lemma"]])
        if lemma_norm not in target_lemmas:
            continue
        form = str(row[index["Word"]])
        pos = str(row[index["dominant.pos"]] or "X")
        add_pos_entry(pos_entries, lemma_norm, pos, "subtlex_nl", 0.950, is_primary=True)
        add_form(
            forms,
            lemma_norm,
            pos,
            form,
            "subtlex_observed",
            "subtlex_nl",
            f"subtlex:{rank}",
            False,
            0.950,
            {"rank": rank, "dominant_pos_lemma": lemma_norm},
        )
        stats.append(
            {
                "lemma_norm": lemma_norm,
                "pos": pos,
                "form_norm": norm(form),
                "form_type": "subtlex_observed",
                "corpus_key": "subtlex_nl",
                "freq_count": int(row[index["FREQcount"]] or 0),
                "doc_count": int(row[index["CDcount"]] or 0),
                "freq_low": int(row[index["FREQlow"]] or 0),
                "doc_low": int(row[index["CDlow"]] or 0),
                "zipf": row[index["Zipf"]] or "",
                "rank": rank,
                "metadata": raw_json({"SUBTLEXWF": row[index["SUBTLEXWF"]], "SUBTLEXCD": row[index["SUBTLEXCD"]]}),
            }
        )
    return stats


def parse_odwn(
    path: Path,
    target_lemmas: set[str],
    pos_entries: dict[tuple[str, str], dict[str, object]],
    forms: dict[tuple[str, str, str, str], dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    senses: list[dict[str, object]] = []
    examples: list[dict[str, object]] = []
    with gzip.open(path, "rb") as handle:
        context = etree.iterparse(handle, events=("end",), tag="LexicalEntry", recover=True)
        for _, entry in context:
            lemma_el = entry.find("Lemma")
            if lemma_el is None:
                entry.clear()
                continue
            lemma = lemma_el.get("writtenForm") or ""
            lemma_norm = norm(lemma)
            if lemma_norm not in target_lemmas:
                entry.clear()
                continue
            pos = map_odwn_pos(entry.get("partOfSpeech"))
            external_entry_id = entry.get("id") or ""
            add_pos_entry(pos_entries, lemma_norm, pos, "odwn_1_3", 0.900, external_entry_id=external_entry_id)
            add_form(
                forms,
                lemma_norm,
                pos,
                lemma,
                "canonical",
                "odwn_1_3",
                f"odwn-form:{external_entry_id}:lemma",
                True,
                0.900,
                {"entry_id": external_entry_id},
            )
            for wf in entry.findall(".//WordForm"):
                written = wf.get("writtenForm")
                if not written:
                    continue
                attrs = {k: v for k, v in wf.attrib.items() if k != "writtenForm"}
                form_type = "odwn_wordform"
                if attrs:
                    form_type = "odwn_" + "_".join(f"{k}={v}" for k, v in sorted(attrs.items()))[:120]
                add_form(
                    forms,
                    lemma_norm,
                    pos,
                    written,
                    form_type,
                    "odwn_1_3",
                    f"odwn-form:{external_entry_id}:{norm(written)}:{form_type}",
                    False,
                    0.900,
                    {"entry_id": external_entry_id, "attributes": attrs},
                )
            for sense in entry.findall("Sense"):
                external_id = sense.get("id") or f"{external_entry_id}:sense:{sense.get('senseId', '')}"
                definition = clean_text(sense.get("definition"))
                senses.append(
                    {
                        "lemma_norm": lemma_norm,
                        "pos": pos,
                        "source_key": "odwn_1_3",
                        "external_id": external_id,
                        "external_synset_id": sense.get("synset") or "",
                        "sense_no": sense.get("senseId") or "",
                        "definition_nl": definition,
                        "usage_note": "",
                        "domain": "",
                        "register": "",
                        "confidence": "0.900",
                        "is_primary": "true" if sense.get("senseId") in ("1", "1.0") else "false",
                        "review_status": "unreviewed",
                        "raw_payload": raw_json(
                            {
                                "entry_id": external_entry_id,
                                "provenance": sense.get("provenance") or "",
                                "annotator": sense.get("annotator") or "",
                            }
                        ),
                    }
                )
                for ex_index, ex in enumerate(sense.findall(".//SenseExample"), start=1):
                    text = clean_text(ex.get("definition") or "".join(ex.itertext()))
                    if not text:
                        continue
                    examples.append(
                        {
                            "sense_source_key": "odwn_1_3",
                            "sense_external_id": external_id,
                            "ex_nl": text,
                            "source_key": "odwn_1_3",
                            "external_id": f"{external_id}:example:{ex_index}",
                            "quality_score": "0.700",
                            "raw_payload": raw_json({"entry_id": external_entry_id}),
                        }
                    )
            entry.clear()
    return senses, examples


def iter_ttl_blocks(path: Path) -> Iterable[str]:
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        block: list[str] = []
        for line in handle:
            if line.startswith("@prefix"):
                continue
            if not line.strip() and not block:
                continue
            block.append(line)
            if line.strip().endswith("."):
                text = "".join(block)
                block.clear()
                if text.strip():
                    yield text
        if block:
            yield "".join(block)


def regex_text(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.S)
    return clean_text(match.group(1)) if match else ""


def parse_dbnary(
    path: Path,
    target_lemmas: set[str],
    pos_entries: dict[tuple[str, str], dict[str, object]],
    forms: dict[tuple[str, str, str, str], dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    entry_by_sense: dict[str, dict[str, str]] = {}
    for block in iter_ttl_blocks(path):
        if "ontolex:LexicalEntry" not in block or "rdfs:label" not in block:
            continue
        subject = block.split(None, 1)[0]
        label = regex_text(r'rdfs:label\s+"((?:\\"|[^"])*)"\@nl', block)
        lemma_norm = norm(label)
        if lemma_norm not in target_lemmas:
            continue
        pos_raw = regex_text(r'dbnary:partOfSpeech\s+"([^"]+)"', block)
        if not pos_raw:
            pos_match = re.search(r"__([A-Za-z0-9]+)__\d+", subject)
            pos_raw = pos_match.group(1) if pos_match else ""
        pos = map_dbnary_pos(pos_raw)
        entry_id = subject.removeprefix("nld:")
        add_pos_entry(pos_entries, lemma_norm, pos, "dbnary_nld_2026_05", 0.850, external_entry_id=entry_id)
        add_form(
            forms,
            lemma_norm,
            pos,
            label,
            "canonical",
            "dbnary_nld_2026_05",
            f"dbnary-form:{entry_id}:canonical",
            True,
            0.850,
            {"entry_id": entry_id, "part_of_speech": pos_raw},
        )
        sense_segment = re.search(r"ontolex:sense\s+(.+?)\s*\.", block, flags=re.S)
        if not sense_segment:
            continue
        for sense_ref in re.findall(r"nld:([A-Za-z0-9_.$%+-]+)", sense_segment.group(1)):
            entry_by_sense[sense_ref] = {
                "lemma_norm": lemma_norm,
                "pos": pos,
                "entry_id": entry_id,
                "pos_raw": pos_raw,
            }

    senses: list[dict[str, object]] = []
    examples: list[dict[str, object]] = []
    for block in iter_ttl_blocks(path):
        if "ontolex:LexicalSense" not in block:
            continue
        subject = block.split(None, 1)[0].removeprefix("nld:")
        entry = entry_by_sense.get(subject)
        if entry is None:
            continue
        sense_no = regex_text(r'dbnary:senseNumber\s+"([^"]+)"', block)
        definitions = re.findall(r'skos:definition\s+\[\s*rdf:value\s+"((?:\\"|[^"])*)"\@nl\s*\]', block, flags=re.S)
        definition = clean_text(definitions[0]) if definitions else ""
        senses.append(
            {
                "lemma_norm": entry["lemma_norm"],
                "pos": entry["pos"],
                "source_key": "dbnary_nld_2026_05",
                "external_id": subject,
                "external_synset_id": "",
                "sense_no": sense_no,
                "definition_nl": definition,
                "usage_note": "",
                "domain": "",
                "register": "",
                "confidence": "0.850",
                "is_primary": "true" if sense_no in ("1", "1.0") else "false",
                "review_status": "unreviewed",
                "raw_payload": raw_json({"entry_id": entry["entry_id"], "pos_raw": entry["pos_raw"]}),
            }
        )
        for ex_index, ex in enumerate(
            re.findall(r'skos:example\s+\[\s*rdf:value\s+"((?:\\"|[^"])*)"\@nl\s*\]', block, flags=re.S),
            start=1,
        ):
            examples.append(
                {
                    "sense_source_key": "dbnary_nld_2026_05",
                    "sense_external_id": subject,
                    "ex_nl": clean_text(ex),
                    "source_key": "dbnary_nld_2026_05",
                    "external_id": f"{subject}:example:{ex_index}",
                    "quality_score": "0.750",
                    "raw_payload": raw_json({}),
                }
            )
    return senses, examples


def build_import(output_dir: Path) -> dict[str, int]:
    vocab_rows, vocab_by_norm = load_vocab(VOCAB_PATH)
    target_lemmas = set(vocab_by_norm)
    pos_entries: dict[tuple[str, str], dict[str, object]] = {}
    forms: dict[tuple[str, str, str, str], dict[str, object]] = {}

    lemma_rows = []
    lemma_stats_rows = []
    for row in vocab_rows:
        lemma_rows.append(
            {
                "lemma": row["lemma"],
                "lemma_norm": row["lemma_norm"],
                "display_lemma": row["lemma"],
                "level": row["level"],
                "word_family": row.get("family") or "",
                "is_academic": "true" if row.get("is_academic") else "false",
                "academic_source": row.get("academic_source") or "",
                "subtlex_freq": row.get("sub_freq") or 0,
                "subtlex_form_count": row.get("sub_forms") or 0,
                "cc100_freq": row.get("cc_freq") or 0,
                "cc100_form_count": row.get("cc_forms") or 0,
                "popularity": row.get("sub_freq") or 0,
            }
        )
        lemma_stats_rows.append(
            {
                "lemma_norm": row["lemma_norm"],
                "corpus_key": "subtlex_nl",
                "freq_count": row.get("sub_freq") or 0,
                "form_count": row.get("sub_forms") or 0,
                "rank": "",
                "coverage": "",
                "metadata": raw_json({}),
            }
        )
        lemma_stats_rows.append(
            {
                "lemma_norm": row["lemma_norm"],
                "corpus_key": "cc100_nl_local_20260525",
                "freq_count": row.get("cc_freq") or 0,
                "form_count": row.get("cc_forms") or 0,
                "rank": "",
                "coverage": "",
                "metadata": raw_json({}),
            }
        )

    curated_rows = load_curated_form_levels(FORM_LEVELS_PATH)
    subtlex_form_stats = scan_subtlex(SUBTLEX_PATH, target_lemmas, pos_entries, forms)
    odwn_senses, odwn_examples = parse_odwn(ODWN_PATH, target_lemmas, pos_entries, forms)
    dbnary_senses, dbnary_examples = parse_dbnary(DBNARY_PATH, target_lemmas, pos_entries, forms)
    sense_rows = odwn_senses + dbnary_senses
    example_rows = odwn_examples + dbnary_examples

    all_pos_tags = {row["pos"] for row in pos_entries.values()}
    pos_tag_rows = [pos_tag_row(tag, "import") for tag in sorted(all_pos_tags)]

    files = {
        "lemmas.tsv": (
            [
                "lemma",
                "lemma_norm",
                "display_lemma",
                "level",
                "word_family",
                "is_academic",
                "academic_source",
                "subtlex_freq",
                "subtlex_form_count",
                "cc100_freq",
                "cc100_form_count",
                "popularity",
            ],
            lemma_rows,
        ),
        "lemma_corpus_stats.tsv": (
            ["lemma_norm", "corpus_key", "freq_count", "form_count", "rank", "coverage", "metadata"],
            lemma_stats_rows,
        ),
        "curated_form_levels.tsv": (
            ["form", "form_norm", "level", "source_name", "note", "raw_payload"],
            curated_rows,
        ),
        "pos_tags_extra.tsv": (
            ["tag", "english", "dutch", "description_zh", "example", "sort_order"],
            pos_tag_rows,
        ),
        "lemma_pos_entries.tsv": (
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
            sorted(pos_entries.values(), key=lambda item: (item["lemma_norm"], item["pos"])),
        ),
        "forms.tsv": (
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
            sorted(forms.values(), key=lambda item: (item["lemma_norm"], item["pos"], item["form_norm"], item["form_type"])),
        ),
        "form_corpus_stats.tsv": (
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
            subtlex_form_stats,
        ),
        "senses.tsv": (
            [
                "lemma_norm",
                "pos",
                "source_key",
                "external_id",
                "external_synset_id",
                "sense_no",
                "definition_nl",
                "usage_note",
                "domain",
                "register",
                "confidence",
                "is_primary",
                "review_status",
                "raw_payload",
            ],
            sense_rows,
        ),
        "examples.tsv": (
            [
                "sense_source_key",
                "sense_external_id",
                "ex_nl",
                "source_key",
                "external_id",
                "quality_score",
                "raw_payload",
            ],
            example_rows,
        ),
    }

    counts: dict[str, int] = {}
    for filename, (headers, rows) in files.items():
        counts[filename] = write_tsv(output_dir / filename, headers, rows)
    (output_dir / "build_metadata.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "target_lemmas": len(target_lemmas),
                "counts": counts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    counts = build_import(output_dir)
    print(f"Wrote import files to {output_dir}")
    for key in sorted(counts):
        print(f"{key}\t{counts[key]}")


if __name__ == "__main__":
    main()
