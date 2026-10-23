#!/usr/bin/env python3
"""Build small subagent work chunks from the AIGC replacement queues."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = ROOT / "outputs" / "aigc_agent_replacement_v1"
QUEUE_DIR = BASE_DIR / "queue"
CHUNK_DIR = BASE_DIR / "chunks"
MARKER = "#aigc"


SENSE_OUTPUT_FIELDS = [
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

EXAMPLE_OUTPUT_FIELDS = [
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


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def chunk_rows(rows: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def instructions(kind: str, chunk_id: str, input_file: str, output_file: str, rows: int) -> str:
    if kind == "sense":
        output_fields = "\t".join(SENSE_OUTPUT_FIELDS)
        content_rules = """
For each input row, generate one output row with these columns:

batch_id, sense_id, translation_id, example_id, example_translation_id, lemma_norm, pos, definition_nl, usage_note, gloss_zh, explanation_zh, ex_nl, ex_zh, confidence, quality_note

Rules:
- Preserve IDs exactly from the input.
- batch_id must be exactly `{chunk_id}` for every output row.
- If replace_definition is false, still write a concise best definition_nl for audit, but the loader will not overwrite that field.
- If replace_translation is false, still write a best gloss_zh/explanation_zh for audit.
- If replace_example is false, still write a natural example for audit.
- Every generated natural-language value must end literally with #aigc: definition_nl, usage_note, gloss_zh, explanation_zh, ex_nl, ex_zh, quality_note.
- Do not append #aigc to IDs, pos, confidence, or batch_id.
- No tabs or newlines inside fields.
- definition_nl must be Dutch, concise, dictionary-style, and specific to the given sense.
- usage_note must be Dutch and mention uncertainty only when the synset/lemma evidence is weak or conflicting.
- gloss_zh must be natural Chinese, not a placeholder and not only a transliteration unless the item is a proper name/abbreviation.
- explanation_zh must explain the sense boundary for learners.
- ex_nl must be a natural Dutch sentence using the lemma/form appropriately; avoid "Dit voorbeeld gaat over..." and avoid meta-sentences.
- ex_zh must be a real Chinese translation of ex_nl, not an explanation about the example.
- If WordNet/OMW evidence looks mismatched to the Dutch lemma, write a conservative definition and mark the quality_note as "义项证据疑似错配，需人工复核#aigc".
- confidence should be 0.70-0.88 for good evidence, 0.45-0.65 for weak/conflicting evidence.
"""
    else:
        output_fields = "\t".join(EXAMPLE_OUTPUT_FIELDS)
        content_rules = """
For each input row, generate one output row with these columns:

batch_id, translation_id, example_id, sense_id, lemma_norm, pos, translation_zh, confidence, quality_note

Rules:
- Preserve IDs exactly from the input.
- batch_id must be exactly `{chunk_id}` for every output row.
- translation_zh must be a real Chinese translation of ex_nl, not an explanation about what the sentence expresses.
- Every generated natural-language value must end literally with #aigc: translation_zh and quality_note.
- Do not append #aigc to IDs, pos, confidence, or batch_id.
- No tabs or newlines inside fields.
- Preserve the sense in definition_nl when translating ambiguous examples.
- confidence should be 0.75-0.92 for straightforward examples, 0.55-0.70 for awkward or uncertain examples.
"""
    return f"""# AIGC Lexicon Replacement Chunk

Chunk: `{chunk_id}`
Kind: `{kind}`
Rows: {rows}
Input file: `{input_file}`
Output file: `{output_file}`

You are a subagent generating high-quality Dutch lexicon replacement data. This replaces low-quality script drafts in the full database.

Read the TSV input file, then write exactly one TSV output file at the output path above. The first row must be the header exactly:

```tsv
{output_fields}
```

{content_rules}

Quality bar:
- Prefer ordinary modern Dutch.
- Keep dictionary definitions short and concrete.
- Keep examples safe, neutral, and plausible.
- Use the supplied WordNet/OMW data as evidence, but do not blindly trust it.
- Treat previous draft fields as bad examples unless they are clearly useful.
- Output must be complete for all {rows} input rows.
"""


def make_chunks(kind: str, rows: list[dict[str, str]], size: int, fields: list[str]) -> list[dict[str, str]]:
    chunks = []
    for index, subset in enumerate(chunk_rows(rows, size), start=1):
        chunk_id = f"{kind}_{index:05d}"
        chunk_path = CHUNK_DIR / kind / chunk_id
        input_path = chunk_path / "input.tsv"
        output_path = chunk_path / "output.tsv"
        instruction_path = chunk_path / "instructions.md"
        write_tsv(input_path, subset, fields)
        instruction_path.write_text(
            instructions(kind, chunk_id, str(input_path), str(output_path), len(subset)),
            encoding="utf-8",
        )
        chunks.append(
            {
                "chunk_id": chunk_id,
                "kind": kind,
                "rows": len(subset),
                "input": str(input_path),
                "output": str(output_path),
                "instructions": str(instruction_path),
                "status": "pending",
            }
        )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sense-size", type=int, default=20)
    parser.add_argument("--example-size", type=int, default=80)
    args = parser.parse_args()

    sense_fields = next(csv.DictReader((QUEUE_DIR / "sense_replacement_queue.tsv").open(encoding="utf-8"), delimiter="\t")).keys()
    example_fields = next(csv.DictReader((QUEUE_DIR / "example_translation_replacement_queue.tsv").open(encoding="utf-8"), delimiter="\t")).keys()
    sense_rows = read_tsv(QUEUE_DIR / "sense_replacement_queue.tsv")
    example_rows = read_tsv(QUEUE_DIR / "example_translation_replacement_queue.tsv")

    chunks = []
    chunks.extend(make_chunks("sense", sense_rows, args.sense_size, list(sense_fields)))
    chunks.extend(make_chunks("example_translation", example_rows, args.example_size, list(example_fields)))

    manifest = {
        "marker": MARKER,
        "sense_rows": len(sense_rows),
        "example_translation_rows": len(example_rows),
        "sense_chunk_size": args.sense_size,
        "example_translation_chunk_size": args.example_size,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "chunk_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in manifest if k != "chunks"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
