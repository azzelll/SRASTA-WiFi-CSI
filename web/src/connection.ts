import { createClient } from '@supabase/supabase-js';
import type { CommandReceipt, Device, Snapshot } from './types';

export const accessMode = import.meta.env.VITE_ACCESS_MODE || 'local';
export const publicAccess = accessMode === 'public';
export const remoteAccess = publicAccess || accessMode === 'cloud';
const cloudUrl = import.meta.env.VITE_SUPABASE_URL || '';
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || '';
export function isPublishableKey(key:string):boolean {
 if(key.startsWith('sb_publishable_')) return true;
 try {return JSON.parse(atob(key.split('.')[1])).role==='anon';} catch {return false;}
}
export const cloudConfigured = remoteAccess && /^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(cloudUrl) && isPublishableKey(publishableKey);
export const cloud = cloudConfigured ? createClient(cloudUrl,publishableKey,publicAccess ? {
 auth:{persistSession:false,autoRefreshToken:false,detectSessionInUrl:false},
} : undefined) : null;

export async function localSnapshot():Promise<Snapshot> {
 const response = await fetch('/api/caregiver',{cache:'no-store'});
 if(!response.ok) throw new Error('Edge belum merespons.');
 return response.json();
}
export async function listDevices():Promise<Device[]> {
 if(!cloud) return [];
 const {data,error} = publicAccess
  ? await cloud.rpc('list_public_devices')
  : await cloud.from('devices').select('id,label').order('label');
 if(error) throw new Error('Daftar perangkat belum dapat dimuat.');
 return data || [];
}
export async function remoteSnapshot(deviceId:string):Promise<Snapshot|null> {
 if(!cloud) throw new Error('Cloud belum dikonfigurasi.');
 const {data,error} = await cloud.from('device_status').select('snapshot,received_at').eq('device_id',deviceId).maybeSingle();
 if(error) throw new Error('Status cloud belum dapat dimuat.');
 // Freshness is checked from the edge timestamp, not from time of this read.
 return data?.snapshot || null;
}
export async function commands(deviceId:string):Promise<CommandReceipt[]> {
 if(!cloud) return [];
 const {data,error} = await cloud.from('caregiver_commands').select('id,event_uid,action,status,applied_at_s').eq('device_id',deviceId).order('created_at',{ascending:false}).limit(30);
 if(error) throw new Error('Konfirmasi edge belum dapat dimuat.');
 return data || [];
}
export async function remoteState(deviceId:string):Promise<{snapshot:Snapshot|null;receipts:CommandReceipt[]}> {
 if(publicAccess) {
  if(!cloud) throw new Error('Cloud belum dikonfigurasi.');
  const {data,error}=await cloud.rpc('read_public_dashboard',{p_device_id:deviceId});
  if(error || !data) throw new Error('Dashboard perangkat belum tersedia.');
  return data;
 }
 const [snapshot,receipts]=await Promise.all([remoteSnapshot(deviceId),commands(deviceId)]);
 return {snapshot,receipts};
}
export async function sendCommand(deviceId:string,eventUid:string,action:'acknowledge'|'assistance',id:string):Promise<CommandReceipt> {
 if(remoteAccess) {
  if(!cloud) throw new Error('Cloud belum dikonfigurasi.');
  const {data,error} = await cloud.rpc(publicAccess ? 'request_public_caregiver_command' : 'request_caregiver_command',{p_id:id,p_device_id:deviceId,p_event_uid:eventUid,p_action:action});
  if(error) throw new Error('Perintah belum terkirim. Periksa koneksi dan hak akses.');
  return data;
 }
 const response=await fetch('/api/commands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,event_uid:eventUid,action,expires_at_s:Date.now()/1000+120})});
 if(!response.ok) throw new Error('Edge belum menerima perintah.');
 return response.json();
}

export async function enablePush(deviceId:string):Promise<string> {
 if(!('Notification' in window) || !('serviceWorker' in navigator)) return 'Browser belum mendukung notifikasi. Pada iPhone, pasang app ke Home Screen dahulu.';
 const permission=await Notification.requestPermission();
 if(permission!=='granted') return 'Notifikasi belum diizinkan. Ubah melalui pengaturan browser.';
 if(!remoteAccess) return 'Notifikasi saat app terbuka aktif. Push jarak jauh tersedia setelah cloud terhubung.';
 if(!cloud || !deviceId || !import.meta.env.VITE_VAPID_PUBLIC_KEY) return 'Push belum dikonfigurasi untuk perangkat ini.';
 const registration=await navigator.serviceWorker.ready;
 if(!('pushManager' in registration)) return 'Push belum didukung browser ini.';
 const key=import.meta.env.VITE_VAPID_PUBLIC_KEY.replace(/-/g,'+').replace(/_/g,'/');
 const bytes=Uint8Array.from(atob(key.padEnd(Math.ceil(key.length/4)*4,'=')),c=>c.charCodeAt(0));
 const subscription=await registration.pushManager.getSubscription() || await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes});
 const {error}=await cloud.rpc(publicAccess ? 'register_public_push_subscription' : 'register_push_subscription',{p_device_id:deviceId,p_subscription:subscription.toJSON()});
 if(error) throw new Error('Langganan push belum tersimpan.');
 return 'Push aktif pada perangkat ini.';
}
