-- Search, detail and index construction must use the same reviewed translation.
create or replace function public.match_senses(
  query_embedding extensions.vector(1024),
  match_count integer default 50,
  active_index_version text default null
)
returns table (
  sense_id bigint, lemma_id bigint, lemma text, level smallint,
  definition_nl text, translation_zh text, translation_en text,
  frequency bigint, distance double precision, similarity double precision
)
language sql stable
as $$
  select s.id, s.lemma_id, l.lemma, l.level,
    coalesce(nullif(btrim(s.display_definition_nl), ''), s.definition_nl, ''),
    coalesce(zh.gloss, ''), coalesce(en.gloss, ''),
    coalesce(l.cc100_freq, l.subtlex_freq, 0),
    (se.embedding <=> query_embedding)::double precision,
    (1.0 - (se.embedding <=> query_embedding))::double precision
  from public.sense_embeddings se
  join public.senses s on s.id=se.sense_id
  join public.lemmas l on l.id=s.lemma_id
  left join lateral (
    select t.gloss from public.sense_translations t
    where t.sense_id=s.id and t.lang='zh' and t.review_status<>'rejected' and btrim(t.gloss)<>''
    order by case t.review_status when 'accepted' then 0 when 'needs_review' then 1 else 2 end,
      t.confidence desc nulls last, t.id desc limit 1
  ) zh on true
  left join lateral (
    select t.gloss from public.sense_translations t
    where t.sense_id=s.id and t.lang='en' and t.review_status<>'rejected' and btrim(t.gloss)<>''
    order by case t.review_status when 'accepted' then 0 when 'needs_review' then 1 else 2 end,
      t.confidence desc nulls last, t.id desc limit 1
  ) en on true
  where s.merged_into_sense_id is null and s.review_status<>'rejected'
    and l.review_status='accepted' and se.index_version not like 'stale:%'
    and (active_index_version is null or se.index_version=active_index_version)
  order by se.embedding <=> query_embedding
  limit least(greatest(match_count, 1), 250);
$$;
alter function public.match_senses(extensions.vector(1024), integer, text)
set search_path = public, extensions, pg_temp;
