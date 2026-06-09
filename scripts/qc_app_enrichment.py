#!/usr/bin/env python3
"""Write a compact QC report for Dutch lexicon app enrichment."""

from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "app_enrichment" / "reports" / "app_enrichment_qc.md"


QUERIES = {
    "table_counts": """
select 'lemmas' as metric, count(*)::text as value from public.lemmas
union all select 'lemma_pos_entries', count(*)::text from public.lemma_pos_entries
union all select 'forms', count(*)::text from public.forms
union all select 'senses', count(*)::text from public.senses
union all select 'sense_translations', count(*)::text from public.sense_translations
union all select 'lemma_examples', count(*)::text from public.lemma_examples
union all select 'lemma_relations', count(*)::text from public.lemma_relations
union all select 'sense_relations', count(*)::text from public.sense_relations
""",
    "coverage": """
with eligible as (
    select id
    from public.senses
    where merged_into_sense_id is null
      and coalesce(display_definition_nl, nullif(btrim(definition_nl), '')) is not null
),
llm as (
    select t.sense_id, t.lang
    from public.sense_translations t
    join public.sources src on src.id=t.source_id
    where src.source_key='llm_sense_translation_v1'
)
select 'pos_without_app_pos' as metric, count(*)::text as value from public.pos_tags where app_pos is null
union all select 'forms_without_app_role', count(*)::text from public.forms where app_form_role is null
union all select 'non_merged_senses_without_order', count(*)::text from public.senses where merged_into_sense_id is null and app_sense_order is null
union all select 'eligible_senses_for_translation', count(*)::text from eligible
union all select 'eligible_senses_with_zh_translation', count(distinct l.sense_id)::text from eligible e join llm l on l.sense_id=e.id and l.lang='zh'
union all select 'eligible_senses_with_en_translation', count(distinct l.sense_id)::text from eligible e join llm l on l.sense_id=e.id and l.lang='en'
union all select 'eligible_senses_missing_zh_translation', count(*)::text from eligible e where not exists (select 1 from llm l where l.sense_id=e.id and l.lang='zh')
union all select 'eligible_senses_missing_en_translation', count(*)::text from eligible e where not exists (select 1 from llm l where l.sense_id=e.id and l.lang='en')
union all select 'eligible_senses_with_both_translations', count(*)::text from eligible e where exists (select 1 from llm l where l.sense_id=e.id and l.lang='zh') and exists (select 1 from llm l where l.sense_id=e.id and l.lang='en')
union all select 'llm_translation_rows', count(*)::text from llm
union all select 'empty_definition_senses', count(*)::text from public.senses where definition_nl is null or btrim(definition_nl) = ''
""",
    "pos_distribution": """
select coalesce(app_pos, 'NULL') as metric, count(*)::text as value
from public.pos_tags
group by app_pos
order by app_pos
""",
    "relations": """
select relation_type as metric, count(*)::text as value
from public.lemma_relations
group by relation_type
union all
select 'sense:' || relation_type, count(*)::text
from public.sense_relations
group by relation_type
order by metric
""",
}


def run_query(container: str, sql: str) -> list[dict[str, str]]:
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


def table(rows: list[dict[str, str]]) -> str:
    lines = ["| Metric | Value |", "|---|---:|"]
    for row in rows:
        lines.append(f"| `{row['metric']}` | {row['value']} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="supabase_db_dutch-corpus-database")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sections = ["# Dutch Lexicon App Enrichment QC", ""]
    for title, sql in QUERIES.items():
        rows = run_query(args.container, sql.strip())
        sections.extend([f"## {title.replace('_', ' ').title()}", "", table(rows), ""])
    args.output.write_text("\n".join(sections), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
