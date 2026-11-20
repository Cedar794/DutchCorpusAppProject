#!/usr/bin/env python3
"""Export non-empty Dutch senses into JSONL chunks for LLM translation."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "app_enrichment" / "translation_jobs"


def run_psql_csv(container: str, sql: str) -> list[dict[str, str]]:
    command = [
        "docker",
        "exec",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-c",
        f"copy ({sql}) to stdout with csv header",
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    return list(csv.DictReader(result.stdout.splitlines()))


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_query(limit: int | None) -> str:
    limit_clause = f"\nlimit {limit}" if limit else ""
    return f"""
select
  s.id::text as sense_id,
  l.lemma_norm,
  l.level::text as level,
  p.pos,
  coalesce(pt.app_pos, 'unknown') as app_pos,
  coalesce(s.sense_no, '') as sense_no,
  coalesce(s.display_definition_nl, nullif(btrim(s.definition_nl), '')) as definition_nl,
  src.source_key as source_key,
  coalesce(src.license, '') as source_license,
  coalesce(src.license_url, '') as source_license_url
from public.senses s
join public.lemmas l on l.id = s.lemma_id
left join public.lemma_pos_entries p on p.id = s.lemma_pos_entry_id
left join public.pos_tags pt on pt.tag = p.pos
join public.sources src on src.id = s.source_id
where coalesce(s.display_definition_nl, nullif(btrim(s.definition_nl), '')) is not null
  and s.merged_into_sense_id is null
  and not (
    exists (
      select 1
      from public.sense_translations t
      join public.sources tsrc on tsrc.id = t.source_id
      where t.sense_id = s.id
        and t.lang = 'zh'
        and tsrc.source_key = 'llm_sense_translation_v1'
    )
    and exists (
      select 1
      from public.sense_translations t
      join public.sources tsrc on tsrc.id = t.source_id
      where t.sense_id = s.id
        and t.lang = 'en'
        and tsrc.source_key = 'llm_sense_translation_v1'
    )
  )
order by l.level, l.lemma_norm, coalesce(pt.display_order, 999), s.app_sense_order nulls last, s.id
{limit_clause}
""".strip()


def make_payload(row: dict[str, str]) -> dict[str, object]:
    return {
        "sense_id": int(row["sense_id"]),
        "lemma_norm": row["lemma_norm"],
        "level": int(row["level"]),
        "pos": row["pos"],
        "app_pos": row["app_pos"],
        "sense_no": row["sense_no"],
        "definition_nl": row["definition_nl"],
        "source": {
            "source_key": row["source_key"],
            "license": row["source_license"],
            "license_url": row["source_license_url"],
        },
    }


def write_prompt(path: Path) -> None:
    path.write_text(
        """# Dutch Sense Translation Job

Translate each JSONL input record into Chinese and English learner-dictionary text.

Return one JSON object per input record, also as JSONL:

```json
{"sense_id": 123, "translations": {"zh": {"gloss": "简短中文词义", "explanation": "面向学习者的中文解释。"}, "en": {"gloss": "short English gloss", "explanation": "Learner-friendly English explanation."}}}
```

Rules:
- Preserve `sense_id` exactly.
- Use the Dutch `definition_nl` as the only semantic source. Do not invent details not implied by it.
- Preserve the specified part of speech and distinguish reflexive, possessive, auxiliary and lexical uses.
- Translate the complete core meaning. A concise gloss must never be truncated to satisfy a word count.
- Grammar labels such as ergatief, overgankelijk and absoluut are not the lexical meaning. Explain them separately where relevant; intransitivity is not inseparability.
- Use natural target-language wording, not copied Dutch fragments. Quoted Dutch constructions may be retained with an explanation.
- Do not include subtitle codes, template parameters, source sense numbers or internal repair instructions.
- If the source is incomplete or contradictory and cannot support a translation, emit {"sense_id": 123, "needs_source_review": true, "reason": "..."} instead of inventing a meaning. This record will be quarantined by validation.
- Similar translations do not authorize merging senses across part of speech, register, domain or construction.
- `zh.gloss` should be concise Simplified Chinese, usually 1-8 Chinese words.
- `zh.explanation` should be natural Simplified Chinese, one short sentence.
- `en.gloss` should be concise English, usually 1-8 words.
- `en.explanation` should be simple learner-friendly English, one short sentence.
- If the source definition is vague, keep the translation broad rather than over-specific.
- Output valid JSONL only, no Markdown, no comments.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="supabase_db_dutch-corpus-database")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chunk-size", type=int, default=250)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = [make_payload(row) for row in run_psql_csv(args.container, build_query(args.limit))]
    write_prompt(args.output_dir / "translation_prompt.md")
    write_jsonl(args.output_dir / "senses_to_translate.jsonl", rows)

    chunks_dir = args.output_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunk_paths = []
    for index in range(0, len(rows), args.chunk_size):
        chunk_no = index // args.chunk_size + 1
        chunk = rows[index : index + args.chunk_size]
        chunk_path = chunks_dir / f"chunk_{chunk_no:05d}.jsonl"
        write_jsonl(chunk_path, chunk)
        chunk_paths.append(str(chunk_path.relative_to(ROOT)))

    manifest = {
        "total_senses": len(rows),
        "chunk_size": args.chunk_size,
        "chunk_count": len(chunk_paths),
        "chunks": chunk_paths,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
