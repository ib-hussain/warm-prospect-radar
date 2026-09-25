-- Warm Prospect Radar functions v2
-- Run after schema_v1.sql.

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists businesses_set_updated_at on public.businesses;
create trigger businesses_set_updated_at
before update on public.businesses
for each row execute function public.set_updated_at();

drop trigger if exists app_users_set_updated_at on public.app_users;
create trigger app_users_set_updated_at
before update on public.app_users
for each row execute function public.set_updated_at();

create or replace function public.archive_business(
  p_business_id uuid,
  p_actor_user_id uuid default null
)
returns boolean
language plpgsql
as $$
declare
  previous_row jsonb;
begin
  select to_jsonb(b) into previous_row
  from public.businesses b
  where b.id = p_business_id and b.archived_at is null
  for update;

  if previous_row is null then
    return false;
  end if;

  update public.businesses set archived_at = now(), updated_by = p_actor_user_id where id = p_business_id;
  update public.business_websites set archived_at = now() where business_id = p_business_id and archived_at is null;
  update public.business_contacts set archived_at = now() where business_id = p_business_id and archived_at is null;
  update public.business_social_profiles set archived_at = now() where business_id = p_business_id and archived_at is null;

  insert into public.audit_events (actor_user_id, entity_type, entity_id, action, before_state, after_state)
  select p_actor_user_id, 'business', p_business_id, 'archive', previous_row, to_jsonb(b)
  from public.businesses b where b.id = p_business_id;
  return true;
end;
$$;

create or replace function public.business_score_components(p_business_id uuid)
returns table (
  prospect_likelihood numeric,
  prospect_score numeric,
  explanation jsonb
)
language sql
stable
as $$
with base as (
  select
    b.*,
    (select count(*) from public.business_contacts c where c.business_id = b.id and c.archived_at is null) as contact_count,
    (select count(*) from public.business_social_profiles s where s.business_id = b.id and s.archived_at is null) as social_count,
    (select count(*) from public.prospect_interactions i where i.business_id = b.id and i.archived_at is null and i.kind in ('email_sent','message_sent','comment_posted')) as attempts,
    (select count(*) from public.prospect_interactions i where i.business_id = b.id and i.archived_at is null and i.kind in ('reply_received','positive_reply','negative_reply')) as replies,
    (select count(*) from public.prospect_interactions i where i.business_id = b.id and i.archived_at is null and i.kind = 'positive_reply') as positive_replies
  from public.businesses b where b.id = p_business_id
), components as (
  select *,
    case
      when employee_count is null then 50.0
      when employee_count <= 1 then 95.0
      else greatest(5.0, least(95.0, 100.0 - greatest(0.0, log(10, employee_count::numeric) - 1.0) * 18.0))
    end as size_accessibility,
    least(100.0,
      15.0 +
      case when website is not null then 15.0 else 0.0 end +
      least(35.0, contact_count * 14.0) +
      least(25.0, social_count * 5.0) +
      case when city is not null or country_code is not null then 10.0 else 0.0 end
    ) as contactability,
    case when attempts = 0 then 0.0 else
      least(100.0,
        ((replies::numeric / attempts) * 70.0 + (positive_replies::numeric / attempts) * 30.0) *
        (0.5 + 0.5 * least(1.0, log(2, attempts + 1) / 4.0))
      )
    end as response_strength,
    (
      (case when name is not null then 1 else 0 end) +
      (case when description is not null then 1 else 0 end) +
      (case when website is not null then 1 else 0 end) +
      (case when country_code is not null then 1 else 0 end) +
      (case when employee_count is not null then 1 else 0 end) +
      (case when gics_sector is not null or gics_sector_code is not null then 1 else 0 end) +
      (case when contact_count > 0 then 1 else 0 end) +
      (case when social_count > 0 then 1 else 0 end) +
      (case when cardinality(products_services) > 0 then 1 else 0 end) +
      (case when cardinality(source_urls) > 0 then 1 else 0 end)
    ) * 10.0 as completeness
  from base
), final as (
  select *,
    least(100.0, greatest(0.0, size_accessibility * 0.80 + contactability * 0.20)) as likelihood
  from components
)
select
  round(likelihood, 2),
  round(least(100.0, greatest(0.0, response_strength * 0.65 + (100.0 - likelihood) * 0.25 + completeness * 0.10)), 2),
  jsonb_build_object(
    'size_accessibility', round(size_accessibility, 2),
    'contactability', round(contactability, 2),
    'response_strength', round(response_strength, 2),
    'difficulty_value', round(100.0 - likelihood, 2),
    'data_completeness', round(completeness, 2),
    'attempts', attempts,
    'replies', replies,
    'positive_replies', positive_replies,
    'formula', 'response 65% + difficulty 25% + completeness 10%'
  )
from final;
$$;

create or replace function public.refresh_business_score(p_business_id uuid)
returns void
language plpgsql
as $$
declare
  calculated record;
begin
  select * into calculated from public.business_score_components(p_business_id);
  if calculated is null then
    return;
  end if;
  update public.businesses
  set prospect_likelihood = calculated.prospect_likelihood,
      prospect_score = calculated.prospect_score,
      score_explanation = calculated.explanation
  where id = p_business_id;
  insert into public.prospect_score_history (
    business_id, prospect_likelihood, prospect_score, explanation
  ) values (
    p_business_id, calculated.prospect_likelihood, calculated.prospect_score, calculated.explanation
  );
end;
$$;

create or replace function public.record_prospect_interaction(
  p_business_id uuid,
  p_kind public.interaction_kind,
  p_actor_user_id uuid default null,
  p_channel text default null,
  p_summary text default null,
  p_metadata jsonb default '{}'::jsonb
)
returns uuid
language plpgsql
as $$
declare
  new_id uuid;
begin
  insert into public.prospect_interactions (
    business_id, actor_user_id, kind, channel, summary, metadata
  ) values (
    p_business_id, p_actor_user_id, p_kind, p_channel, p_summary, p_metadata
  ) returning id into new_id;
  perform public.refresh_business_score(p_business_id);
  return new_id;
end;
$$;

create or replace function public.dashboard_summary()
returns jsonb
language sql
stable
as $$
select jsonb_build_object(
  'businesses', (select count(*) from public.businesses where archived_at is null),
  'runs_24h', (select count(*) from public.scrape_runs where started_at >= now() - interval '24 hours'),
  'successful_runs_24h', (select count(*) from public.scrape_runs where started_at >= now() - interval '24 hours' and status in ('completed','partial')),
  'average_completeness', (
    select coalesce(round(avg((score_explanation->>'data_completeness')::numeric), 1), 0)
    from public.businesses where archived_at is null
  ),
  'updated_at', now()
);
$$;

create or replace view public.business_radar as
select
  b.*,
  (select count(*) from public.business_contacts c where c.business_id = b.id and c.archived_at is null) as contact_count,
  (select count(*) from public.business_social_profiles s where s.business_id = b.id and s.archived_at is null) as social_profile_count,
  (select count(*) from public.business_snapshots sn where sn.business_id = b.id) as snapshot_count,
  (select max(r.started_at) from public.scrape_runs r where r.business_id = b.id) as last_scraped_at
from public.businesses b
where b.archived_at is null;

