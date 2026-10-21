import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AlertHistory, CameraPanel, MetricGrid } from './dashboard';
import type { CameraPose, CareEvent, Snapshot } from './types';

const event = {id:1,event_uid:'event-current',timestamp_s:1_800_000_000,state:'confirmed_fall',evidence:'live CSI',confidence:.8,motion_energy:.001,ack_source:null,acknowledged_at_s:null} as CareEvent;
const snapshot: Snapshot = {
 schema_version:1,updated_at_s:1_800_000_000,observed_at_s:1_800_000_000,state_verified:true,
 monitoring_online:true,stream_age_s:0,breathing_quality:90,breathing_reason:'Test fixture',
 capture_rate_hz:100,accepted_frames:100,quarantined_frames:0,packet_loss_rate:0,inference_ms:10,
 serial_connected:true,serial_reconnects:0,alarm:{available:true,active:false,requested:false},
 blynk_connected:true,remote:{enabled:true,connected:true},
 model:{label:'Test fixture',validation:'Test only',presence_available:true,activity_classes_available:true},
 source:'live',simulation:false,state:'normal',activity:'Berjalan',motion_energy:.001,breathing_bpm:19,
 breathing_condition:'normal',stationary_duration_s:30,signal_quality:99,fall_confidence:.8,
 events:[event],camera:{available:true,active:false,event_uid:'event-current',result:'Global result must not attach',validations:[]}
};
describe('dashboard evidence boundaries', () => {
 it('renders event-linked camera coordinates only for a current live snapshot', () => {
  const pose:CameraPose={format:'movenet-coco17',keypoints:Array.from({length:17},(_,i)=>[i<11?.3:.7,.4,.9])};
  const camera={...snapshot.camera,validations:[{event_uid:event.event_uid,checked_at_s:event.timestamp_s,outcome:'not_horizontal' as const,result:'Postur belum mendukung indikasi jatuh',latency_ms:1000,pose}]};
  const current={...snapshot,camera};
  const html=renderToStaticMarkup(<CameraPanel snapshot={current} active />);
  expect(html).toContain('Skeleton dari kamera: Postur tegak');
  expect(html).toContain('bisa berdiri atau duduk');
  expect(html).toContain('Cuplikan kejadian');
  for(const changed of [{...current,source:'replay' as const},{...current,simulation:true},{...current,events:[{...event,event_uid:'another-event'}]}]) {
   expect(renderToStaticMarkup(<CameraPanel snapshot={changed} active />)).not.toContain('Skeleton dari kamera');
  }
  expect(renderToStaticMarkup(<CameraPanel snapshot={current} active={false} />)).not.toContain('Skeleton dari kamera');
 });
 it('hides stale numerical readings without dropping an unacknowledged alert', () => {
  const html=renderToStaticMarkup(<MetricGrid snapshot={snapshot} active={false} alerts={[event]} />);
  expect(html).not.toContain('Kualitas: 99%');
  expect(html).not.toContain('Skor jatuh: 80%');
  expect(html).not.toContain('>19<');
  expect(html).toContain('Offline');
  expect(html).toContain('1 peringatan belum diakui');
  expect(html).not.toContain('darurat telah dikirim');
  expect(html).not.toContain('dBm');
 });
 it('does not say there are no active alerts when current data is missing', () => {
  const html=renderToStaticMarkup(<MetricGrid snapshot={null} active={false} alerts={[]} />);
  expect(html).toContain('Belum ada data terkini');
  expect(html).not.toContain('Tidak ada peringatan aktif');
 });
 it('ignores camera results and running capture belonging to a different event', () => {
  const camera={...snapshot.camera,active:true,event_uid:'event-other',validations:[{event_uid:'event-other',result:'UNRELATED_RESULT',outcome:'horizontal' as const,checked_at_s:1_800_000_000,latency_ms:10}]};
  const html=renderToStaticMarkup(<CameraPanel snapshot={{...snapshot,camera}} active />);
  expect(html).not.toContain('UNRELATED_RESULT');
  expect(html).not.toContain('Global result must not attach');
  expect(html).not.toContain('Ilustrasi proses');
 });
 it('does not turn an uncertain or failed validation into a confirmed fall', () => {
  for(const outcome of ['uncertain','error'] as const) {
   const camera={...snapshot.camera,validations:[{event_uid:event.event_uid,result:'Belum dapat memastikan postur.',outcome,checked_at_s:1_800_000_000,latency_ms:10}]};
   const html=renderToStaticMarkup(<CameraPanel snapshot={{...snapshot,camera}} active />);
   expect(html).toContain(outcome==='uncertain'?'Belum pasti':'Terhambat');
   expect(html).toContain(outcome==='uncertain'?'Koordinat belum tersedia':'Tidak ada cuplikan');
   expect(html).not.toContain('Skeleton dari kamera');
   expect(html).not.toContain('jatuh terkonfirmasi');
  }
 });
 it('never attaches real camera output to replay or simulator snapshots', () => {
  const camera={...snapshot.camera,active:true,validations:[{event_uid:event.event_uid,result:'PRIVATE_RESULT',outcome:'horizontal' as const,checked_at_s:1_800_000_000,latency_ms:10}]};
  for(const source of ['replay','simulator'] as const) {
   const html=renderToStaticMarkup(<CameraPanel snapshot={{...snapshot,camera,source}} active />);
   expect(html).not.toContain('PRIVATE_RESULT');
   expect(html).toContain('Kamera belum tersedia');
  }
 });
 it('does not downgrade an acknowledged critical condition to standby', () => {
  const prior={...event,acknowledged_at_s:event.timestamp_s+30};
  const current={...snapshot,state:'critical' as const,events:[prior]};
  const history=renderToStaticMarkup(<AlertHistory snapshot={current} active onOpen={()=>{}} />);
  const metrics=renderToStaticMarkup(<MetricGrid snapshot={current} active alerts={[prior]} />);
  expect(history).toContain('Periksa kondisi dan tindak lanjut');
  expect(history).not.toContain('Sistem dalam mode siaga');
  expect(metrics).toContain('Peringatan telah diakui');
  expect(metrics).not.toContain('Tidak ada peringatan aktif');
 });
 it('keeps stale critical warnings visible and puts unacknowledged alerts first', () => {
  const prior={...event,event_uid:'event-old',state:'inactive',timestamp_s:event.timestamp_s+200,acknowledged_at_s:event.timestamp_s+201};
  const html=renderToStaticMarkup(<AlertHistory snapshot={{...snapshot,state:'critical',events:[prior,event]}} active={false} onOpen={()=>{}} />);
  expect(html.indexOf('Diam setelah indikasi jatuh')).toBeLessThan(html.indexOf('Respons caregiver tercatat'));
  expect(html).not.toContain('Sistem berjalan normal');
  expect(html).not.toContain('Selesai');
  expect(html).toContain('Diakui');
 });
});
