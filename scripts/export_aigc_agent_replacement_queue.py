#!/usr/bin/env python3
"""Export script-generated AIGC rows that must be replaced by subagents.

The previous bulk batches closed structural gaps with low-confidence templates.
This exporter builds auditable replacement queues with enough lexical context
for subagents to produce higher-quality drafts.
"""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs" / "aigc_agent_replacement_v1" / "queue"
DB_CONTAINER = "supabase_db_dutch-corpus-database"
MARKER = "#aigc"


SENSE_FIELDS = [
    "priority_rank",
    "sense_id",
    "lemma_id",
    "lemma_norm",
    "display_lemma",
    "level",
    "cefr_level",
    "cc100_freq",
    "subtlex_freq",
    "is_academic",
    "pos",
    "external_synset_id",
    "sense_source_key",
    "replace_definition",
    "replace_translation",
    "replace_example",
    "replace_example_translation",
    "p1_new_sense",
    "translation_id",
    "example_id",
    "example_translation_id",
    "current_definition_nl",
    "current_usage_note",
    "current_gloss_zh",
    "current_explanation_zh",
    "current_ex_nl",
    "current_ex_zh",
    "other_human_definitions_nl",
    "forms_summary",
    "corpus_examples_nl",
    "wordnet_definition_en",
    "wordnet_examples_en",
    "wordnet_lemmas_eng",
    "wordnet_lemmas_nld",
    "wordnet_lemmas_cmn",
]

EXAMPLE_TRANSLATION_FIELDS = [
    "priority_rank",
    "translation_id",
    "example_id",
    "sense_id",
    "lemma_id",
    "lemma_norm",
    "display_lemma",
    "level",
    "cefr_level",
    "cc100_freq",
    "subtlex_freq",
    "pos",
    "external_synset_id",
    "definition_nl",
    "usage_note",
    "gloss_zh",
    "explanation_zh",
    "ex_nl",
    "current_translation_zh",
    "other_human_definitions_nl",
    "wordnet_definition_en",
    "wordnet_examples_en",
    "wordnet_lemmas_eng",
    "wordnet_lemmas_nld",
    "wordnet_lemmas_cmn",
]


def run_copy(sql: str) -> list[dict[str, str]]:
    copy_sql = f"copy ({sql}) to stdout with (format csv, header true, delimiter E'\\t', quote E'\\b');"
    result = subprocess.run(
        ["docker", "exec", "-i", DB_CONTAINER, "psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", copy_sql],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return list(csv.DictReader(io.StringIO(result.stdout), delimiter="\t", quotechar="\b"))


def clean(value: Any, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\t", " ")).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


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


def lemma_names(synset: Any | None, lang: str) -> str:
    if not synset:
        return ""
    try:
        return "; ".join(clean(name.replace("_", " "), 80) for name in synset.lemma_names(lang=lang)[:12])
    except Exception:
        return ""


def enrich_wordnet(rows: list[dict[str, str]]) -> None:
    wn = load_wordnet()
    for row in rows:
        synset = synset_for(row.get("external_synset_id", ""), wn)
        row["wordnet_definition_en"] = clean(synset.definition(), 300) if synset else ""
        row["wordnet_examples_en"] = " || ".join(clean(x, 180) for x in (synset.examples()[:4] if synset else []))
        row["wordnet_lemmas_eng"] = lemma_names(synset, "eng")
        row["wordnet_lemmas_nld"] = lemma_names(synset, "nld")
        row["wordnet_lemmas_cmn"] = lemma_names(synset, "cmn")


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field, "")) for field in fields})


