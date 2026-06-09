\set ON_ERROR_STOP on

\set lemmas_file '/tmp/dutch_lexicon_import/full_20260529/lemmas.tsv'
\set lemma_corpus_stats_file '/tmp/dutch_lexicon_import/full_20260529/lemma_corpus_stats.tsv'
\set curated_form_levels_file '/tmp/dutch_lexicon_import/full_20260529/curated_form_levels.tsv'
\set pos_tags_extra_file '/tmp/dutch_lexicon_import/full_20260529/pos_tags_extra.tsv'
\set lemma_pos_entries_file '/tmp/dutch_lexicon_import/full_20260529/lemma_pos_entries.tsv'
\set forms_file '/tmp/dutch_lexicon_import/full_20260529/forms.tsv'
\set form_corpus_stats_file '/tmp/dutch_lexicon_import/full_20260529/form_corpus_stats.tsv'
\set senses_file '/tmp/dutch_lexicon_import/full_20260529/senses.tsv'
\set examples_file '/tmp/dutch_lexicon_import/full_20260529/examples.tsv'

begin;

truncate
  public.sense_relations,
  public.lemma_relations,
  public.example_translations,
  public.examples,
  public.sense_translations,
  public.senses,
  public.form_corpus_stats,
  public.forms,
  public.lemma_corpus_stats,
  public.lemma_level_evidence,
  public.curated_form_levels,
  public.lemma_pos_entries,
  public.lemmas,
  public.lexical_import_runs
restart identity cascade;

create temp table stg_lemmas (
  lemma text,
  lemma_norm text,
  display_lemma text,
  level text,
  word_family text,
  is_academic text,
  academic_source text,
  subtlex_freq text,
  subtlex_form_count text,
  cc100_freq text,
  cc100_form_count text,
  popularity text
) on commit drop;

create temp table stg_lemma_corpus_stats (
  lemma_norm text,
  corpus_key text,
  freq_count text,
  form_count text,
  rank text,
  coverage text,
  metadata text
) on commit drop;

create temp table stg_curated_form_levels (
  form text,
  form_norm text,
  level text,
  source_name text,
  note text,
  raw_payload text
) on commit drop;

create temp table stg_pos_tags_extra (
  tag text,
  english text,
  dutch text,
  description_zh text,
  example text,
  sort_order text
) on commit drop;

