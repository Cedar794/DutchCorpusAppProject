-- Dutch corpus lexicon application schema.
-- Level is assigned at normalized lemma-string level in public.lemmas.
-- POS-specific entries, forms, and senses inherit that lemma-level assignment.

create extension if not exists pgcrypto with schema extensions;
create extension if not exists pg_trgm with schema extensions;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table public.sources (
  id bigserial primary key,
  source_key text not null unique,
  name text not null,
  source_type text not null,
  url text,
  license text,
  license_url text,
  attribution text,
  version text,
  downloaded_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.lexical_import_runs (
  id uuid primary key default gen_random_uuid(),
  run_key text not null unique,
  source_id bigint references public.sources(id) on delete set null,
  import_type text not null,
  status text not null default 'pending'
    check (status in ('pending', 'running', 'completed', 'failed', 'cancelled')),
  started_at timestamptz,
  finished_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.corpora (
  id bigserial primary key,
  source_id bigint references public.sources(id) on delete set null,
  corpus_key text not null unique,
  name text not null,
  language text not null default 'nl',
  version text,
  token_count bigint,
  document_count bigint,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.pos_tags (
  tag text primary key,
  english text,
  dutch text,
  description_zh text,
  example text,
  sort_order integer
);

create table public.lemmas (
  id bigserial primary key,
  lemma text not null,
  lemma_norm text not null unique,
  display_lemma text,
  level smallint not null check (level between 1 and 4),
  level_source text not null default 'manual_vocab_levels_v1',
  level_confidence numeric(4,3) not null default 1.000
    check (level_confidence >= 0 and level_confidence <= 1),
  word_family text,
  family_head_lemma_id bigint references public.lemmas(id) on delete set null,
  is_academic boolean not null default false,
  academic_source text,
  popularity integer,
  cefr_level text,
  subtlex_freq bigint,
  subtlex_form_count integer,
  cc100_freq bigint,
  cc100_form_count integer,
  source_id bigint references public.sources(id) on delete set null,
  import_run_id uuid references public.lexical_import_runs(id) on delete set null,
  review_status text not null default 'accepted'
    check (review_status in ('accepted', 'needs_review', 'rejected')),
  needs_review boolean not null default false,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.lemmas is
  'One row per normalized lemma string. The vocabulary level is assigned here and inherited by every POS-specific entry for the same lemma.';

create table public.lemma_pos_entries (
  id bigserial primary key,
  lemma_id bigint not null references public.lemmas(id) on delete cascade,
  pos text not null references public.pos_tags(tag) on update cascade,
  pos_source text,
  pos_confidence numeric(4,3) not null default 1.000
    check (pos_confidence >= 0 and pos_confidence <= 1),
  gender text,
  article text,
  external_entry_id text,
  is_primary boolean not null default false,
  needs_review boolean not null default false,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (lemma_id, pos)
);

comment on table public.lemma_pos_entries is
  'POS-specific lexical entries under a lemma. All entries under the same lemma inherit public.lemmas.level.';

create table public.forms (
  id bigserial primary key,
  lemma_id bigint not null references public.lemmas(id) on delete cascade,
  lemma_pos_entry_id bigint references public.lemma_pos_entries(id) on delete cascade,
  form text not null,
  form_norm text not null,
  form_type text,
  source_id bigint references public.sources(id) on delete set null,
  external_id text,
  is_canonical boolean not null default false,
  confidence numeric(4,3) not null default 1.000
    check (confidence >= 0 and confidence <= 1),
  needs_review boolean not null default false,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index forms_pos_form_type_unique
  on public.forms (lemma_pos_entry_id, form_norm, coalesce(form_type, ''));

create table public.curated_form_levels (
  id bigserial primary key,
  form text not null,
  form_norm text not null,
  level smallint not null check (level between 1 and 4),
  source_name text not null default 'manual_vocab_levels_v1',
  source_id bigint references public.sources(id) on delete set null,
  note text,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (form_norm, level, source_name)
);

create table public.lemma_level_evidence (
  id bigserial primary key,
  lemma_id bigint not null references public.lemmas(id) on delete cascade,
  form_id bigint references public.forms(id) on delete set null,
  curated_form_level_id bigint references public.curated_form_levels(id) on delete set null,
  matched_form text,
  matched_level smallint check (matched_level between 1 and 4),
  match_type text not null,
  confidence numeric(4,3) not null default 1.000
    check (confidence >= 0 and confidence <= 1),
  created_at timestamptz not null default now()
);

create table public.lemma_corpus_stats (
  id bigserial primary key,
  lemma_id bigint not null references public.lemmas(id) on delete cascade,
  corpus_id bigint not null references public.corpora(id) on delete cascade,
  freq_count bigint,
  form_count integer,
  rank integer,
  coverage numeric,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (lemma_id, corpus_id)
);

create table public.form_corpus_stats (
  id bigserial primary key,
  form_id bigint not null references public.forms(id) on delete cascade,
  corpus_id bigint not null references public.corpora(id) on delete cascade,
  freq_count bigint,
  doc_count bigint,
  freq_low bigint,
  doc_low bigint,
  zipf numeric,
  rank integer,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (form_id, corpus_id)
);

create table public.senses (
  id bigserial primary key,
  lemma_id bigint not null references public.lemmas(id) on delete cascade,
  lemma_pos_entry_id bigint references public.lemma_pos_entries(id) on delete cascade,
  source_id bigint not null references public.sources(id) on delete restrict,
  external_id text,
  external_synset_id text,
  sense_no text,
  definition_nl text,
  usage_note text,
  domain text,
  register text,
  confidence numeric(4,3) not null default 1.000
    check (confidence >= 0 and confidence <= 1),
  is_primary boolean not null default false,
  review_status text not null default 'unreviewed'
    check (review_status in ('unreviewed', 'accepted', 'needs_review', 'rejected')),
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index senses_source_external_id_unique
  on public.senses (source_id, external_id)
  where external_id is not null;

create table public.sense_translations (
  id bigserial primary key,
  sense_id bigint not null references public.senses(id) on delete cascade,
  lang text not null,
  gloss text not null,
  explanation text,
  source_id bigint references public.sources(id) on delete set null,
  external_id text,
  confidence numeric(4,3) not null default 1.000
    check (confidence >= 0 and confidence <= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.examples (
  id bigserial primary key,
  sense_id bigint not null references public.senses(id) on delete cascade,
  ex_nl text not null,
  source_id bigint references public.sources(id) on delete set null,
  external_id text,
  cefr_level text,
  quality_score numeric(4,3)
    check (quality_score is null or (quality_score >= 0 and quality_score <= 1)),
  is_active boolean not null default true,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.example_translations (
  id bigserial primary key,
  example_id bigint not null references public.examples(id) on delete cascade,
  lang text not null,
  translation text not null,
  source_id bigint references public.sources(id) on delete set null,
  external_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.lemma_relations (
  id bigserial primary key,
  lemma_id_from bigint not null references public.lemmas(id) on delete cascade,
  lemma_id_to bigint not null references public.lemmas(id) on delete cascade,
  relation_type text not null,
  source_id bigint references public.sources(id) on delete set null,
  external_id text,
  confidence numeric(4,3) not null default 1.000
    check (confidence >= 0 and confidence <= 1),
  notes text,
  created_at timestamptz not null default now(),
  unique (lemma_id_from, lemma_id_to, relation_type, source_id)
);

create table public.sense_relations (
  id bigserial primary key,
  sense_id_from bigint not null references public.senses(id) on delete cascade,
  sense_id_to bigint references public.senses(id) on delete cascade,
  target_external_id text,
  relation_type text not null,
  source_id bigint references public.sources(id) on delete set null,
  confidence numeric(4,3) not null default 1.000
    check (confidence >= 0 and confidence <= 1),
  notes text,
  created_at timestamptz not null default now()
);

create index sources_source_type_idx on public.sources (source_type);
create index corpora_language_idx on public.corpora (language);
create index lemmas_level_idx on public.lemmas (level);
create index lemmas_family_idx on public.lemmas (word_family);
create index lemmas_lemma_norm_trgm_idx on public.lemmas using gin (lemma_norm gin_trgm_ops);
create index lemma_pos_entries_lemma_id_idx on public.lemma_pos_entries (lemma_id);
create index lemma_pos_entries_pos_idx on public.lemma_pos_entries (pos);
create index forms_lemma_id_idx on public.forms (lemma_id);
create index forms_form_norm_idx on public.forms (form_norm);
create index forms_form_norm_trgm_idx on public.forms using gin (form_norm gin_trgm_ops);
create index lemma_level_evidence_lemma_id_idx on public.lemma_level_evidence (lemma_id);
create index lemma_corpus_stats_corpus_id_idx on public.lemma_corpus_stats (corpus_id);
create index form_corpus_stats_corpus_id_idx on public.form_corpus_stats (corpus_id);
create index senses_lemma_id_idx on public.senses (lemma_id);
create index senses_lemma_pos_entry_id_idx on public.senses (lemma_pos_entry_id);
create index senses_source_id_idx on public.senses (source_id);
create index senses_definition_nl_trgm_idx on public.senses using gin (definition_nl gin_trgm_ops);
create index sense_translations_sense_id_idx on public.sense_translations (sense_id);
create index examples_sense_id_idx on public.examples (sense_id);
create index lemma_relations_from_idx on public.lemma_relations (lemma_id_from, relation_type);
create index lemma_relations_to_idx on public.lemma_relations (lemma_id_to, relation_type);
create index sense_relations_from_idx on public.sense_relations (sense_id_from, relation_type);

create trigger sources_set_updated_at
before update on public.sources
for each row execute function public.set_updated_at();

create trigger lexical_import_runs_set_updated_at
before update on public.lexical_import_runs
for each row execute function public.set_updated_at();

create trigger corpora_set_updated_at
before update on public.corpora
for each row execute function public.set_updated_at();

create trigger lemmas_set_updated_at
before update on public.lemmas
for each row execute function public.set_updated_at();

create trigger lemma_pos_entries_set_updated_at
before update on public.lemma_pos_entries
for each row execute function public.set_updated_at();

create trigger forms_set_updated_at
before update on public.forms
for each row execute function public.set_updated_at();

create trigger lemma_corpus_stats_set_updated_at
before update on public.lemma_corpus_stats
for each row execute function public.set_updated_at();

create trigger form_corpus_stats_set_updated_at
before update on public.form_corpus_stats
for each row execute function public.set_updated_at();

create trigger senses_set_updated_at
before update on public.senses
for each row execute function public.set_updated_at();

create trigger sense_translations_set_updated_at
before update on public.sense_translations
for each row execute function public.set_updated_at();

create trigger examples_set_updated_at
before update on public.examples
for each row execute function public.set_updated_at();

create trigger example_translations_set_updated_at
before update on public.example_translations
for each row execute function public.set_updated_at();

insert into public.pos_tags (tag, english, dutch, description_zh, example, sort_order)
values
  ('NOUN', 'Noun', 'Zelfstandig naamwoord', '名词', 'huis, eten', 10),
  ('VERB', 'Verb', 'Werkwoord', '动词', 'lopen, eten', 20),
  ('ADJ', 'Adjective', 'Bijvoeglijk naamwoord', '形容词', 'groot, mooi', 30),
  ('ADV', 'Adverb', 'Bijwoord', '副词', 'snel, niet, hier', 40),
  ('PROPN', 'Proper Noun', 'Eigennaam', '专有名词', 'Nederland, Jan', 50),
  ('PRON', 'Pronoun', 'Voornaamwoord', '代词', 'ik, jij, zich, wie', 60),
  ('ADP', 'Adposition', 'Voorzetsel', '介词/后置词', 'in, op, naar, mee', 70),
  ('DET', 'Determiner', 'Lidwoord / Bepaler', '限定词/冠词', 'de, het, een', 80),
  ('NUM', 'Numeral', 'Telwoord', '数词', 'één, twee, eerste', 90),
  ('AUX', 'Auxiliary', 'Hulpwerkwoord', '助动词', 'zijn, hebben, worden', 100),
  ('CONJ', 'Coord. Conjunction', 'Nevenschikkend voegwoord', '并列连词', 'en, of, maar', 110),
  ('SCONJ', 'Sub. Conjunction', 'Onderschikkend voegwoord', '从属连词', 'dat, omdat, als', 120),
  ('INTJ', 'Interjection', 'Tussenwerpsel', '感叹词', 'hé, ja, nou, oh', 130),
  ('PART', 'Particle', 'Partikel', '小品词', 'te, niet', 140),
  ('PUNCT', 'Punctuation', 'Leesteken', '标点', '. , ?', 150),
  ('SYM', 'Symbol', 'Symbool', '符号', '$ % &', 160),
  ('X', 'Other', 'Overig', '其他/无法分类', 'foreign or unclassified', 170),
  ('SPEC', 'Special', 'Speciaal', 'Frog 特殊类', '$, urls, symbols', 180),
  ('LET', 'Punctuation', 'Leesteken', 'Frog 标点类', '. , ?', 190),
  ('TW', 'Numeral', 'Telwoord', 'Frog 数词类', '1, twee', 200),
  ('VNW', 'Pronoun', 'Voornaamwoord', 'Frog 代词类', 'ik, hem', 210),
  ('LID', 'Article', 'Lidwoord', 'Frog 冠词类', 'de, het, een', 220),
  ('VZ', 'Preposition', 'Voorzetsel', 'Frog 介词类', 'in, op', 230),
  ('VG', 'Conjunction', 'Voegwoord', 'Frog 连词类', 'en, omdat', 240),
  ('WW', 'Verb', 'Werkwoord', 'Frog 动词类', 'lopen, zijn', 250),
  ('N', 'Noun', 'Zelfstandig naamwoord', 'Frog 名词类', 'huis, eten', 260),
  ('ADJ_FROG', 'Adjective', 'Bijvoeglijk naamwoord', 'Frog 形容词类', 'groot, mooi', 270),
  ('BW', 'Adverb', 'Bijwoord', 'Frog 副词类', 'snel, hier', 280)
on conflict (tag) do nothing;

insert into public.sources
  (source_key, name, source_type, url, license, license_url, attribution, version, notes)
values
  (
    'manual_vocab_levels_v1',
    'Manual vocabulary levels v1',
    'manual',
    null,
    'internal',
    null,
    'Curated 1-4 vocabulary level files provided in the project workspace.',
    '2026-05-28',
    'Primary lemma-level vocabulary grading source.'
  ),
  (
    'subtlex_nl',
    'SUBTLEX-NL with POS and Zipf',
    'corpus_frequency',
    null,
    'source-specific',
    null,
    'Original SUBTLEX-NL workbook used for frequency and form grouping.',
    null,
    'Subtitle corpus frequency source.'
  ),
  (
    'cc100_nl_local_20260525',
    'CC100 Dutch local analysis',
    'corpus_frequency',
    null,
    'source-specific',
    null,
    'Local CC100 Dutch Frog annotation and frequency analysis in /Users/cedar/Desktop/dutch-corpus.',
    'annotated_full_live_w8_b4000',
    '5,002,252,182-token local corpus analysis.'
  ),
  (
    'odwn_1_3',
    'Open Dutch WordNet 1.3',
    'lexical_semantic',
    'https://github.com/cltl/OpenDutchWordnet',
    'CC BY-SA 4.0',
    'https://creativecommons.org/licenses/by-sa/4.0/',
    'Open Dutch WordNet, derived from Cornetto and Open Multilingual Wordnet resources.',
    '1.3',
    'Sense, synset, POS, and lexical relation source.'
  ),
  (
    'dbnary_nld_2026_05',
    'DBnary Dutch OntoLex',
    'wiktionary_extract',
    'https://kaiko.getalp.org/about-dbnary/',
    'CC BY-SA 3.0',
    'https://creativecommons.org/licenses/by-sa/3.0/',
    'DBnary extraction from Dutch Wiktionary.',
    '2026-05',
    'Supplementary sense, definition, example, relation, and translation source.'
  ),
  (
    'opentaal_hunspell',
    'OpenTaal Hunspell Dutch',
    'morphology_wordlist',
    'https://github.com/OpenTaal/opentaal-hunspell',
    'project license',
    null,
    'OpenTaal Dutch spelling and Hunspell resources.',
    null,
    'Supplementary form/spelling source; license should be reviewed before redistribution.'
  )
on conflict (source_key) do nothing;

insert into public.corpora
  (source_id, corpus_key, name, language, version, token_count, document_count, description)
select id, 'subtlex_nl', 'SUBTLEX-NL', 'nl', null, 44000000, null,
       'Dutch subtitle corpus used as the primary grading frequency source.'
from public.sources where source_key = 'subtlex_nl'
on conflict (corpus_key) do nothing;

insert into public.corpora
  (source_id, corpus_key, name, language, version, token_count, document_count, description)
select id, 'cc100_nl_local_20260525', 'CC100 Dutch local analysis', 'nl',
       'annotated_full_live_w8_b4000', 5002252182, 198229800,
       'Local CC100 Dutch corpus annotation run with Frog POS/lemma analysis.'
from public.sources where source_key = 'cc100_nl_local_20260525'
on conflict (corpus_key) do nothing;

alter table public.sources enable row level security;
alter table public.lexical_import_runs enable row level security;
alter table public.corpora enable row level security;
alter table public.pos_tags enable row level security;
alter table public.lemmas enable row level security;
alter table public.lemma_pos_entries enable row level security;
alter table public.forms enable row level security;
alter table public.curated_form_levels enable row level security;
alter table public.lemma_level_evidence enable row level security;
alter table public.lemma_corpus_stats enable row level security;
alter table public.form_corpus_stats enable row level security;
alter table public.senses enable row level security;
alter table public.sense_translations enable row level security;
alter table public.examples enable row level security;
alter table public.example_translations enable row level security;
alter table public.lemma_relations enable row level security;
alter table public.sense_relations enable row level security;

create policy "public read sources" on public.sources
for select to anon, authenticated using (true);
create policy "public read lexical_import_runs" on public.lexical_import_runs
for select to anon, authenticated using (true);
create policy "public read corpora" on public.corpora
for select to anon, authenticated using (true);
create policy "public read pos_tags" on public.pos_tags
for select to anon, authenticated using (true);
create policy "public read lemmas" on public.lemmas
for select to anon, authenticated using (true);
create policy "public read lemma_pos_entries" on public.lemma_pos_entries
for select to anon, authenticated using (true);
create policy "public read forms" on public.forms
for select to anon, authenticated using (true);
create policy "public read curated_form_levels" on public.curated_form_levels
for select to anon, authenticated using (true);
create policy "public read lemma_level_evidence" on public.lemma_level_evidence
for select to anon, authenticated using (true);
create policy "public read lemma_corpus_stats" on public.lemma_corpus_stats
for select to anon, authenticated using (true);
create policy "public read form_corpus_stats" on public.form_corpus_stats
for select to anon, authenticated using (true);
create policy "public read senses" on public.senses
for select to anon, authenticated using (true);
create policy "public read sense_translations" on public.sense_translations
for select to anon, authenticated using (true);
create policy "public read examples" on public.examples
for select to anon, authenticated using (true);
create policy "public read example_translations" on public.example_translations
for select to anon, authenticated using (true);
create policy "public read lemma_relations" on public.lemma_relations
for select to anon, authenticated using (true);
create policy "public read sense_relations" on public.sense_relations
for select to anon, authenticated using (true);

grant usage on schema public to anon, authenticated;
grant select on all tables in schema public to anon, authenticated;
