-- Load validated LLM sense translations from a TSV copied into the DB container.
-- Expected file path in container:
--   /tmp/dutch_lexicon_import/app_enrichment/sense_translations_valid.tsv

\set ON_ERROR_STOP on

begin;

create temp table stg_sense_translations (
  sense_id text,
  lang text,
  gloss text,
  explanation text,
  source_key text,
  external_id text,
  confidence text,
  review_status text,
  translation_style text,
  raw_payload text
);

\copy stg_sense_translations from '/tmp/dutch_lexicon_import/app_enrichment/sense_translations_valid.tsv' with (format csv, delimiter E'\t', header true)

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
  s.sense_id::bigint,
  s.lang,
  s.gloss,
  s.explanation,
  src.id,
  nullif(s.external_id, ''),
  coalesce(nullif(s.confidence, '')::numeric, 0.700),
  coalesce(nullif(s.review_status, ''), 'unreviewed'),
  coalesce(nullif(s.translation_style, ''), 'learner_dictionary'),
  coalesce(nullif(s.raw_payload, '')::jsonb, '{}'::jsonb)
from stg_sense_translations s
join public.senses se on se.id = s.sense_id::bigint
join public.sources src on src.source_key = s.source_key
where s.lang in ('zh', 'en')
  and nullif(btrim(s.gloss), '') is not null
  and nullif(btrim(s.explanation), '') is not null
on conflict (sense_id, lang, source_id)
where source_id is not null
do update set
  gloss = excluded.gloss,
  explanation = excluded.explanation,
  external_id = excluded.external_id,
  confidence = excluded.confidence,
  review_status = excluded.review_status,
  translation_style = excluded.translation_style,
  raw_payload = excluded.raw_payload,
  updated_at = now();

commit;

select lang, count(*) as rows
from public.sense_translations t
join public.sources s on s.id = t.source_id
where s.source_key = 'llm_sense_translation_v1'
group by lang
order by lang;
