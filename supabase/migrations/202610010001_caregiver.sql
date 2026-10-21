-- Summary-only cloud contract. Provision membership and hashed device tokens
-- from the owner/admin console; neither is writable by browser clients.
create schema if not exists srasta_private;
revoke all on schema srasta_private from public, anon, authenticated;

create table public.devices (id uuid primary key, label text not null check(length(label)<=80));
create table public.device_members (device_id uuid references public.devices on delete cascade, user_id uuid references auth.users on delete cascade, primary key(device_id,user_id));
create table srasta_private.device_secrets (device_id uuid primary key references public.devices on delete cascade, token_sha256 text not null check(token_sha256 ~ '^[0-9a-f]{64}$'));
create table public.device_status (device_id uuid primary key references public.devices on delete cascade, snapshot jsonb not null, received_at timestamptz not null default now());
create table public.care_events (device_id uuid references public.devices on delete cascade, event_uid uuid not null, timestamp_s double precision not null, state text not null, confidence double precision not null, motion_energy double precision not null, evidence text not null, acknowledged_at_s double precision, ack_source text, primary key(device_id,event_uid));
create table public.caregiver_commands (id uuid primary key, device_id uuid not null references public.devices on delete cascade, event_uid uuid not null, action text not null check(action in ('acknowledge','assistance')), status text not null default 'pending' check(status in ('pending','applied','expired','rejected')), created_by uuid not null references auth.users, created_at timestamptz not null default now(), expires_at_s double precision not null default extract(epoch from now()+interval '2 minutes'), applied_at_s double precision, foreign key(device_id,event_uid) references public.care_events);
create table public.push_subscriptions (id uuid primary key default gen_random_uuid(), device_id uuid not null references public.devices on delete cascade, user_id uuid not null references auth.users on delete cascade, endpoint text not null, subscription jsonb not null, unique(device_id,user_id,endpoint));
create table srasta_private.push_jobs (device_id uuid not null, event_uid uuid not null, subscription_id uuid not null references public.push_subscriptions on delete cascade, sent_at timestamptz, leased_until timestamptz, attempts integer not null default 0, created_at timestamptz not null default now(), primary key(device_id,event_uid,subscription_id));

alter table public.devices enable row level security;
alter table public.device_members enable row level security;
alter table public.device_status enable row level security;
alter table public.care_events enable row level security;
alter table public.caregiver_commands enable row level security;
alter table public.push_subscriptions enable row level security;
revoke all on public.devices,public.device_members,public.device_status,public.care_events,public.caregiver_commands,public.push_subscriptions from anon,authenticated;
grant select on public.devices,public.device_members,public.device_status,public.care_events,public.caregiver_commands,public.push_subscriptions to authenticated;
grant all on public.devices,public.device_members,public.device_status,public.care_events,public.caregiver_commands,public.push_subscriptions to service_role;
create policy own_memberships on public.device_members for select to authenticated using(user_id=(select auth.uid()));
create policy assigned_devices on public.devices for select to authenticated using(exists(select 1 from public.device_members m where m.device_id=id and m.user_id=(select auth.uid())));
create policy assigned_status on public.device_status for select to authenticated using(exists(select 1 from public.device_members m where m.device_id=device_status.device_id and m.user_id=(select auth.uid())));
create policy assigned_events on public.care_events for select to authenticated using(exists(select 1 from public.device_members m where m.device_id=care_events.device_id and m.user_id=(select auth.uid())));
create policy assigned_commands on public.caregiver_commands for select to authenticated using(exists(select 1 from public.device_members m where m.device_id=caregiver_commands.device_id and m.user_id=(select auth.uid())));
create policy own_push on public.push_subscriptions for select to authenticated using(user_id=(select auth.uid()) and exists(select 1 from public.device_members m where m.device_id=push_subscriptions.device_id and m.user_id=(select auth.uid())));

create function public.request_caregiver_command(p_id uuid,p_device_id uuid,p_event_uid uuid,p_action text) returns jsonb language plpgsql security definer set search_path='' as $$
declare result public.caregiver_commands;
begin
 if auth.uid() is null or not exists(select 1 from public.device_members where device_id=p_device_id and user_id=auth.uid()) then raise exception 'not authorized'; end if;
 if p_action not in ('acknowledge','assistance') or not exists(select 1 from public.care_events where device_id=p_device_id and event_uid=p_event_uid and state in ('inactive','anomaly','critical','suspected_fall','confirmed_fall')) then raise exception 'invalid action or event'; end if;
 insert into public.caregiver_commands(id,device_id,event_uid,action,created_by) values(p_id,p_device_id,p_event_uid,p_action,auth.uid()) on conflict(id) do nothing;
 select * into result from public.caregiver_commands where id=p_id and device_id=p_device_id and event_uid=p_event_uid and action=p_action and created_by=auth.uid();
 if result.id is null then raise exception 'command conflict'; end if;
 return to_jsonb(result);
