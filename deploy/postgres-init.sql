-- For an isolated search deployment without Supabase REST/Auth services.
create schema if not exists extensions;
create extension if not exists vector with schema extensions;
create extension if not exists pg_trgm with schema extensions;
create extension if not exists pgcrypto with schema extensions;
create extension if not exists "uuid-ossp" with schema extensions;
-- Existing dump policies refer to these roles; neither can log in.
create role anon nologin;
create role authenticated nologin;
