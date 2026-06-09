\set ON_ERROR_STOP on

begin;

create temp table stg_cc100_pos_tags_extra (
  tag text,
  english text,
  dutch text,
  description_zh text,
  example text,
  sort_order text
) on commit drop;

create temp table stg_cc100_lemma_pos_entries (
  lemma_norm text,
  pos text,
  pos_source text,
  pos_confidence text,
  gender text,
  article text,
  external_entry_id text,
  is_primary text,
  needs_review text,
  notes text
) on commit drop;

create temp table stg_cc100_forms (
  lemma_norm text,
  pos text,
  form text,
  form_norm text,
  form_type text,
  source_key text,
  external_id text,
  is_canonical text,
  confidence text,
  raw_payload text
) on commit drop;

create temp table stg_cc100_form_corpus_stats (
  lemma_norm text,
  pos text,
  form_norm text,
  form_type text,
  corpus_key text,
  freq_count text,
  doc_count text,
  freq_low text,
  doc_low text,
  zipf text,
  rank text,
  metadata text
) on commit drop;

\copy stg_cc100_pos_tags_extra from '/tmp/dutch_lexicon_import/full_20260529/cc100_pos_tags_extra.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_cc100_lemma_pos_entries from '/tmp/dutch_lexicon_import/full_20260529/cc100_lemma_pos_entries.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_cc100_forms from '/tmp/dutch_lexicon_import/full_20260529/cc100_forms.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_cc100_form_corpus_stats from '/tmp/dutch_lexicon_import/full_20260529/cc100_form_corpus_stats.tsv' with (format csv, delimiter E'\t', header true)

insert into public.pos_tags (tag, english, dutch, description_zh, example, sort_order)
select distinct
  tag,
  nullif(english, ''),
  nullif(dutch, ''),
  nullif(description_zh, ''),
  nullif(example, ''),
  nullif(sort_order, '')::integer
from stg_cc100_pos_tags_extra
where tag is not null and tag <> ''
on conflict (tag) do update
set
  english = excluded.english,
  dutch = excluded.dutch,
  description_zh = excluded.description_zh,
  example = excluded.example;

insert into public.lemma_pos_entries (
  lemma_id,
  pos,
  pos_source,
  pos_confidence,
  gender,
  article,
  external_entry_id,
  is_primary,
  needs_review,
  notes
)
select
  l.id,
  p.pos,
  nullif(p.pos_source, ''),
  coalesce(nullif(p.pos_confidence, '')::numeric, 1.000),
  nullif(p.gender, ''),
  nullif(p.article, ''),
  nullif(p.external_entry_id, ''),
  coalesce(nullif(p.is_primary, '')::boolean, false),
  coalesce(nullif(p.needs_review, '')::boolean, false),
  nullif(p.notes, '')
from stg_cc100_lemma_pos_entries p
join public.lemmas l on l.lemma_norm = p.lemma_norm
on conflict (lemma_id, pos) do update
set
  pos_source = case
    when public.lemma_pos_entries.pos_confidence < excluded.pos_confidence then excluded.pos_source
    else public.lemma_pos_entries.pos_source
  end,
  pos_confidence = greatest(public.lemma_pos_entries.pos_confidence, excluded.pos_confidence);

insert into public.forms (
  lemma_id,
  lemma_pos_entry_id,
  form,
  form_norm,
  form_type,
  source_id,
  external_id,
  is_canonical,
  confidence,
  raw_payload
)
select
  l.id,
  p.id,
  f.form,
  f.form_norm,
  nullif(f.form_type, ''),
  s.id,
  nullif(f.external_id, ''),
  coalesce(nullif(f.is_canonical, '')::boolean, false),
  coalesce(nullif(f.confidence, '')::numeric, 1.000),
  coalesce(nullif(f.raw_payload, '')::jsonb, '{}'::jsonb)
from stg_cc100_forms f
join public.lemmas l on l.lemma_norm = f.lemma_norm
join public.lemma_pos_entries p on p.lemma_id = l.id and p.pos = f.pos
left join public.sources s on s.source_key = f.source_key
on conflict do nothing;

insert into public.form_corpus_stats (
  form_id,
  corpus_id,
  freq_count,
  doc_count,
  freq_low,
  doc_low,
  zipf,
  rank,
  metadata
)
select distinct on (f.id, c.id)
  f.id,
  c.id,
  nullif(s.freq_count, '')::bigint,
  nullif(s.doc_count, '')::bigint,
  nullif(s.freq_low, '')::bigint,
  nullif(s.doc_low, '')::bigint,
  nullif(s.zipf, '')::numeric,
  nullif(s.rank, '')::integer,
  coalesce(nullif(s.metadata, '')::jsonb, '{}'::jsonb)
from stg_cc100_form_corpus_stats s
join public.lemmas l on l.lemma_norm = s.lemma_norm
join public.lemma_pos_entries p on p.lemma_id = l.id and p.pos = s.pos
join public.forms f
  on f.lemma_pos_entry_id = p.id
  and f.form_norm = s.form_norm
  and coalesce(f.form_type, '') = coalesce(nullif(s.form_type, ''), '')
join public.corpora c on c.corpus_key = s.corpus_key
order by f.id, c.id
on conflict (form_id, corpus_id) do update
set
  freq_count = excluded.freq_count,
  doc_count = excluded.doc_count,
  freq_low = excluded.freq_low,
  doc_low = excluded.doc_low,
  metadata = excluded.metadata,
  updated_at = now();

commit;

select 'lemma_pos_entries' as table_name, count(*) as rows from public.lemma_pos_entries
union all select 'forms', count(*) from public.forms
union all select 'cc100_form_stats', count(*) from public.form_corpus_stats fs join public.corpora c on c.id = fs.corpus_id where c.corpus_key = 'cc100_nl_local_20260525'
order by table_name;
