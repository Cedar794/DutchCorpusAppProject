\set ON_ERROR_STOP on

drop table if exists tmp_aigc_backlog_p0;
create temp table tmp_aigc_backlog_p0 as
select
  'P0' as priority,
  'missing_definition_existing_sense' as task_type,
  s.id as sense_id,
  src.source_key as target_source_key,
  s.external_id as target_external_id,
  s.external_synset_id,
  s.sense_no,
  l.id as lemma_id,
  l.lemma_norm,
  l.display_lemma,
  l.level,
  l.popularity,
  l.is_academic,
  l.academic_source,
  p.id as lemma_pos_entry_id,
  p.pos,
  s.app_sense_order,
  s.is_core,
  s.confidence,
  s.review_status,
  s.raw_payload
from public.senses s
join public.lemmas l on l.id = s.lemma_id
left join public.lemma_pos_entries p on p.id = s.lemma_pos_entry_id
join public.sources src on src.id = s.source_id
where coalesce(btrim(s.definition_nl), '') = ''
order by
  l.level,
  l.is_academic desc,
  l.popularity desc nulls last,
  l.lemma_norm,
  p.pos nulls last,
  s.id;

\copy tmp_aigc_backlog_p0 to '/tmp/dutch_lexicon_import/aigc_full_backlog_v1/p0_missing_definitions.tsv' with (format csv, delimiter E'\t', header true)

drop table if exists tmp_aigc_backlog_p1;
create temp table tmp_aigc_backlog_p1 as
with lemma_sense_counts as (
  select l.id, count(s.id) as sense_count
  from public.lemmas l
  left join public.senses s on s.lemma_id = l.id
  group by l.id
),
pos_summary as (
  select
    lemma_id,
    string_agg(pos, ',' order by pos) as observed_pos_tags,
    bool_or(pos in ('N', 'NOUN', 'WW', 'VERB', 'ADJ', 'BW', 'ADV')) as has_content_pos
  from public.lemma_pos_entries
  group by lemma_id
)
select
  'P1' as priority,
  'new_sense_for_senseless_lemma' as task_type,
  l.id as lemma_id,
  l.lemma_norm,
  l.display_lemma,
  l.level,
  l.word_family,
  l.is_academic,
  l.academic_source,
  l.popularity,
  coalesce(ps.observed_pos_tags, '') as observed_pos_tags,
  coalesce(ps.has_content_pos, false) as has_content_pos
from public.lemmas l
join lemma_sense_counts c on c.id = l.id
left join pos_summary ps on ps.lemma_id = l.id
where c.sense_count = 0
order by
  l.level,
  l.is_academic desc,
  l.popularity desc nulls last,
  l.lemma_norm;

\copy tmp_aigc_backlog_p1 to '/tmp/dutch_lexicon_import/aigc_full_backlog_v1/p1_senseless_lemmas.tsv' with (format csv, delimiter E'\t', header true)

drop table if exists tmp_aigc_backlog_p2;
create temp table tmp_aigc_backlog_p2 as
select
  'P2' as priority,
  'missing_zh_translation' as task_type,
  s.id as sense_id,
  src.source_key as target_source_key,
  s.external_id as target_external_id,
  s.external_synset_id,
  s.sense_no,
  l.id as lemma_id,
  l.lemma_norm,
  l.display_lemma,
  l.level,
  l.popularity,
  p.id as lemma_pos_entry_id,
  p.pos,
  s.definition_nl,
  s.usage_note,
  s.app_sense_order,
  s.is_core
from public.senses s
join public.lemmas l on l.id = s.lemma_id
left join public.lemma_pos_entries p on p.id = s.lemma_pos_entry_id
join public.sources src on src.id = s.source_id
where not exists (
  select 1 from public.sense_translations t
  where t.sense_id = s.id and t.lang = 'zh'
)
order by
  l.level,
  case when coalesce(btrim(s.definition_nl), '') = '' then 1 else 0 end,
  l.popularity desc nulls last,
  l.lemma_norm,
  s.id;

\copy tmp_aigc_backlog_p2 to '/tmp/dutch_lexicon_import/aigc_full_backlog_v1/p2_missing_zh_translations.tsv' with (format csv, delimiter E'\t', header true)

drop table if exists tmp_aigc_backlog_p3;
create temp table tmp_aigc_backlog_p3 as
select
  'P3' as priority,
  'missing_sense_example' as task_type,
  s.id as sense_id,
  src.source_key as target_source_key,
  s.external_id as target_external_id,
  s.external_synset_id,
  s.sense_no,
  l.id as lemma_id,
  l.lemma_norm,
  l.display_lemma,
  l.level,
  l.popularity,
  p.id as lemma_pos_entry_id,
  p.pos,
  s.definition_nl,
  s.usage_note,
  s.app_sense_order,
  s.is_core
from public.senses s
join public.lemmas l on l.id = s.lemma_id
left join public.lemma_pos_entries p on p.id = s.lemma_pos_entry_id
join public.sources src on src.id = s.source_id
where not exists (
  select 1 from public.examples e
  where e.sense_id = s.id
)
order by
  l.level,
  case when coalesce(btrim(s.definition_nl), '') = '' then 1 else 0 end,
  l.popularity desc nulls last,
  l.lemma_norm,
  s.id;

\copy tmp_aigc_backlog_p3 to '/tmp/dutch_lexicon_import/aigc_full_backlog_v1/p3_missing_sense_examples.tsv' with (format csv, delimiter E'\t', header true)

drop table if exists tmp_aigc_backlog_p4;
create temp table tmp_aigc_backlog_p4 as
select
  'P4' as priority,
  'missing_example_zh_translation' as task_type,
  e.id as example_id,
  ex_src.source_key as example_source_key,
  e.external_id as example_external_id,
  e.ex_nl,
  s.id as sense_id,
  sense_src.source_key as target_source_key,
  s.external_id as target_external_id,
  l.id as lemma_id,
  l.lemma_norm,
  l.display_lemma,
  l.level,
  p.pos,
  s.definition_nl
from public.examples e
join public.senses s on s.id = e.sense_id
join public.lemmas l on l.id = s.lemma_id
left join public.lemma_pos_entries p on p.id = s.lemma_pos_entry_id
left join public.sources ex_src on ex_src.id = e.source_id
join public.sources sense_src on sense_src.id = s.source_id
where not exists (
  select 1 from public.example_translations et
  where et.example_id = e.id and et.lang = 'zh'
)
order by
  l.level,
  l.popularity desc nulls last,
  l.lemma_norm,
  e.id;

\copy tmp_aigc_backlog_p4 to '/tmp/dutch_lexicon_import/aigc_full_backlog_v1/p4_missing_example_zh_translations.tsv' with (format csv, delimiter E'\t', header true)

select 'p0_missing_definitions' as backlog, count(*) as rows from tmp_aigc_backlog_p0
union all select 'p1_senseless_lemmas', count(*) from tmp_aigc_backlog_p1
union all select 'p2_missing_zh_translations', count(*) from tmp_aigc_backlog_p2
union all select 'p3_missing_sense_examples', count(*) from tmp_aigc_backlog_p3
union all select 'p4_missing_example_zh_translations', count(*) from tmp_aigc_backlog_p4
order by backlog;
