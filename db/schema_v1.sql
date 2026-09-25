-- Warm Prospect Radar schema v1
-- Run this file first in the Supabase SQL editor, then run functions_v2.sql.
-- The operational model keeps businesses at the centre with acquisition, contact,
-- social, scoring and interaction tables around it.

create extension if not exists pgcrypto;

do $$ begin
  create type public.social_platform as enum (
    'facebook', 'instagram', 'linkedin', 'x', 'youtube', 'github', 'discord', 'whatsapp', 'other'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.scrape_run_status as enum ('queued', 'running', 'completed', 'partial', 'failed');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.interaction_kind as enum (
    'email_sent', 'message_sent', 'comment_posted', 'reply_received', 'positive_reply', 'negative_reply', 'other'
  );
exception when duplicate_object then null;
end $$;

create table if not exists public.app_users (
  id uuid primary key default gen_random_uuid(),
  display_name text not null,
  email text unique,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.businesses (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  legal_name text,
  description text,
  website text,
  city text,
  region text,
  country_code char(2),
  founded_year integer check (founded_year between 1000 and 2200),
  employee_count bigint check (employee_count >= 0),
  employee_band text,
  gics_sector_code varchar(2) check (
    gics_sector_code is null or gics_sector_code in ('10','15','20','25','30','35','40','45','50','55','60')
  ),
  gics_sector text,
  gics_industry_group_code varchar(4) check (gics_industry_group_code is null or gics_industry_group_code ~ '^[0-9]{4}$'),
  gics_industry_group text,
  gics_industry_code varchar(6) check (gics_industry_code is null or gics_industry_code ~ '^[0-9]{6}$'),
  gics_industry text,
  gics_sub_industry_code varchar(8) check (gics_sub_industry_code is null or gics_sub_industry_code ~ '^[0-9]{8}$'),
  gics_sub_industry text,
  products_services text[] not null default '{}',
  technologies text[] not null default '{}',
  keywords text[] not null default '{}',
  source_urls text[] not null default '{}',
  prospect_likelihood numeric(5,2) not null default 0 check (prospect_likelihood between 0 and 100),
  prospect_score numeric(5,2) not null default 0 check (prospect_score between 0 and 100),
  score_explanation jsonb not null default '{}'::jsonb,
  created_by uuid references public.app_users(id) on delete set null,
  updated_by uuid references public.app_users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);

create table if not exists public.business_websites (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  url text not null,
  label text,
  is_primary boolean not null default false,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  archived_at timestamptz,
  unique (business_id, url)
);

create table if not exists public.business_contacts (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  kind text not null check (kind in ('email', 'phone', 'landline', 'whatsapp', 'address', 'other')),
  value text not null,
  label text,
  source_url text,
  confidence numeric(4,3) not null default 0.8 check (confidence between 0 and 1),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  archived_at timestamptz,
  unique (business_id, kind, value)
);

create table if not exists public.business_social_profiles (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  platform public.social_platform not null,
  url text not null,
  handle text,
  source_url text,
  is_official boolean,
  confidence numeric(4,3) not null default 0.75 check (confidence between 0 and 1),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  archived_at timestamptz,
  unique (business_id, platform, url)
);

create table if not exists public.scrape_runs (
  id uuid primary key default gen_random_uuid(),
  requested_url text not null,
  business_id uuid references public.businesses(id) on delete set null,
  requested_by uuid references public.app_users(id) on delete set null,
  status public.scrape_run_status not null default 'queued',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  pages_attempted integer not null default 0 check (pages_attempted >= 0),
  pages_succeeded integer not null default 0 check (pages_succeeded >= 0),
  renderer_fallbacks integer not null default 0 check (renderer_fallbacks >= 0),
  errors text[] not null default '{}',
  warnings text[] not null default '{}',
  extraction_provider text not null default 'deterministic'
);

create table if not exists public.business_snapshots (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  run_id uuid not null references public.scrape_runs(id) on delete cascade,
  version integer not null check (version > 0),
  source_url text not null,
  structured_data jsonb not null,
  raw_manifest jsonb not null default '{}'::jsonb,
  local_path text,
  storage_object_path text,
  content_hash char(64) not null,
  created_at timestamptz not null default now(),
  unique (business_id, version)
);

create table if not exists public.prospect_interactions (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  actor_user_id uuid references public.app_users(id) on delete set null,
  occurred_at timestamptz not null default now(),
  kind public.interaction_kind not null,
  channel text,
  summary text,
  metadata jsonb not null default '{}'::jsonb,
  archived_at timestamptz
);

create table if not exists public.prospect_score_history (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  prospect_likelihood numeric(5,2) not null check (prospect_likelihood between 0 and 100),
  prospect_score numeric(5,2) not null check (prospect_score between 0 and 100),
  explanation jsonb not null default '{}'::jsonb,
  calculated_at timestamptz not null default now()
);

create table if not exists public.audit_events (
  id uuid primary key default gen_random_uuid(),
  actor_user_id uuid references public.app_users(id) on delete set null,
  entity_type text not null,
  entity_id uuid not null,
  action text not null,
  before_state jsonb,
  after_state jsonb,
  occurred_at timestamptz not null default now()
);

create index if not exists businesses_active_updated_idx on public.businesses (updated_at desc) where archived_at is null;
create index if not exists businesses_name_search_idx on public.businesses using gin (to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(description, '')));
create index if not exists businesses_gics_sector_idx on public.businesses (gics_sector_code) where archived_at is null;
create index if not exists contacts_business_idx on public.business_contacts (business_id) where archived_at is null;
create index if not exists social_business_idx on public.business_social_profiles (business_id) where archived_at is null;
create index if not exists runs_started_idx on public.scrape_runs (started_at desc);
create index if not exists snapshots_business_version_idx on public.business_snapshots (business_id, version desc);
create index if not exists interactions_business_time_idx on public.prospect_interactions (business_id, occurred_at desc) where archived_at is null;

-- The user requested no RLS for the first version. This makes the supplied key's
-- table privileges especially important. Do not expose a service-role key in a browser.
alter table public.app_users disable row level security;
alter table public.businesses disable row level security;
alter table public.business_websites disable row level security;
alter table public.business_contacts disable row level security;
alter table public.business_social_profiles disable row level security;
alter table public.scrape_runs disable row level security;
alter table public.business_snapshots disable row level security;
alter table public.prospect_interactions disable row level security;
alter table public.prospect_score_history disable row level security;
alter table public.audit_events disable row level security;

insert into storage.buckets (id, name, public)
values ('business-snapshots', 'business-snapshots', false)
on conflict (id) do nothing;
