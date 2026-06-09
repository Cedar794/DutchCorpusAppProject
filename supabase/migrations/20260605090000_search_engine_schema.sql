create extension if not exists vector with schema extensions;

create table if not exists public.sense_embeddings (
  id bigserial primary key,
  sense_id bigint not null references public.senses(id) on delete cascade,
  embedding_model text not null,
  embedding_dim integer not null check (embedding_dim = 1024),
  embedding extensions.vector(1024) not null,
  embedding_text_hash text not null,
  embedding_text_preview text,
  index_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (sense_id, embedding_model, embedding_dim)
);

create index if not exists sense_embeddings_sense_id_idx
  on public.sense_embeddings (sense_id);

create index if not exists sense_embeddings_index_version_idx
  on public.sense_embeddings (index_version);

create index if not exists sense_embeddings_embedding_hnsw_idx
  on public.sense_embeddings
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create table if not exists public.search_query_logs (
  id bigserial primary key,
  query text not null,
  mode text not null check (mode in ('lookup', 'suggest', 'semantic')),
  detected_language text,
  latency_ms integer not null check (latency_ms >= 0),
  candidate_count integer,
  result_count integer not null check (result_count >= 0),
  top_lemma_ids bigint[],
  top_sense_ids bigint[],
  cache_hit boolean not null default false,
  embedding_model text,
  index_version text,
  request_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists search_query_logs_created_at_idx
  on public.search_query_logs (created_at desc);

create index if not exists search_query_logs_mode_created_idx
  on public.search_query_logs (mode, created_at desc);

create table if not exists public.search_benchmark_queries (
  id bigserial primary key,
  query text not null,
  mode text not null check (mode in ('lookup', 'suggest', 'semantic')),
  language text,
  expected_lemma_ids bigint[],
  expected_sense_ids bigint[],
  tags text[] not null default '{}',
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.search_benchmark_runs (
  id uuid primary key default gen_random_uuid(),
  index_version text not null,
  embedding_model text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  metrics jsonb not null default '{}'::jsonb,
  notes text
);

drop trigger if exists sense_embeddings_set_updated_at on public.sense_embeddings;
create trigger sense_embeddings_set_updated_at
before update on public.sense_embeddings
for each row execute function public.set_updated_at();

drop trigger if exists search_benchmark_queries_set_updated_at on public.search_benchmark_queries;
create trigger search_benchmark_queries_set_updated_at
before update on public.search_benchmark_queries
for each row execute function public.set_updated_at();

create or replace function public.match_senses(
  query_embedding extensions.vector(1024),
  match_count integer default 50,
  active_index_version text default null
)
returns table (
  sense_id bigint,
  lemma_id bigint,
  lemma text,
  level smallint,
  definition_nl text,
  translation_zh text,
  translation_en text,
  frequency bigint,
  distance double precision,
  similarity double precision
)
language sql
stable
as $$
  with ranked as (
    select
      s.id as sense_id,
      s.lemma_id,
      l.lemma,
      l.level,
      coalesce(s.display_definition_nl, s.definition_nl, '') as definition_nl,
      max(st_zh.gloss) filter (where st_zh.lang = 'zh') as translation_zh,
      max(st_en.gloss) filter (where st_en.lang = 'en') as translation_en,
      coalesce(l.cc100_freq, l.subtlex_freq, 0) as frequency,
      (se.embedding <=> query_embedding)::double precision as distance
    from public.sense_embeddings se
    join public.senses s on s.id = se.sense_id
    join public.lemmas l on l.id = s.lemma_id
    left join public.sense_translations st_zh
      on st_zh.sense_id = s.id and st_zh.lang = 'zh'
    left join public.sense_translations st_en
      on st_en.sense_id = s.id and st_en.lang = 'en'
    where s.merged_into_sense_id is null
      and (active_index_version is null or se.index_version = active_index_version)
    group by
      s.id,
      s.lemma_id,
      l.lemma,
      l.level,
      s.display_definition_nl,
      s.definition_nl,
      l.cc100_freq,
      l.subtlex_freq,
      se.embedding
    order by se.embedding <=> query_embedding
    limit least(greatest(match_count, 1), 250)
  )
  select
    ranked.sense_id,
    ranked.lemma_id,
    ranked.lemma,
    ranked.level,
    ranked.definition_nl,
    coalesce(ranked.translation_zh, '') as translation_zh,
    coalesce(ranked.translation_en, '') as translation_en,
    ranked.frequency,
    ranked.distance,
    (1.0 - ranked.distance) as similarity
  from ranked
  order by ranked.distance asc;
$$;

alter table public.sense_embeddings enable row level security;
alter table public.search_query_logs enable row level security;
alter table public.search_benchmark_queries enable row level security;
alter table public.search_benchmark_runs enable row level security;

revoke all on public.sense_embeddings from anon, authenticated;
revoke all on public.search_query_logs from anon, authenticated;
revoke all on public.search_benchmark_queries from anon, authenticated;
revoke all on public.search_benchmark_runs from anon, authenticated;
revoke all on function public.match_senses(extensions.vector(1024), integer, text) from public;
grant execute on function public.match_senses(extensions.vector(1024), integer, text) to authenticated;
