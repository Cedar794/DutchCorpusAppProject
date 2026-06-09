-- Load validated lemma example candidates from a TSV copied into the DB container.
-- Expected file path in container:
--   /tmp/dutch_lexicon_import/app_enrichment/lemma_examples.tsv

\set ON_ERROR_STOP on

begin;

create temp table stg_lemma_examples (
  lemma_id text,
  lemma_pos_entry_id text,
  form_id text,
  ex_nl text,
  source_key text,
  external_id text,
  quality_score text,
  raw_payload text
);

\copy stg_lemma_examples from '/tmp/dutch_lexicon_import/app_enrichment/lemma_examples.tsv' with (format csv, delimiter E'\t', header true)

insert into public.lemma_examples (
  lemma_id,
  lemma_pos_entry_id,
  form_id,
  ex_nl,
  source_id,
  external_id,
  quality_score,
  raw_payload
)
select
  s.lemma_id::bigint,
  nullif(s.lemma_pos_entry_id, '')::bigint,
  nullif(s.form_id, '')::bigint,
  s.ex_nl,
  src.id,
  nullif(s.external_id, ''),
  nullif(s.quality_score, '')::numeric,
  coalesce(nullif(s.raw_payload, '')::jsonb, '{}'::jsonb)
from stg_lemma_examples s
join public.lemmas l on l.id = s.lemma_id::bigint
left join public.lemma_pos_entries p on p.id = nullif(s.lemma_pos_entry_id, '')::bigint
left join public.forms f on f.id = nullif(s.form_id, '')::bigint
join public.sources src on src.source_key = s.source_key
where nullif(btrim(s.ex_nl), '') is not null
on conflict (lemma_id, lemma_pos_entry_id, ex_nl)
do update set
  form_id = excluded.form_id,
  source_id = excluded.source_id,
  external_id = excluded.external_id,
  quality_score = excluded.quality_score,
  raw_payload = excluded.raw_payload,
  updated_at = now();

commit;

select 'lemma_examples', count(*) from public.lemma_examples;
