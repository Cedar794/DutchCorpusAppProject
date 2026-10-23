create table if not exists public.bilingual_gap_repair_audit (
 id bigserial primary key,run_key text not null,chunk text not null,
 sense_id bigint not null references public.senses(id),review_key text not null,
 action text not null check(action in ('correct','keep')),
 proposal jsonb not null,before_state jsonb not null,after_state jsonb not null,
 created_at timestamptz not null default now(),unique(run_key,chunk,sense_id)
);
create table if not exists public.bilingual_gap_repair_batches (
 run_key text not null,chunk text not null,result jsonb not null,
 created_at timestamptz not null default now(),primary key(run_key,chunk)
);
alter table public.bilingual_gap_repair_audit enable row level security;
alter table public.bilingual_gap_repair_batches enable row level security;
revoke all on public.bilingual_gap_repair_audit,public.bilingual_gap_repair_batches from anon,authenticated;
