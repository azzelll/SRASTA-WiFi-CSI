-- Owner-selected public dashboards. No anonymous table access or device ingest.
create table srasta_private.public_dashboards (
 device_id uuid primary key references public.devices on delete cascade,
 enabled boolean not null default false,
 allow_commands boolean not null default false,
 allow_push boolean not null default false
);
revoke all on srasta_private.public_dashboards from public,anon,authenticated;
grant all on srasta_private.public_dashboards to service_role;

create function public.list_public_devices() returns jsonb language sql stable security definer set search_path='' as $$
 select coalesce(jsonb_agg(jsonb_build_object('id',d.id,'label',d.label) order by d.label),'[]')
 from public.devices d join srasta_private.public_dashboards p on p.device_id=d.id where p.enabled;
$$;

create function public.read_public_dashboard(p_device_id uuid) returns jsonb language sql stable security definer set search_path='' as $$
 select jsonb_build_object('snapshot',s.snapshot,'receipts',coalesce((
  select jsonb_agg(jsonb_build_object('id',c.id,'event_uid',c.event_uid,'action',c.action,'status',c.status,'applied_at_s',c.applied_at_s) order by c.created_at desc)
  from (select id,event_uid,action,status,applied_at_s,created_at from public.caregiver_commands where device_id=p.device_id order by created_at desc limit 30) c
 ),'[]'))
 from srasta_private.public_dashboards p left join public.device_status s on s.device_id=p.device_id
 where p.device_id=p_device_id and p.enabled;
$$;

-- Public actions must not be attributed to an authenticated caregiver.
alter table public.caregiver_commands alter column created_by drop not null;
alter table public.caregiver_commands add column request_origin text not null default 'caregiver';
alter table public.caregiver_commands add constraint command_request_origin check (
 (request_origin='caregiver' and created_by is not null) or
 (request_origin='public_dashboard' and created_by is null)
);

create function public.request_public_caregiver_command(p_id uuid,p_device_id uuid,p_event_uid uuid,p_action text) returns jsonb language plpgsql security definer set search_path='' as $$
declare result public.caregiver_commands;
begin
 if not exists(select 1 from srasta_private.public_dashboards where device_id=p_device_id and enabled and allow_commands) then raise exception 'public actions unavailable'; end if;
 if p_id is null or p_action is null or p_action not in ('acknowledge','assistance') or not exists(select 1 from public.care_events where device_id=p_device_id and event_uid=p_event_uid and state in ('inactive','anomaly','critical','suspected_fall','confirmed_fall')) then raise exception 'invalid action or event'; end if;
 perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('srasta-public-command:'||p_device_id::text));
 select * into result from public.caregiver_commands where id=p_id;
 if found then
  if result.device_id<>p_device_id or result.event_uid<>p_event_uid or result.action<>p_action or result.request_origin<>'public_dashboard' then raise exception 'command conflict'; end if;
 else
  -- Multiple visitors retrying the same action share one pending/applied result.
  select * into result from public.caregiver_commands where device_id=p_device_id and event_uid=p_event_uid and action=p_action and request_origin='public_dashboard' and (status='applied' or (status='pending' and expires_at_s>extract(epoch from now()))) order by created_at desc limit 1;
  if not found then
   if (select count(*) from public.caregiver_commands where device_id=p_device_id and request_origin='public_dashboard' and created_at>now()-interval '1 minute')>=30 then raise exception 'public action rate exceeded'; end if;
   insert into public.caregiver_commands(id,device_id,event_uid,action,created_by,request_origin) values(p_id,p_device_id,p_event_uid,p_action,null,'public_dashboard') returning * into result;
  end if;
 end if;
 return jsonb_build_object('id',result.id,'event_uid',result.event_uid,'action',result.action,'status',result.status,'applied_at_s',result.applied_at_s);
end $$;

-- Keep opt-in browser push available without creating a hidden user account.
alter table public.push_subscriptions alter column user_id drop not null;
create unique index public_push_endpoint on public.push_subscriptions(device_id,endpoint) where user_id is null;

create function public.register_public_push_subscription(p_device_id uuid,p_subscription jsonb) returns void language plpgsql security definer set search_path='' as $$
begin
 if not exists(select 1 from srasta_private.public_dashboards where device_id=p_device_id and enabled and allow_push) then raise exception 'public push unavailable'; end if;
 if p_subscription is null or octet_length(p_subscription::text)>8192 or coalesce(p_subscription->>'endpoint','') !~ '^https://(fcm\.googleapis\.com|updates\.push\.services\.mozilla\.com|web\.push\.apple\.com|[a-z0-9-]+\.notify\.windows\.com)/' or coalesce(p_subscription#>>'{keys,p256dh}','') !~ '^[A-Za-z0-9_-]{64,128}={0,2}$' or coalesce(p_subscription#>>'{keys,auth}','') !~ '^[A-Za-z0-9_-]{16,64}={0,2}$' then raise exception 'invalid subscription'; end if;
 perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('srasta-public-push:'||p_device_id::text));
 if not exists(select 1 from public.push_subscriptions where device_id=p_device_id and user_id is null and endpoint=p_subscription->>'endpoint') and (select count(*) from public.push_subscriptions where device_id=p_device_id and user_id is null)>=64 then raise exception 'public subscription limit exceeded'; end if;
 insert into public.push_subscriptions(device_id,user_id,endpoint,subscription) values(p_device_id,null,p_subscription->>'endpoint',p_subscription)
 on conflict(device_id,endpoint) where user_id is null do update set subscription=excluded.subscription;
end $$;

