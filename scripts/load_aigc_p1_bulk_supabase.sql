\set ON_ERROR_STOP on

\set batch_dir '/tmp/dutch_lexicon_import/aigc_p1_bulk'

begin;

insert into public.sources (source_key, name, source_type, version, notes)
values
  ('aigc_missing_sense_v2', 'AIGC senseless lemma completion v2', 'aigc_derived', '2026-06-14', 'Generated low-confidence senses for lemmas without any sense; generated natural-language fields carry #aigc markers.')
on conflict (source_key) do update
set name = excluded.name, source_type = excluded.source_type, version = excluded.version, notes = excluded.notes, updated_at = now();

create temp table stg_p1_new_senses (
  batch_id text,
  lemma_id text,
  lemma_norm text,
  display_lemma text,
  pos text,
  definition_nl text,
  usage_note text,
  confidence text,
  review_status text,
  source_key text,
  external_id text,
  raw_payload text
) on commit drop;

create temp table stg_p1_sense_translations (
  batch_id text,
  sense_external_id text,
  lemma_norm text,
  pos text,
  lang text,
  gloss text,
  explanation text,
  translation_style text,
  confidence text,
  review_status text,
  source_key text,
  external_id text,
  raw_payload text
) on commit drop;

create temp table stg_p1_sense_examples (
  batch_id text,
  sense_external_id text,
  lemma_norm text,
  pos text,
  ex_nl text,
  source_key text,
  external_id text,
  confidence text,
  review_status text,
  raw_payload text
) on commit drop;

create temp table stg_p1_generated_example_translations (
  batch_id text,
  example_external_id text,
  lang text,
  translation text,
  source_key text,
  external_id text,
  confidence text,
  review_status text,
  raw_payload text
) on commit drop;

\copy stg_p1_new_senses from '/tmp/dutch_lexicon_import/aigc_p1_bulk/p1_new_senses.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_p1_sense_translations from '/tmp/dutch_lexicon_import/aigc_p1_bulk/p1_sense_translations.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_p1_sense_examples from '/tmp/dutch_lexicon_import/aigc_p1_bulk/p1_sense_examples.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_p1_generated_example_translations from '/tmp/dutch_lexicon_import/aigc_p1_bulk/p1_generated_example_translations.tsv' with (format csv, delimiter E'\t', header true)

do $$
declare
  missing_count integer;
begin
  select count(*) into missing_count
  from (
    select definition_nl value from stg_p1_new_senses
    union all select usage_note from stg_p1_new_senses
    union all select gloss from stg_p1_sense_translations
    union all select explanation from stg_p1_sense_translations
    union all select ex_nl from stg_p1_sense_examples
    union all select translation from stg_p1_generated_example_translations
  ) generated
  where btrim(value) !~ '#aigc\s*$';
  if missing_count > 0 then
    raise exception 'P1 marker validation failed: % generated fields missing terminal #aigc', missing_count;
  end if;
end $$;

insert into public.senses (
  lemma_id,
  lemma_pos_entry_id,
  source_id,
  external_id,
  sense_no,
  definition_nl,
  usage_note,
  confidence,
  is_primary,
  review_status,
  raw_payload,
  display_definition_nl,
  dedupe_key,
  is_core
)
select
  stg.lemma_id::bigint,
  p.id,
  src.id,
  stg.external_id,
  'aigc-1',
  stg.definition_nl,
  stg.usage_note,
  stg.confidence::numeric,
  false,
  coalesce(nullif(stg.review_status, ''), 'unreviewed'),
  coalesce(nullif(stg.raw_payload, '')::jsonb, '{}'::jsonb),
  stg.definition_nl,
  regexp_replace(lower(btrim(replace(stg.definition_nl, '#aigc', ''))), '\s+', ' ', 'g'),
  false
from stg_p1_new_senses stg
join public.lemmas l on l.id = stg.lemma_id::bigint
join public.lemma_pos_entries p on p.lemma_id = l.id and p.pos = stg.pos
join public.sources src on src.source_key = stg.source_key
on conflict (source_id, external_id) where external_id is not null
do update set
  definition_nl = excluded.definition_nl,
  usage_note = excluded.usage_note,
  confidence = excluded.confidence,
  review_status = excluded.review_status,
  raw_payload = excluded.raw_payload,
  display_definition_nl = excluded.display_definition_nl,
  dedupe_key = excluded.dedupe_key,
  updated_at = now();