end $$;
revoke all on function public.request_caregiver_command(uuid,uuid,uuid,text) from public,anon;
grant execute on function public.request_caregiver_command(uuid,uuid,uuid,text) to authenticated;

create function public.register_push_subscription(p_device_id uuid,p_subscription jsonb) returns void language plpgsql security definer set search_path='' as $$
begin
 if auth.uid() is null or not exists(select 1 from public.device_members where device_id=p_device_id and user_id=auth.uid()) then raise exception 'not authorized'; end if;
 if octet_length(p_subscription::text)>8192 or p_subscription->>'endpoint' !~ '^https://' or p_subscription#>>'{keys,p256dh}' is null or p_subscription#>>'{keys,auth}' is null then raise exception 'invalid subscription'; end if;
 insert into public.push_subscriptions(device_id,user_id,endpoint,subscription) values(p_device_id,auth.uid(),p_subscription->>'endpoint',p_subscription) on conflict(device_id,user_id,endpoint) do update set subscription=excluded.subscription;
end $$;
revoke all on function public.register_push_subscription(uuid,jsonb) from public,anon;
grant execute on function public.register_push_subscription(uuid,jsonb) to authenticated;

create function public.edge_ingest(p_device_id uuid,p_token_sha256 text,p_snapshot jsonb,p_events jsonb,p_receipts jsonb) returns jsonb language plpgsql security definer set search_path='' as $$
declare e jsonb; r jsonb; pending jsonb;
begin
 if not exists(select 1 from srasta_private.device_secrets where device_id=p_device_id and token_sha256=p_token_sha256) then raise exception 'unauthorized device'; end if;
 for e in select value from jsonb_array_elements(p_events) loop
  insert into public.care_events(device_id,event_uid,timestamp_s,state,confidence,motion_energy,evidence,acknowledged_at_s,ack_source) values(p_device_id,(e->>'event_uid')::uuid,(e->>'timestamp_s')::double precision,e->>'state',(e->>'confidence')::double precision,(e->>'motion_energy')::double precision,e->>'evidence',(e->>'acknowledged_at_s')::double precision,e->>'ack_source')
  on conflict(device_id,event_uid) do update set acknowledged_at_s=coalesce(excluded.acknowledged_at_s,care_events.acknowledged_at_s),ack_source=coalesce(excluded.ack_source,care_events.ack_source);
  if e->>'state' in ('inactive','anomaly','critical','suspected_fall','confirmed_fall') and (e->>'timestamp_s')::double precision>extract(epoch from now()-interval '10 minutes') then
   insert into srasta_private.push_jobs(device_id,event_uid,subscription_id) select p_device_id,(e->>'event_uid')::uuid,id from public.push_subscriptions s where s.device_id=p_device_id and exists(select 1 from public.device_members m where m.device_id=s.device_id and m.user_id=s.user_id)
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

create function public.pending_push_jobs(p_device_id uuid) returns jsonb language sql security definer set search_path='' as $$
 with candidates as (
  select j.device_id,j.event_uid,j.subscription_id from srasta_private.push_jobs j join public.push_subscriptions s on s.id=j.subscription_id
  where j.device_id=p_device_id and j.sent_at is null and j.attempts<5 and j.created_at>now()-interval '10 minutes' and (j.leased_until is null or j.leased_until<now())
   and exists(select 1 from public.device_members m where m.device_id=s.device_id and m.user_id=s.user_id)
  order by j.created_at limit 8 for update of j skip locked
 ), claimed as (
  update srasta_private.push_jobs j set leased_until=now()+interval '60 seconds' from candidates c
  where j.device_id=c.device_id and j.event_uid=c.event_uid and j.subscription_id=c.subscription_id returning j.*
 )
 select coalesce(jsonb_agg(jsonb_build_object('device_id',j.device_id,'event_uid',j.event_uid,'subscription_id',j.subscription_id,'subscription',s.subscription,'simulation',e.evidence like 'demo%' or e.evidence like 'replay%')),'[]') from claimed j join public.push_subscriptions s on s.id=j.subscription_id join public.care_events e on e.device_id=j.device_id and e.event_uid=j.event_uid;
$$;
create function public.finish_push_job(p_device_id uuid,p_event_uid uuid,p_subscription_id uuid,p_sent boolean) returns void language sql security definer set search_path='' as $$
 update srasta_private.push_jobs set attempts=attempts+1,sent_at=case when p_sent then now() else null end,leased_until=case when p_sent then null else now()+make_interval(secs=>least(160,10*power(2,attempts))::integer) end where device_id=p_device_id and event_uid=p_event_uid and subscription_id=p_subscription_id and sent_at is null;
$$;
revoke all on function public.pending_push_jobs(uuid),public.finish_push_job(uuid,uuid,uuid,boolean) from public,anon,authenticated;
grant execute on function public.pending_push_jobs(uuid),public.finish_push_job(uuid,uuid,uuid,boolean) to service_role;
alter publication supabase_realtime add table public.device_status;
