-- Preserve invalid observed mappings while excluding them from normal lookup.
alter table public.forms add column if not exists is_active boolean not null default true;

-- Multiword entries retain their relation to an existing graded lemma/sense.
-- Productive constructions and usage notes are explicitly separate from lexicalized expressions.
create table if not exists public.lexical_expressions (
  id bigserial primary key,
  lemma_id bigint not null references public.lemmas(id),
  lemma_pos_entry_id bigint not null references public.lemma_pos_entries(id),
  sense_id bigint not null references public.senses(id),
  entry_kind text not null check (entry_kind in ('lexical_expression','usage_construction','definition_note','usage_example')),
  expression_type text not null,
  expression_nl text not null,
  expression_norm text not null,
  definition_nl text not null,
  usage_note text not null,
  gloss_en text not null,
  explanation_en text not null,
  gloss_zh text not null,
  explanation_zh text not null,
  example_nl text not null,
  example_zh text not null,
  source_id bigint not null references public.sources(id),
  external_id text not null,
  confidence numeric(4,3) not null check (confidence between 0 and 0.9),
  review_status text not null default 'needs_review' check (review_status in ('needs_review','accepted','rejected')),
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_id, external_id)
);
create index if not exists lexical_expressions_lemma_idx on public.lexical_expressions(lemma_id);
alter table public.lexical_expressions enable row level security;
drop policy if exists "public read researched expressions" on public.lexical_expressions;
create policy "public read researched expressions" on public.lexical_expressions
  for select to anon, authenticated using (review_status <> 'rejected');
grant select on public.lexical_expressions to anon, authenticated;

create table if not exists public.source_gap_research_audit (
  id bigserial primary key, run_key text not null, batch text not null, target_id text not null,
  plan_key text not null, before_state jsonb not null, after_state jsonb not null,
  decision jsonb not null, created_at timestamptz not null default now(),
  unique (run_key,target_id)
);
create table if not exists public.source_gap_research_batches (
  run_key text not null,batch text not null,plan_key text not null,result jsonb not null,
  created_at timestamptz not null default now(),primary key(run_key,batch)
);
alter table public.source_gap_research_audit enable row level security;
alter table public.source_gap_research_batches enable row level security;
revoke all on public.source_gap_research_audit, public.source_gap_research_batches from anon, authenticated;