insert into public.sense_translations (
  sense_id,
  lang,
  gloss,
  explanation,
  source_id,
  external_id,
  confidence,
  review_status,
  translation_style,
  raw_payload
)
select
  s.id,
  stg.lang,
  stg.gloss,
  stg.explanation,
  src.id,
  stg.external_id,
  stg.confidence::numeric,
  coalesce(nullif(stg.review_status, ''), 'unreviewed'),
  coalesce(nullif(stg.translation_style, ''), 'learner_dictionary'),
  coalesce(nullif(stg.raw_payload, '')::jsonb, '{}'::jsonb)
from stg_p1_sense_translations stg
join public.sources sense_src on sense_src.source_key = 'aigc_missing_sense_v2'
join public.senses s on s.source_id = sense_src.id and s.external_id = stg.sense_external_id
join public.sources src on src.source_key = stg.source_key
where stg.lang in ('zh', 'en')
on conflict (sense_id, lang, source_id) where source_id is not null
do update set
  gloss = excluded.gloss,
  explanation = excluded.explanation,
  external_id = excluded.external_id,
  confidence = excluded.confidence,
  review_status = excluded.review_status,
  translation_style = excluded.translation_style,
  raw_payload = excluded.raw_payload,
  updated_at = now();

delete from public.examples e
using stg_p1_sense_examples stg, public.sources src
where src.source_key = stg.source_key
  and e.source_id = src.id
  and e.external_id = stg.external_id;

insert into public.examples (
  sense_id,
  ex_nl,
  source_id,
  external_id,
  quality_score,
  raw_payload
)
select
  s.id,
  stg.ex_nl,
  src.id,
  stg.external_id,
  stg.confidence::numeric,
  coalesce(nullif(stg.raw_payload, '')::jsonb, '{}'::jsonb)
from stg_p1_sense_examples stg
join public.sources sense_src on sense_src.source_key = 'aigc_missing_sense_v2'
join public.senses s on s.source_id = sense_src.id and s.external_id = stg.sense_external_id
join public.sources src on src.source_key = stg.source_key;

delete from public.example_translations et
using stg_p1_generated_example_translations stg, public.sources src
where src.source_key = stg.source_key
  and et.source_id = src.id
  and et.external_id = stg.external_id;

insert into public.example_translations (
  example_id,
  lang,
  translation,
  source_id,
  external_id
)
select
  e.id,
  stg.lang,
  stg.translation,
  src.id,
  stg.external_id
from stg_p1_generated_example_translations stg
join public.sources ex_src on ex_src.source_key = 'aigc_sense_examples_v2'
join public.examples e on e.source_id = ex_src.id and e.external_id = stg.example_external_id
join public.sources src on src.source_key = stg.source_key
where stg.lang in ('zh', 'en');

insert into public.aigc_full_batch_imports (
  batch_id,
  source_key,
  item_type,
  target_id,
  external_id,
  review_status,
  confidence,
  raw_payload
)
select batch_id, source_key, 'p1_new_sense', lemma_id::bigint, external_id, review_status, confidence::numeric, coalesce(nullif(raw_payload, '')::jsonb, '{}'::jsonb)
from stg_p1_new_senses
on conflict (source_key, external_id) do update
set review_status = excluded.review_status, confidence = excluded.confidence, raw_payload = excluded.raw_payload, imported_at = now();

with ordered_senses as (
  select
    s.id,
    row_number() over (
      partition by s.lemma_pos_entry_id
      order by
        s.is_primary desc,
        case when s.display_definition_nl is not null then 0 else 1 end,
        s.app_sense_order nulls last,
        s.id
    ) as sense_order
  from public.senses s
  where s.merged_into_sense_id is null
)
update public.senses s
set app_sense_order = o.sense_order, is_core = o.sense_order <= 3
from ordered_senses o
where s.id = o.id;

commit;

select 'p1_new_senses' as item_type, count(*) as rows
from public.senses s
join public.sources src on src.id = s.source_id
where src.source_key = 'aigc_missing_sense_v2'
union all
select 'p1_translations', count(*)
from public.sense_translations t
join public.sources src on src.id = t.source_id
join public.senses s on s.id = t.sense_id
join public.sources sense_src on sense_src.id = s.source_id
where src.source_key = 'aigc_sense_translation_v3'
  and sense_src.source_key = 'aigc_missing_sense_v2'
union all
select 'p1_examples', count(*)
from public.examples e
join public.sources src on src.id = e.source_id
join public.senses s on s.id = e.sense_id
join public.sources sense_src on sense_src.id = s.source_id
where src.source_key = 'aigc_sense_examples_v2'
  and sense_src.source_key = 'aigc_missing_sense_v2';
