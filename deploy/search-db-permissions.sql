-- Run as postgres after restoration. Set login passwords separately using \password.
-- Rerunnable; service has no write access to lexicon/embedding content.
do $$ begin
  if not exists(select from pg_roles where rolname='search_service_user') then
    create role search_service_user login;
  end if;
  if not exists(select from pg_roles where rolname='search_indexer') then
    create role search_indexer login;
  end if;
end $$;
grant usage on schema public, extensions to search_service_user, search_indexer;
grant select on public.lemmas, public.forms, public.form_corpus_stats,
  public.senses, public.sense_translations, public.lemma_relations,
  public.sense_relations, public.sense_embeddings, public.lexical_expressions,
  public.pos_tags, public.lemma_pos_entries, public.examples,
  public.example_translations, public.lemma_examples, public.sources to search_service_user;
grant insert on public.search_query_logs to search_service_user;
grant usage on sequence public.search_query_logs_id_seq to search_service_user;
grant execute on function public.match_senses(extensions.vector, integer, text) to search_service_user;
grant select on public.lemmas, public.lemma_pos_entries, public.senses,
  public.sense_translations, public.sense_embeddings to search_indexer;
grant insert, update on public.sense_embeddings to search_indexer;
grant usage on sequence public.sense_embeddings_id_seq to search_indexer;
drop policy if exists search_service_embeddings on public.sense_embeddings;
create policy search_service_embeddings on public.sense_embeddings for select to search_service_user using (true);
drop policy if exists search_service_logs on public.search_query_logs;
create policy search_service_logs on public.search_query_logs for insert to search_service_user with check (true);
drop policy if exists search_indexer_embeddings on public.sense_embeddings;
create policy search_indexer_embeddings on public.sense_embeddings to search_indexer using (true) with check (true);
-- Supabase's existing read policies target anon/authenticated only.
-- Explicit policies are required for these independent least-privilege logins.
do $$
declare table_name text;
begin
  foreach table_name in array array['lemmas','forms','form_corpus_stats','senses',
      'sense_translations','lemma_relations','sense_relations','pos_tags',
      'lemma_pos_entries','examples','example_translations','lemma_examples','sources'] loop
    execute format('drop policy if exists search_service_read on public.%I', table_name);
    execute format('create policy search_service_read on public.%I for select to search_service_user using (true)', table_name);
  end loop;
  foreach table_name in array array['lemmas','lemma_pos_entries','senses','sense_translations'] loop
    execute format('drop policy if exists search_indexer_read on public.%I', table_name);
    execute format('create policy search_indexer_read on public.%I for select to search_indexer using (true)', table_name);
  end loop;
end $$;
drop policy if exists search_service_expression_read on public.lexical_expressions;
create policy search_service_expression_read on public.lexical_expressions
  for select to search_service_user using (review_status <> 'rejected');
revoke execute on function public.match_senses(extensions.vector, integer, text) from public;
