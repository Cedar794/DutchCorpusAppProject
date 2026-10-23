-- Source repair history must not be indexed or returned as live data.
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
      on st_zh.sense_id = s.id and st_zh.lang = 'zh' and st_zh.review_status <> 'rejected'
    left join public.sense_translations st_en
      on st_en.sense_id = s.id and st_en.lang = 'en' and st_en.review_status <> 'rejected'
    where s.merged_into_sense_id is null
      and s.review_status <> 'rejected'
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

alter function public.match_senses(extensions.vector(1024), integer, text)
set search_path = public, extensions, pg_temp;
