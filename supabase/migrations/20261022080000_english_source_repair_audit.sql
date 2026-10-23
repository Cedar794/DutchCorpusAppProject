create table if not exists public.english_source_repair_audit (
  id bigserial primary key,
  sense_id bigint not null references public.senses(id),
  review_key text not null,
  action text not null check (action in ('reject_mapping','correct')),
  proposal jsonb not null,
  before_state jsonb not null,
  after_state jsonb not null,
  created_at timestamptz not null default now(),
  unique (sense_id, review_key)
);
alter table public.english_source_repair_audit enable row level security;
revoke all on public.english_source_repair_audit from anon, authenticated;
