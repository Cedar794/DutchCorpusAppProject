-- Preserve individual review decisions and before/after images, not public content.
create table if not exists public.human_review_audit (
  run_key text not null,
  action_key text not null,
  manifest_hash text not null,
  proposal jsonb not null,
  before_state jsonb not null,
  after_state jsonb not null,
  created_at timestamptz not null default now(),
  primary key (run_key, action_key)
);
alter table public.human_review_audit enable row level security;
revoke all on public.human_review_audit from anon, authenticated;
