alter function public.set_updated_at()
set search_path = public, extensions, pg_temp;

alter function public.match_senses(extensions.vector(1024), integer, text)
set search_path = public, extensions, pg_temp;