SENSE_QUEUE_SQL = r"""
with script_translation as (
  select
    t.id as translation_id,
    t.sense_id,
    t.gloss,
    t.explanation
  from public.sense_translations t
  join public.sources src on src.id = t.source_id
  where src.source_key = 'aigc_sense_translation_v3'
    and t.raw_payload->>'generator' in ('aigc_full_bulk_remaining_0002', 'aigc_p1_bulk_remaining_0003')
    and t.lang = 'zh'
),
script_example as (
  select
    e.id as example_id,
    e.sense_id,
    e.ex_nl,
    et.id as example_translation_id,
    et.translation as ex_zh
  from public.examples e
  join public.sources src on src.id = e.source_id
  left join public.example_translations et on et.example_id = e.id
  left join public.sources etsrc on etsrc.id = et.source_id
  where src.source_key = 'aigc_sense_examples_v2'
    and e.raw_payload->>'generator' in ('aigc_full_bulk_remaining_0002', 'aigc_p1_bulk_remaining_0003')
    and (et.id is null or etsrc.source_key = 'aigc_example_translation_v2')
),
script_definition as (
  select s.id as sense_id
  from public.senses s
  where s.raw_payload#>>'{aigc_full_batch,batch_id}' = 'aigc_full_bulk_remaining_0002'
),
p1_sense as (
  select s.id as sense_id
  from public.senses s
  join public.sources src on src.id = s.source_id
  where src.source_key = 'aigc_missing_sense_v2'
    and s.raw_payload->>'generator' = 'aigc_p1_bulk_remaining_0003'
),
target as (
  select sense_id, true as replace_definition, false as replace_translation, false as replace_example, false as p1_new_sense from script_definition
  union all
  select sense_id, false, true, false, false from script_translation
  union all
  select sense_id, false, false, true, false from script_example
  union all
  select sense_id, true, true, true, true from p1_sense
),
target_agg as (
  select
    sense_id,
    bool_or(replace_definition) as replace_definition,
    bool_or(replace_translation) as replace_translation,
    bool_or(replace_example) as replace_example,
    bool_or(p1_new_sense) as p1_new_sense
  from target
  group by sense_id
)
select
  row_number() over (order by l.level, l.cc100_freq desc nulls last, l.subtlex_freq desc nulls last, l.lemma_norm, s.id) as priority_rank,
  s.id as sense_id,
  l.id as lemma_id,
  l.lemma_norm,
  coalesce(l.display_lemma, l.lemma) as display_lemma,
  l.level,
  coalesce(l.cefr_level, '') as cefr_level,
  coalesce(l.cc100_freq, 0) as cc100_freq,
  coalesce(l.subtlex_freq, 0) as subtlex_freq,
  l.is_academic,
  coalesce(p.pos, '') as pos,
  coalesce(s.external_synset_id, '') as external_synset_id,
  src.source_key as sense_source_key,
  target_agg.replace_definition,
  target_agg.replace_translation,
  target_agg.replace_example,
  (se.example_translation_id is not null) as replace_example_translation,
  target_agg.p1_new_sense,
  coalesce(st.translation_id::text, '') as translation_id,
  coalesce(se.example_id::text, '') as example_id,
  coalesce(se.example_translation_id::text, '') as example_translation_id,
  coalesce(s.definition_nl, '') as current_definition_nl,
  coalesce(s.usage_note, '') as current_usage_note,
  coalesce(st.gloss, '') as current_gloss_zh,
  coalesce(st.explanation, '') as current_explanation_zh,
  coalesce(se.ex_nl, '') as current_ex_nl,
  coalesce(se.ex_zh, '') as current_ex_zh,
  coalesce(human_defs.items, '') as other_human_definitions_nl,
  coalesce(forms.items, '') as forms_summary,
  coalesce(corpus_examples.items, '') as corpus_examples_nl
from target_agg
join public.senses s on s.id = target_agg.sense_id
join public.lemmas l on l.id = s.lemma_id
left join public.lemma_pos_entries p on p.id = s.lemma_pos_entry_id
join public.sources src on src.id = s.source_id
left join script_translation st on st.sense_id = s.id
left join script_example se on se.sense_id = s.id
left join lateral (
  select string_agg(item, ' || ') as items
  from (
    select concat('[', coalesce(p2.pos, ''), '] ', regexp_replace(s2.definition_nl, '#aigc\s*$', '', 'g')) as item
    from public.senses s2
    left join public.lemma_pos_entries p2 on p2.id = s2.lemma_pos_entry_id
    where s2.lemma_id = s.lemma_id
      and s2.id <> s.id
      and coalesce(s2.definition_nl, '') <> ''
      and s2.definition_nl !~ '#aigc\s*$'
    order by s2.is_primary desc, s2.confidence desc, s2.id
    limit 8
  ) d
) human_defs on true
left join lateral (
  select string_agg(item, '; ') as items
  from (
    select concat(f.form, coalesce(' (' || nullif(f.form_type, '') || ')', '')) as item
    from public.forms f
    where f.lemma_id = l.id
    order by f.is_canonical desc, f.confidence desc, f.form
    limit 10
  ) d
) forms on true
left join lateral (
  select string_agg(ex_nl, ' || ') as items
  from (
    select le.ex_nl
    from public.lemma_examples le
    where le.lemma_id = l.id
      and le.ex_nl !~ '#aigc\s*$'
    order by le.quality_score desc nulls last, le.id
    limit 4
  ) d
) corpus_examples on true
order by priority_rank
"""


