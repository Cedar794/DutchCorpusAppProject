-- Entry examples load translations in bounded batches by example_id.
create index if not exists example_translations_example_id_idx
  on public.example_translations (example_id);
