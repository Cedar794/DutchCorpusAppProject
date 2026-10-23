\set ON_ERROR_STOP on

select 'lemmas' as table_name, count(*) as rows from public.lemmas
union all select 'lemma_pos_entries', count(*) from public.lemma_pos_entries
union all select 'forms', count(*) from public.forms
union all select 'senses', count(*) from public.senses
union all select 'sense_translations', count(*) from public.sense_translations
union all select 'examples', count(*) from public.examples
union all select 'example_translations', count(*) from public.example_translations
union all select 'lemma_examples', count(*) from public.lemma_examples
union all select 'lemma_relations', count(*) from public.lemma_relations
union all select 'sense_relations', count(*) from public.sense_relations
order by table_name;

select 'odwn_empty_definitions_remaining' as metric, count(*) as value
from public.senses se
join public.sources src on src.id = se.source_id
where src.source_key = 'odwn_1_3'
  and coalesce(btrim(se.definition_nl), '') = ''
union all
select 'p0_aigc_definition_updates', count(*)
from public.senses
where raw_payload ? 'aigc_completion_v1'
union all
select 'p1_aigc_inserted_senses', count(*)
from public.senses se
join public.sources src on src.id = se.source_id
where src.source_key = 'aigc_missing_definition_v1'
union all
select 'aigc_sense_translations', count(*)
from public.sense_translations st
join public.sources src on src.id = st.source_id
where src.source_key = 'aigc_sense_translation_v2'
union all
select 'aigc_examples', count(*)
from public.examples e
join public.sources src on src.id = e.source_id
where src.source_key = 'aigc_examples_v1'
union all
select 'aigc_example_translations', count(*)
from public.example_translations et
join public.sources src on src.id = et.source_id
where src.source_key = 'aigc_example_translation_v1'
union all
select 'aigc_lemma_relations', count(*)
from public.lemma_relations lr
join public.sources src on src.id = lr.source_id
where src.source_key = 'aigc_relations_v1'
order by metric;

with missing_marker as (
  select 'senses_p0_update' tbl, id::text row_id, 'definition_nl' col, definition_nl val
  from public.senses
  where raw_payload ? 'aigc_completion_v1'
    and coalesce(definition_nl, '') !~ '#aigc\s*$'
  union all
  select 'senses_p0_update', id::text, 'usage_note', usage_note
  from public.senses
  where raw_payload ? 'aigc_completion_v1'
    and coalesce(usage_note, '') <> ''
    and usage_note !~ '#aigc\s*$'
  union all
  select 'senses_p1_aigc', se.id::text, 'definition_nl', se.definition_nl
  from public.senses se
  join public.sources src on src.id = se.source_id
  where src.source_key = 'aigc_missing_definition_v1'
    and coalesce(se.definition_nl, '') !~ '#aigc\s*$'
  union all
  select 'senses_p1_aigc', se.id::text, 'usage_note', se.usage_note
  from public.senses se
  join public.sources src on src.id = se.source_id
  where src.source_key = 'aigc_missing_definition_v1'
    and coalesce(se.usage_note, '') <> ''
    and se.usage_note !~ '#aigc\s*$'
  union all
  select 'sense_translations', st.id::text, 'gloss', st.gloss
  from public.sense_translations st
  join public.sources src on src.id = st.source_id
  where src.source_key = 'aigc_sense_translation_v2'
    and st.gloss !~ '#aigc\s*$'
  union all
  select 'sense_translations', st.id::text, 'explanation', st.explanation
  from public.sense_translations st
  join public.sources src on src.id = st.source_id
  where src.source_key = 'aigc_sense_translation_v2'
    and coalesce(st.explanation, '') !~ '#aigc\s*$'
  union all
  select 'examples', e.id::text, 'ex_nl', e.ex_nl
  from public.examples e
  join public.sources src on src.id = e.source_id
  where src.source_key = 'aigc_examples_v1'
    and e.ex_nl !~ '#aigc\s*$'
  union all
  select 'example_translations', et.id::text, 'translation', et.translation
  from public.example_translations et
  join public.sources src on src.id = et.source_id
  where src.source_key = 'aigc_example_translation_v1'
    and et.translation !~ '#aigc\s*$'
  union all
  select 'lemma_relations', lr.id::text, 'notes', lr.notes
  from public.lemma_relations lr
  join public.sources src on src.id = lr.source_id
  where src.source_key = 'aigc_relations_v1'
    and coalesce(lr.notes, '') !~ '#aigc\s*$'
  union all
  select 'aigc_relation_candidates', id::text, 'target_text_nl', target_text_nl
  from public.aigc_relation_candidates
  where batch_id = 'aigc_completion_v1'
    and coalesce(target_text_nl, '') <> ''
    and target_text_nl !~ '#aigc\s*$'
  union all
  select 'aigc_relation_candidates', id::text, 'notes', notes
  from public.aigc_relation_candidates
  where batch_id = 'aigc_completion_v1'
    and coalesce(notes, '') <> ''
    and notes !~ '#aigc\s*$'
),
forbidden_marker as (
  select 'sources' tbl, id::text row_id, 'source_key' col, source_key val
  from public.sources
  where source_key like '%#aigc%'
  union all
  select 'senses', id::text, 'external_id', external_id
  from public.senses
  where coalesce(external_id, '') like '%#aigc%'
  union all
  select 'sense_translations', id::text, 'translation_style', translation_style
  from public.sense_translations
  where coalesce(translation_style, '') like '%#aigc%'
  union all
  select 'sense_translations', id::text, 'lang', lang
  from public.sense_translations
  where lang like '%#aigc%'
  union all
  select 'lemma_relations', id::text, 'relation_type', relation_type
  from public.lemma_relations
  where relation_type like '%#aigc%'
)
select 'missing_marker' as issue, count(*) as rows from missing_marker
union all
select 'forbidden_marker', count(*) from forbidden_marker
order by issue;

select import_status, count(*) as rows
from public.aigc_new_sense_candidates
where batch_id = 'aigc_completion_v1'
group by import_status
order by import_status;

select import_status, count(*) as rows
from public.aigc_relation_candidates
where batch_id = 'aigc_completion_v1'
group by import_status
order by import_status;

select lemma_norm, requested_pos, pos as db_pos, import_status
from public.aigc_new_sense_candidates
where batch_id = 'aigc_completion_v1'
  and import_status <> 'inserted_sense'
order by lemma_norm;