create function srasta_private.push_recipient_allowed(p_device_id uuid,p_user_id uuid) returns boolean language sql stable security definer set search_path='' as $$
 select case when p_user_id is null then exists(select 1 from srasta_private.public_dashboards where device_id=p_device_id and enabled and allow_push)
 else exists(select 1 from public.device_members where device_id=p_device_id and user_id=p_user_id) end;
$$;
revoke all on function srasta_private.push_recipient_allowed(uuid,uuid) from public,anon,authenticated;

revoke all on function public.list_public_devices(),public.read_public_dashboard(uuid),public.request_public_caregiver_command(uuid,uuid,uuid,text),public.register_public_push_subscription(uuid,jsonb) from public;
grant execute on function public.list_public_devices(),public.read_public_dashboard(uuid),public.request_public_caregiver_command(uuid,uuid,uuid,text),public.register_public_push_subscription(uuid,jsonb) to anon,authenticated,service_role;

-- Existing device authentication, receipts, TTL and push dedup remain unchanged.
create or replace function public.edge_ingest(p_device_id uuid,p_token_sha256 text,p_snapshot jsonb,p_events jsonb,p_receipts jsonb) returns jsonb language plpgsql security definer set search_path='' as $$
declare e jsonb; r jsonb; pending jsonb;
begin
 if not exists(select 1 from srasta_private.device_secrets where device_id=p_device_id and token_sha256=p_token_sha256) then raise exception 'unauthorized device'; end if;
 for e in select value from jsonb_array_elements(p_events) loop
  insert into public.care_events(device_id,event_uid,timestamp_s,state,confidence,motion_energy,evidence,acknowledged_at_s,ack_source) values(p_device_id,(e->>'event_uid')::uuid,(e->>'timestamp_s')::double precision,e->>'state',(e->>'confidence')::double precision,(e->>'motion_energy')::double precision,e->>'evidence',(e->>'acknowledged_at_s')::double precision,e->>'ack_source')
  on conflict(device_id,event_uid) do update set acknowledged_at_s=coalesce(excluded.acknowledged_at_s,care_events.acknowledged_at_s),ack_source=coalesce(excluded.ack_source,care_events.ack_source);
  if e->>'state' in ('inactive','anomaly','critical','suspected_fall','confirmed_fall') and (e->>'timestamp_s')::double precision>extract(epoch from now()-interval '10 minutes') then
   insert into srasta_private.push_jobs(device_id,event_uid,subscription_id) select p_device_id,(e->>'event_uid')::uuid,id from public.push_subscriptions s where s.device_id=p_device_id and srasta_private.push_recipient_allowed(s.device_id,s.user_id)
    and not exists(select 1 from srasta_private.push_jobs j join public.care_events prior on prior.device_id=j.device_id and prior.event_uid=j.event_uid where j.device_id=p_device_id and j.subscription_id=s.id and j.created_at>now()-interval '60 seconds' and (prior.state in ('critical','confirmed_fall'))=(e->>'state' in ('critical','confirmed_fall')) and (prior.evidence like 'demo%' or prior.evidence like 'replay%')=(e->>'evidence' like 'demo%' or e->>'evidence' like 'replay%'))
   on conflict do nothing;
  end if;
 end loop;
 for r in select value from jsonb_array_elements(p_receipts) loop
  update public.caregiver_commands set status=r->>'status',applied_at_s=(r->>'applied_at_s')::double precision where id=(r->>'id')::uuid and device_id=p_device_id and event_uid=(r->>'event_uid')::uuid and action=r->>'action' and status='pending';
 end loop;
 update public.caregiver_commands set status='expired' where device_id=p_device_id and status='pending' and expires_at_s<extract(epoch from now());
 insert into public.device_status(device_id,snapshot) values(p_device_id,p_snapshot) on conflict(device_id) do update set snapshot=excluded.snapshot,received_at=now();
 select coalesce(jsonb_agg(jsonb_build_object('id',id,'event_uid',event_uid,'action',action,'expires_at_s',expires_at_s)),'[]') into pending from (select * from public.caregiver_commands where device_id=p_device_id and status='pending' order by created_at limit 30) c;
 return jsonb_build_object('ok',true,'commands',pending);
end $$;
revoke all on function public.edge_ingest(uuid,text,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.edge_ingest(uuid,text,jsonb,jsonb,jsonb) to service_role;

-- Keep the event's severity and device with the leased notification.
create or replace function public.pending_push_jobs(p_device_id uuid) returns jsonb language sql security definer set search_path='' as $$
 with candidates as (
  select j.device_id,j.event_uid,j.subscription_id from srasta_private.push_jobs j join public.push_subscriptions s on s.id=j.subscription_id
  where j.device_id=p_device_id and j.sent_at is null and j.attempts<5 and j.created_at>now()-interval '10 minutes' and (j.leased_until is null or j.leased_until<now())
   and srasta_private.push_recipient_allowed(s.device_id,s.user_id)
  order by j.created_at limit 8 for update of j skip locked
 ), claimed as (
  update srasta_private.push_jobs j set leased_until=now()+interval '60 seconds' from candidates c
  where j.device_id=c.device_id and j.event_uid=c.event_uid and j.subscription_id=c.subscription_id returning j.*
 )
 select coalesce(jsonb_agg(jsonb_build_object('device_id',j.device_id,'event_uid',j.event_uid,'state',e.state,'subscription_id',j.subscription_id,'subscription',s.subscription,'simulation',e.evidence like 'demo%' or e.evidence like 'replay%')),'[]') from claimed j join public.push_subscriptions s on s.id=j.subscription_id join public.care_events e on e.device_id=j.device_id and e.event_uid=j.event_uid;
$$;
revoke all on function public.pending_push_jobs(uuid) from public,anon,authenticated;
grant execute on function public.pending_push_jobs(uuid) to service_role;
