import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { StatusCard } from './app';
import { isFresh, receiverStatus, states } from './status';
import type { Snapshot, SystemState } from './types';

const now=1_800_000_000_000;
const sample={schema_version:1,updated_at_s:now/1000,observed_at_s:now/1000,source:'live',simulation:false,state:'normal',state_verified:true,monitoring_online:true,fall_confidence:null} as Snapshot;
describe('caregiver state contract',()=>{
 it('never calls simulator/replay a flowing receiver or stale data connected',()=>{
  expect(receiverStatus({...sample,source:'simulator',serial_connected:false},true)).toEqual({ok:false,value:'Tidak dipakai di simulasi'});
  expect(receiverStatus({...sample,source:'replay',serial_connected:false},false)).toEqual({ok:false,value:'Replay rekaman'});
  expect(receiverStatus({...sample,serial_connected:true},true)).toEqual({ok:true,value:'Mengalir'});
  expect(receiverStatus({...sample,serial_connected:true},false)).toEqual({ok:false,value:'Status terakhir: terhubung'});
 });
 it('renders the five distinct caregiver states',()=>{
  for(const state of Object.keys(states) as SystemState[]) {
   const output=renderToStaticMarkup(<StatusCard snapshot={{...sample,state}} active name="Uji" room="Ruang uji"/>);
   expect(output).toContain(states[state].label);
   expect(output).toContain(`status-card ${state}`);
  }
 });
 it('does not show fresh normal with no data or stale observations',()=>{
  expect(isFresh(null,now,now)).toBe(false);
  expect(isFresh(sample,now,now)).toBe(true);
  expect(isFresh(sample,now-11000,now)).toBe(false);
  expect(isFresh({...sample,observed_at_s:now/1000-11},now,now)).toBe(false);
  expect(isFresh({...sample,state_verified:false},now,now)).toBe(false);
  expect(renderToStaticMarkup(<StatusCard snapshot={sample} active={false} name="Uji" room="Uji"/>)).toContain('Kondisi terkini belum dapat dipastikan');
 });
 it('explicitly labels replay and simulator and retains last critical state',()=>{
  expect(isFresh({...sample,source:'replay',simulation:true},now,now)).toBe(false);
  expect(isFresh({...sample,source:'simulator',simulation:true},now,now)).toBe(true);
  expect(renderToStaticMarkup(<StatusCard snapshot={{...sample,source:'simulator'}} active name="Uji" room="Uji"/>)).toContain('Simulasi');
  const output=renderToStaticMarkup(<StatusCard snapshot={{...sample,state:'critical'}} active={false} name="Uji" room="Uji"/>);
  expect(output).toContain('Status terakhir: Kondisi kritis');
  expect(output).toContain('status-card critical');
 });
});
