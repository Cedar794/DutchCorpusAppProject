-- User-authorized removal of unsupported extreme records, with private recovery data.
create table if not exists public.extreme_record_archives (
  run_key text primary key,
  plan_sha256 text not null,
  payload jsonb not null,
  result jsonb not null,
  created_at timestamptz not null default now()
);
alter table public.extreme_record_archives enable row level security;
revoke all on public.extreme_record_archives from public, anon, authenticated;