EXAMPLE_TRANSLATION_QUEUE_SQL = r"""
select
  row_number() over (order by l.level, l.cc100_freq desc nulls last, l.subtlex_freq desc nulls last, l.lemma_norm, e.id) as priority_rank,
  et.id as translation_id,
  e.id as example_id,
  s.id as sense_id,
  l.id as lemma_id,
  l.lemma_norm,
  coalesce(l.display_lemma, l.lemma) as display_lemma,
  l.level,
  coalesce(l.cefr_level, '') as cefr_level,
  coalesce(l.cc100_freq, 0) as cc100_freq,
  coalesce(l.subtlex_freq, 0) as subtlex_freq,
  coalesce(p.pos, '') as pos,
  coalesce(s.external_synset_id, '') as external_synset_id,
  coalesce(s.definition_nl, '') as definition_nl,
  coalesce(s.usage_note, '') as usage_note,
  '' as gloss_zh,
  '' as explanation_zh,
  e.ex_nl,
  et.translation as current_translation_zh,
  coalesce(human_defs.items, '') as other_human_definitions_nl
from public.example_translations et
join public.sources etsrc on etsrc.id = et.source_id
join public.examples e on e.id = et.example_id
left join public.sources esrc on esrc.id = e.source_id
join public.senses s on s.id = e.sense_id
join public.lemmas l on l.id = s.lemma_id
left join public.lemma_pos_entries p on p.id = s.lemma_pos_entry_id
left join lateral (
  select string_agg(item, ' || ') as items
  from (
    select concat('[', coalesce(p2.pos, ''), '] ', regexp_replace(s2.definition_nl, '#aigc\s*$', '', 'g')) as item
    from public.senses s2
    left join public.lemma_pos_entries p2 on p2.id = s2.lemma_pos_entry_id
    where s2.lemma_id = s.lemma_id
      and s2.definition_nl !~ '#aigc\s*$'
    order by s2.is_primary desc, s2.confidence desc, s2.id
    limit 8
  ) d
) human_defs on true
where etsrc.source_key = 'aigc_example_translation_v2'
  and et.external_id like 'aigc_full_bulk_remaining_0002_p4_extr_%'
order by priority_rank
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sense_rows = run_copy(SENSE_QUEUE_SQL)
    example_translation_rows = run_copy(EXAMPLE_TRANSLATION_QUEUE_SQL)
    enrich_wordnet(sense_rows)
    enrich_wordnet(example_translation_rows)

    write_tsv(OUTPUT_DIR / "sense_replacement_queue.tsv", sense_rows, SENSE_FIELDS)
    write_tsv(OUTPUT_DIR / "example_translation_replacement_queue.tsv", example_translation_rows, EXAMPLE_TRANSLATION_FIELDS)

    report = {
        "marker": MARKER,
        "sense_replacement_queue_rows": len(sense_rows),
        "example_translation_replacement_queue_rows": len(example_translation_rows),
        "output_dir": str(OUTPUT_DIR),
    }
    (OUTPUT_DIR / "queue_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
