-- Keep the event's severity and device with the leased notification.
create or replace function public.pending_push_jobs(p_device_id uuid) returns jsonb language sql security definer set search_path='' as $$
 with candidates as (
  select j.device_id,j.event_uid,j.subscription_id from srasta_private.push_jobs j join public.push_subscriptions s on s.id=j.subscription_id
  where j.device_id=p_device_id and j.sent_at is null and j.attempts<5 and j.created_at>now()-interval '10 minutes' and (j.leased_until is null or j.leased_until<now())
   and exists(select 1 from public.device_members m where m.device_id=s.device_id and m.user_id=s.user_id)
  order by j.created_at limit 8 for update of j skip locked
 ), claimed as (
  update srasta_private.push_jobs j set leased_until=now()+interval '60 seconds' from candidates c
  where j.device_id=c.device_id and j.event_uid=c.event_uid and j.subscription_id=c.subscription_id returning j.*
 )
 select coalesce(jsonb_agg(jsonb_build_object('device_id',j.device_id,'event_uid',j.event_uid,'state',e.state,'subscription_id',j.subscription_id,'subscription',s.subscription,'simulation',e.evidence like 'demo%' or e.evidence like 'replay%')),'[]') from claimed j join public.push_subscriptions s on s.id=j.subscription_id join public.care_events e on e.device_id=j.device_id and e.event_uid=j.event_uid;
$$;
revoke all on function public.pending_push_jobs(uuid) from public,anon,authenticated;
grant execute on function public.pending_push_jobs(uuid) to service_role;
