create table if not exists public.gap_source_extras_audit (
 id bigserial primary key,run_key text not null,kind text not null,target_id bigint not null,
 before_state jsonb not null,after_state jsonb not null,proposal jsonb not null,
 created_at timestamptz not null default now(),unique(run_key,kind,target_id)
);
alter table public.gap_source_extras_audit enable row level security;
revoke all on public.gap_source_extras_audit from anon,authenticated;
