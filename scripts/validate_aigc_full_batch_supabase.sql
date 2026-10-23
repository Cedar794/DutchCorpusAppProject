\set ON_ERROR_STOP on

select item_type, count(*) as rows
from public.aigc_full_batch_imports
group by item_type
order by item_type;

select 'senses_missing_definition' as metric, count(*) as value
from public.senses
where coalesce(btrim(definition_nl), '') = ''
union all
select 'senses_missing_zh_translation', count(*)
from public.senses s
where not exists (
  select 1 from public.sense_translations t
  where t.sense_id = s.id and t.lang = 'zh'
)
union all
select 'senses_missing_examples', count(*)
from public.senses s
where not exists (
  select 1 from public.examples e
  where e.sense_id = s.id
)
union all
select 'examples_missing_zh_translation', count(*)
from public.examples e
where not exists (
  select 1 from public.example_translations et
  where et.example_id = e.id and et.lang = 'zh'
)
order by metric;

with missing_marker as (
  select 'senses_v2_definition' tbl, id::text row_id, 'definition_nl' col, definition_nl val
  from public.senses
  where raw_payload ? 'aigc_full_batch'
    and coalesce(definition_nl, '') !~ '#aigc\s*$'
  union all
  select 'senses_v2_definition', id::text, 'usage_note', usage_note
  from public.senses
  where raw_payload ? 'aigc_full_batch'
    and coalesce(usage_note, '') <> ''
    and usage_note !~ '#aigc\s*$'
  union all
  select 'sense_translations_v3', st.id::text, 'gloss', st.gloss
  from public.sense_translations st
  join public.sources src on src.id = st.source_id
  where src.source_key = 'aigc_sense_translation_v3'
    and st.gloss !~ '#aigc\s*$'
  union all
  select 'sense_translations_v3', st.id::text, 'explanation', st.explanation
  from public.sense_translations st
  join public.sources src on src.id = st.source_id
  where src.source_key = 'aigc_sense_translation_v3'
    and coalesce(st.explanation, '') !~ '#aigc\s*$'
  union all
  select 'sense_examples_v2', e.id::text, 'ex_nl', e.ex_nl
  from public.examples e
  join public.sources src on src.id = e.source_id
  where src.source_key = 'aigc_sense_examples_v2'
    and e.ex_nl !~ '#aigc\s*$'
  union all
  select 'example_translations_v2', et.id::text, 'translation', et.translation
  from public.example_translations et
  join public.sources src on src.id = et.source_id
  where src.source_key = 'aigc_example_translation_v2'
    and et.translation !~ '#aigc\s*$'
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
  select 'aigc_full_batch_imports', id::text, 'source_key', source_key
  from public.aigc_full_batch_imports
  where source_key like '%#aigc%'
)
select 'missing_marker' as issue, count(*) as rows from missing_marker
union all
select 'forbidden_marker', count(*) from forbidden_marker
order by issue;