create temp table stg_lemma_pos_entries (
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

create temp table stg_forms (
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

create temp table stg_form_corpus_stats (
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

create temp table stg_senses (
  lemma_norm text,
  pos text,
  source_key text,
  external_id text,
  external_synset_id text,
  sense_no text,
  definition_nl text,
  usage_note text,
  domain text,
  register text,
  confidence text,
  is_primary text,
  review_status text,
  raw_payload text
) on commit drop;

create temp table stg_examples (
  sense_source_key text,
  sense_external_id text,
  ex_nl text,
  source_key text,
  external_id text,
  quality_score text,
  raw_payload text
) on commit drop;

\copy stg_lemmas from '/tmp/dutch_lexicon_import/full_20260529/lemmas.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_lemma_corpus_stats from '/tmp/dutch_lexicon_import/full_20260529/lemma_corpus_stats.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_curated_form_levels from '/tmp/dutch_lexicon_import/full_20260529/curated_form_levels.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_pos_tags_extra from '/tmp/dutch_lexicon_import/full_20260529/pos_tags_extra.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_lemma_pos_entries from '/tmp/dutch_lexicon_import/full_20260529/lemma_pos_entries.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_forms from '/tmp/dutch_lexicon_import/full_20260529/forms.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_form_corpus_stats from '/tmp/dutch_lexicon_import/full_20260529/form_corpus_stats.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_senses from '/tmp/dutch_lexicon_import/full_20260529/senses.tsv' with (format csv, delimiter E'\t', header true)
\copy stg_examples from '/tmp/dutch_lexicon_import/full_20260529/examples.tsv' with (format csv, delimiter E'\t', header true)

insert into public.lexical_import_runs (run_key, source_id, import_type, status, started_at, finished_at, metadata)
select
  'lexicon_full_import_20260529',
  sources.id,
  'full_lexicon_import',
  'completed',
  now(),
  now(),
  jsonb_build_object(
    'lemmas', (select count(*) from stg_lemmas),
    'forms', (select count(*) from stg_forms),
    'senses', (select count(*) from stg_senses)
  )
from public.sources
where source_key = 'manual_vocab_levels_v1';

insert into public.pos_tags (tag, english, dutch, description_zh, example, sort_order)
select distinct
  tag,
  nullif(english, ''),
  nullif(dutch, ''),
  nullif(description_zh, ''),
  nullif(example, ''),
  nullif(sort_order, '')::integer
from stg_pos_tags_extra
where tag is not null and tag <> ''
on conflict (tag) do update
set
  english = excluded.english,
  dutch = excluded.dutch,
  description_zh = excluded.description_zh,
  example = excluded.example;

insert into public.lemmas (
  lemma,
  lemma_norm,
  display_lemma,
  level,
  level_source,
  level_confidence,
  word_family,
  is_academic,
  academic_source,
  popularity,
  subtlex_freq,
  subtlex_form_count,
  cc100_freq,
  cc100_form_count,
  source_id,
  import_run_id
)
select
  l.lemma,
  l.lemma_norm,
  nullif(l.display_lemma, ''),
  l.level::smallint,
  'manual_vocab_levels_v1',
  1.000,
  nullif(l.word_family, ''),
  l.is_academic::boolean,
  nullif(l.academic_source, ''),
  nullif(l.popularity, '')::integer,
  nullif(l.subtlex_freq, '')::bigint,
  nullif(l.subtlex_form_count, '')::integer,
  nullif(l.cc100_freq, '')::bigint,
  nullif(l.cc100_form_count, '')::integer,
  s.id,
  r.id
from stg_lemmas l
join public.sources s on s.source_key = 'manual_vocab_levels_v1'
join public.lexical_import_runs r on r.run_key = 'lexicon_full_import_20260529';

update public.lemmas l
set family_head_lemma_id = h.id
from public.lemmas h
where l.word_family is not null
  and lower(l.word_family) = h.lemma_norm;

insert into public.lemma_corpus_stats (
  lemma_id,
  corpus_id,
  freq_count,
  form_count,
  rank,
  coverage,
  metadata
)
select
  l.id,
  c.id,
  nullif(s.freq_count, '')::bigint,
  nullif(s.form_count, '')::integer,
  nullif(s.rank, '')::integer,
  nullif(s.coverage, '')::numeric,
  coalesce(nullif(s.metadata, '')::jsonb, '{}'::jsonb)
from stg_lemma_corpus_stats s
join public.lemmas l on l.lemma_norm = s.lemma_norm
join public.corpora c on c.corpus_key = s.corpus_key;

insert into public.curated_form_levels (
  form,
  form_norm,
  level,
  source_name,
  source_id,
  note,
  raw_payload
)
select
  c.form,
  c.form_norm,
  c.level::smallint,
  c.source_name,
  s.id,
  nullif(c.note, ''),
  coalesce(nullif(c.raw_payload, '')::jsonb, '{}'::jsonb)
from stg_curated_form_levels c
left join public.sources s on s.source_key = c.source_name;

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
from stg_lemma_pos_entries p
join public.lemmas l on l.lemma_norm = p.lemma_norm;

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
from stg_forms f
join public.lemmas l on l.lemma_norm = f.lemma_norm
join public.lemma_pos_entries p on p.lemma_id = l.id and p.pos = f.pos
left join public.sources s on s.source_key = f.source_key;

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
from stg_form_corpus_stats s
join public.lemmas l on l.lemma_norm = s.lemma_norm
join public.lemma_pos_entries p on p.lemma_id = l.id and p.pos = s.pos
join public.forms f
  on f.lemma_pos_entry_id = p.id
  and f.form_norm = s.form_norm
  and coalesce(f.form_type, '') = coalesce(nullif(s.form_type, ''), '')
join public.corpora c on c.corpus_key = s.corpus_key
order by f.id, c.id, nullif(s.rank, '')::integer nulls last;

insert into public.senses (
  lemma_id,
  lemma_pos_entry_id,
  source_id,
  external_id,
  external_synset_id,
  sense_no,
  definition_nl,
  usage_note,
  domain,
  register,
  confidence,
  is_primary,
  review_status,
  raw_payload
)
select
  l.id,
  p.id,
  src.id,
  nullif(s.external_id, ''),
  nullif(s.external_synset_id, ''),
  nullif(s.sense_no, ''),
  nullif(s.definition_nl, ''),
  nullif(s.usage_note, ''),
  nullif(s.domain, ''),
  nullif(s.register, ''),
  coalesce(nullif(s.confidence, '')::numeric, 1.000),
  coalesce(nullif(s.is_primary, '')::boolean, false),
  coalesce(nullif(s.review_status, ''), 'unreviewed'),
  coalesce(nullif(s.raw_payload, '')::jsonb, '{}'::jsonb)
from stg_senses s
join public.lemmas l on l.lemma_norm = s.lemma_norm
join public.lemma_pos_entries p on p.lemma_id = l.id and p.pos = s.pos
join public.sources src on src.source_key = s.source_key
on conflict do nothing;

insert into public.examples (
  sense_id,
  ex_nl,
  source_id,
  external_id,
  quality_score,
  raw_payload
)
select
  se.id,
  e.ex_nl,
  src.id,
  nullif(e.external_id, ''),
  nullif(e.quality_score, '')::numeric,
  coalesce(nullif(e.raw_payload, '')::jsonb, '{}'::jsonb)
from stg_examples e
join public.sources sense_src on sense_src.source_key = e.sense_source_key
join public.senses se on se.source_id = sense_src.id and se.external_id = e.sense_external_id
left join public.sources src on src.source_key = e.source_key
where e.ex_nl is not null and e.ex_nl <> '';

insert into public.lemma_level_evidence (
  lemma_id,
  form_id,
  curated_form_level_id,
  matched_form,
  matched_level,
  match_type,
  confidence
)
select distinct
  f.lemma_id,
  f.id,
  c.id,
  c.form,
  c.level,
  'form_norm_match',
  case when l.level = c.level then 1.000 else 0.500 end
from public.curated_form_levels c
join public.forms f on f.form_norm = c.form_norm
join public.lemmas l on l.id = f.lemma_id;

commit;

select 'lemmas' as table_name, count(*) as rows from public.lemmas
union all select 'lemma_pos_entries', count(*) from public.lemma_pos_entries
union all select 'forms', count(*) from public.forms
union all select 'senses', count(*) from public.senses
union all select 'examples', count(*) from public.examples
union all select 'curated_form_levels', count(*) from public.curated_form_levels
union all select 'lemma_level_evidence', count(*) from public.lemma_level_evidence
order by table_name;
