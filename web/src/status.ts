import type { CareEvent, Snapshot, SystemState } from './types';
export const states: Record<SystemState,{label:string;description:string}> = {
 standby:{label:'Siaga',description:'Belum ada keberadaan orang yang terkonfirmasi.'},
 normal:{label:'Aktivitas normal',description:'Terus pantau aktivitas dan kondisi terkini.'},
 inactive:{label:'Tidak aktif',description:'Tidak ada gerakan melewati batas waktu. Periksa kondisi.'},
 anomaly:{label:'Perlu perhatian',description:'Ada indikasi anomali. Periksa kondisi dan hasil validasi.'},
 critical:{label:'Kondisi kritis',description:'Segera periksa kondisi dan siapkan bantuan.'},
};
export function eventState(state:string):SystemState {return state==='confirmed_fall'?'critical':state==='suspected_fall'?'anomaly':state in states?state as SystemState:'normal';}
export function isAlert(event:CareEvent):boolean {return ['inactive','anomaly','critical','suspected_fall','confirmed_fall'].includes(event.state);}
export function isFresh(snapshot:Snapshot|null, receivedAt:number, now:number):boolean {
 if(!snapshot || now-receivedAt>10000 || now/1000-snapshot.updated_at_s>15 || snapshot.updated_at_s-now/1000>30) return false;
 return snapshot.source==='simulator' || (snapshot.source==='live' && snapshot.monitoring_online && snapshot.state_verified && snapshot.observed_at_s!==null && now/1000-snapshot.observed_at_s<10);
}
export function formatTime(seconds:number|null):string {return seconds && seconds>1_000_000_000?new Date(seconds*1000).toLocaleString('id-ID',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'Waktu belum tersedia';}
export function eventSource(event:CareEvent):string {return event.evidence.startsWith('demo')?'Simulasi':event.evidence.startsWith('replay')?'Replay':'Edge AI';}

export function cameraNote(camera:Snapshot['camera']|undefined,event:CareEvent):string {
 if(event.evidence.startsWith('demo') || event.evidence.startsWith('replay')) return 'Validasi kamera tidak dijalankan pada simulasi atau replay.';
 const validation=camera?.validations?.find(row=>row.event_uid===event.event_uid);
 if(validation) return `${validation.result} · ${formatTime(validation.checked_at_s)}`;
 if(camera?.active && camera.event_uid===event.event_uid) return 'Validasi postur sedang berjalan.';
 return camera?.available?'Belum ada hasil validasi kamera untuk kejadian ini.':'Validasi kamera belum tersedia.';
}

export function receiverStatus(snapshot:Snapshot|null,active:boolean):{ok:boolean;value:string} {
 if(snapshot?.source==='simulator') return {ok:false,value:'Tidak dipakai di simulasi'};
 if(snapshot?.source==='replay') return {ok:false,value:'Replay rekaman'};
 const flowing=active && snapshot?.source==='live' && !!snapshot.serial_connected;
 return {ok:flowing,value:flowing?'Mengalir':snapshot?.serial_connected?'Status terakhir: terhubung':'Belum terhubung'};
}
