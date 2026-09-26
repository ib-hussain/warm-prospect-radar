-- Upgrade an earlier scraper-first Warm Prospect Radar database to the
-- central, userless full-workspace schema. Run once, then run functions_v2.sql.

begin;

alter type public.interaction_kind add value if not exists 'post_published';

do $$ begin
  create type public.outreach_channel as enum (
    'email', 'direct_message', 'comment', 'social_post', 'picture', 'other'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.outreach_status as enum (
    'draft', 'pending_approval', 'approved', 'rejected', 'delivered', 'failed'
  );
exception when duplicate_object then null;
end $$;

-- Old RPC overloads depend on user-owned columns and must be removed first.
drop function if exists public.archive_business(uuid, uuid);
drop function if exists public.record_prospect_interaction(
  uuid, public.interaction_kind, uuid, text, text, jsonb
);
alter table public.businesses drop column if exists created_by;
alter table public.businesses drop column if exists updated_by;
alter table public.scrape_runs drop column if exists requested_by;
alter table public.prospect_interactions drop column if exists actor_user_id;
alter table public.audit_events drop column if exists actor_user_id;
drop table if exists public.app_users;

create table if not exists public.workspace_feature_flags (
  id smallint primary key default 1 check (id = 1),
  acquisition_enabled boolean not null default true,
  social_acquisition_enabled boolean not null default true,
  llm_enabled boolean not null default true,
  outreach_enabled boolean not null default true,
  chatbot_enabled boolean not null default true,
  scheduled_refresh_enabled boolean not null default true,
  external_delivery_enabled boolean not null default true,
  updated_at timestamptz not null default now()
);

insert into public.workspace_feature_flags (id)
values (1)
on conflict (id) do nothing;

create table if not exists public.outreach_drafts (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  channel public.outreach_channel not null,
  target text,
  subject text,
  body text not null check (length(body) > 0),
  media_prompt text,
  approval_status public.outreach_status not null default 'draft',
  provider text,
  provider_message_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  reviewed_at timestamptz,
  delivered_at timestamptz,
  archived_at timestamptz
);

create table if not exists public.assistant_exchanges (
  id uuid primary key default gen_random_uuid(),
  question text not null check (length(question) > 0),
  answer text not null check (length(answer) > 0),
  provider text not null default 'deterministic',
  business_ids uuid[] not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists outreach_business_updated_idx
  on public.outreach_drafts (business_id, updated_at desc) where archived_at is null;
create index if not exists outreach_approval_idx
  on public.outreach_drafts (approval_status, updated_at desc) where archived_at is null;
create index if not exists assistant_created_idx
  on public.assistant_exchanges (created_at desc);

alter table public.workspace_feature_flags disable row level security;
alter table public.outreach_drafts disable row level security;
alter table public.assistant_exchanges disable row level security;

revoke all privileges on table
  public.businesses,
  public.business_websites,
  public.business_contacts,
  public.business_social_profiles,
  public.scrape_runs,
  public.business_snapshots,
  public.prospect_interactions,
  public.prospect_score_history,
  public.audit_events,
  public.workspace_feature_flags,
  public.outreach_drafts,
  public.assistant_exchanges
from anon, authenticated;

grant all privileges on table
  public.businesses,
  public.business_websites,
  public.business_contacts,
  public.business_social_profiles,
  public.scrape_runs,
  public.business_snapshots,
  public.prospect_interactions,
  public.prospect_score_history,
  public.audit_events,
  public.workspace_feature_flags,
  public.outreach_drafts,
  public.assistant_exchanges
to service_role;

commit;
