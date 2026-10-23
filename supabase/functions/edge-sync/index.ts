import { createClient } from 'npm:@supabase/supabase-js@2.117.2';
import webpush from 'npm:web-push@3.6.7';
import { payload } from './contract.ts';
declare const EdgeRuntime: {waitUntil(promise:Promise<unknown>):void};

function backendKey():string {
 const explicit=Deno.env.get('SRASTA_SUPABASE_SECRET_KEY');
 if(explicit) return explicit;
 // Supabase injects its backend keys into the function environment. None of
 // these keys is returned to the edge device or browser.
 const keys=Deno.env.get('SUPABASE_SECRET_KEYS');
 if(keys) {try {const value=JSON.parse(keys).default;if(typeof value==='string' && value) return value;} catch { /* Legacy projects use the injected service-role key. */ }}
 const legacy=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
 if(legacy) return legacy;
 throw new Error('Backend database credential is not configured');
}
const database=createClient(Deno.env.get('SUPABASE_URL')!,backendKey(),{auth:{persistSession:false,autoRefreshToken:false}});
const json=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});

// Browser-provided URLs must never create an SSRF path for the push sender.
function allowedPushEndpoint(value:string):boolean {
 try {const url=new URL(value);return url.protocol==='https:' && !url.username && !url.password && (url.hostname==='fcm.googleapis.com' || url.hostname==='updates.push.services.mozilla.com' || url.hostname==='web.push.apple.com' || url.hostname.endsWith('.notify.windows.com'));} catch {return false;}
}
async function deliverPush(deviceId:string) {
 const publicKey=Deno.env.get('VAPID_PUBLIC_KEY'),privateKey=Deno.env.get('VAPID_PRIVATE_KEY'),subject=Deno.env.get('VAPID_SUBJECT');
 if(!publicKey || !privateKey || !subject) return;
 const {data,error}=await database.rpc('pending_push_jobs',{p_device_id:deviceId});
 if(error) return;
 for(const job of data || []) {
  let sent=false;
  try {
   if(!allowedPushEndpoint(job.subscription.endpoint)) continue;
   await webpush.sendNotification(job.subscription,JSON.stringify({device_id:job.device_id,event_uid:job.event_uid,state:job.state,simulation:job.simulation}),{TTL:120,urgency:'high',timeout:4000,vapidDetails:{subject,publicKey,privateKey}});
   sent=true;
  } catch { /* Outbox retry on the next edge heartbeat; never log subscriptions. */ }
  finally {await database.rpc('finish_push_job',{p_device_id:deviceId,p_event_uid:job.event_uid,p_subscription_id:job.subscription_id,p_sent:sent});}
 }
}

Deno.serve(async request=>{
 if(request.method!=='POST') return json({error:'method_not_allowed'},405);
 if(Number(request.headers.get('content-length') || 0)>524288) return json({error:'payload_too_large'},413);
 const token=request.headers.get('x-srasta-device-token') || '';
 if(token.length<32 || token.length>256) return json({error:'unauthorized'},401);
 try {
  const body=await request.text();
  if(body.length>524288) return json({error:'payload_too_large'},413);
  const input=payload.safeParse(JSON.parse(body));
  if(!input.success) return json({error:'invalid_summary_contract'},400);
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(token))),byte=>byte.toString(16).padStart(2,'0')).join('');
  const {device_id,snapshot,events,receipts}=input.data;
  const {data,error}=await database.rpc('edge_ingest',{p_device_id:device_id,p_token_sha256:hash,p_snapshot:snapshot,p_events:events,p_receipts:receipts});
  if(error) return json({error:'sync_rejected'},403);
  // Push delivery cannot delay the edge receipt transaction.
  EdgeRuntime.waitUntil(deliverPush(device_id));
  return json(data);
 } catch {return json({error:'invalid_request'},400);}
});
