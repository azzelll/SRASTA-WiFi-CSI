import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { EventCard, EventEvidence } from './event-detail';
import { mergeReceipts } from './receipts';
import { coalesceRefresh } from './refresh';
import type { CameraPose, CareEvent, CommandReceipt, Snapshot } from './types';

const event:CareEvent={id:1,event_uid:'event-a',timestamp_s:1800000000,state:'suspected_fall',confidence:.81,motion_energy:.01,evidence:'model',acknowledged_at_s:null,ack_source:null};
const pose:CameraPose={format:'movenet-coco17',keypoints:Array.from({length:17},(_,i)=>[i<11?.3:.7,.4,.9])};
const snapshot={source:'live',simulation:false,camera:{available:true,active:false,result:'Ready',validations:[{event_uid:'event-a',checked_at_s:1800000001,outcome:'not_horizontal',result:'Postur terukur',latency_ms:1000,pose}]}} as Snapshot;
const receipt:CommandReceipt={id:'receipt-a',event_uid:'event-a',action:'acknowledge',status:'pending'};
function card(receipts:CommandReceipt[], target=event) {return renderToStaticMarkup(<EventCard event={target} snapshot={snapshot} receipts={receipts} busy={false} room="Ruang uji" emergency="" onAction={()=>{}} onSetupEmergency={()=>{}} />);}

describe('event evidence and caregiver receipts',()=>{
 it('binds pose to the selected event and labels historical posture even when offline',()=>{
  const html=renderToStaticMarkup(<EventEvidence event={event} snapshot={{...snapshot,source:'unavailable'}} />);
  expect(html).toContain('Skeleton dari kamera: Postur tegak');
  expect(html).toContain('81%');
  expect(html).toContain('bukan kondisi saat ini');
  expect(renderToStaticMarkup(<EventEvidence event={{...event,event_uid:'event-b'}} snapshot={snapshot} />)).not.toContain('Skeleton dari kamera');
 });
 it('never attaches real pose to simulated/replay events or sessions',()=>{
  for(const changed of [{...snapshot,simulation:true},{...snapshot,source:'simulator' as const},{...snapshot,source:'replay' as const}]) {
   expect(renderToStaticMarkup(<EventEvidence event={event} snapshot={changed} />)).not.toContain('Skeleton dari kamera');
  }
  for(const evidence of ['demo_state_mock','replay_model']) {
   const html=renderToStaticMarkup(<EventEvidence event={{...event,evidence}} snapshot={snapshot} />);
   expect(html).not.toContain('Skeleton dari kamera');
   expect(html).not.toContain('81%');
  }
 });
 it('does not say acknowledged while command is pending and disables duplicate submissions',()=>{
  const html=card([receipt]);
  expect(html).toContain('Menunggu perangkat · belum diterapkan');
  expect(html).not.toContain('Diakui caregiver');
  expect(html).toMatch(/disabled=""[^>]*>[\s\S]*?Menunggu konfirmasi perangkat/);
  const applied=card([{...receipt,status:'applied'}]);
  expect(applied).toContain('Diakui caregiver');
  expect(applied).not.toContain('Saya sudah melihat peringatan');
 });
 it('permits retry for rejected/expired commands and isolates other event receipts',()=>{
  for(const status of ['expired','rejected'] as const) {
   const html=card([{...receipt,status}]);
   expect(html).toContain('Saya sudah melihat peringatan');
   expect(html).not.toContain('Diakui caregiver');
  }
  expect(card([{...receipt,status:'applied',event_uid:'event-b'}])).not.toContain('Diakui caregiver');
 });
 it('keeps assistance distinct from acknowledgement and never claims an automatic call',()=>{
  const html=card([{...receipt,action:'assistance',status:'applied'}]);
  expect(html).toContain('Permintaan bantuan tercatat');
  expect(html).toContain('Saya sudah melihat peringatan');
  expect(html).toContain('tidak melakukan panggilan otomatis');
  expect(card([], {...event,state:'normal'})).not.toContain('Saya sudah melihat peringatan');
 });
 it('does not regress applied receipts after an older poll or duplicate response',()=>{
  const applied={...receipt,status:'applied' as const,applied_at_s:1800000010};
  expect(mergeReceipts([applied],[receipt])).toEqual([applied]);
  expect(mergeReceipts([receipt],[applied,applied])).toEqual([applied]);
  expect(mergeReceipts([{...receipt,status:'expired'}],[receipt])[0].status).toBe('expired');
 });
});

describe('snapshot refresh coalescing',()=>{
 it('queues one followup for overlapping realtime and poll requests',async()=>{
  let finish!:()=>void, count=0;
  const first=new Promise<void>(resolve=>{finish=resolve});
  const poller=coalesceRefresh(async()=>{count++;if(count===1)await first;});
  const pending=poller.request();
  await poller.request(); await poller.request();
  expect(count).toBe(1);
  finish(); await pending;
  expect(count).toBe(2);
 });
 it('cancels queued refreshes on device switch and accepts retries after failure',async()=>{
  let finish!:()=>void, count=0;
  const hold=new Promise<void>(resolve=>{finish=resolve});
  const poller=coalesceRefresh(async()=>{count++;await hold;});
  const pending=poller.request(); await poller.request();poller.close();finish();await pending;await poller.request();
  expect(count).toBe(1);
  const retry=coalesceRefresh(async()=>{count++;if(count===2)throw new Error('offline');});
  await expect(retry.request()).rejects.toThrow('offline');
  await retry.request(); expect(count).toBe(3);
 });
});
