import { expect, it } from 'vitest';
import { cameraNote } from './status';
import type { CareEvent, Snapshot } from './types';

const event={event_uid:'event-a',evidence:'model'} as CareEvent;
const camera:Snapshot['camera']={available:true,active:false,result:'Hasil global yang tidak terkait',event_uid:'event-b',validations:[{event_uid:'event-b',checked_at_s:1800000000,outcome:'horizontal',result:'Postur mendatar',latency_ms:1000}]};

it('only shows the validation attached to this event',()=>{
 expect(cameraNote(camera,event)).toBe('Belum ada hasil validasi kamera untuk kejadian ini.');
 expect(cameraNote(camera,{...event,event_uid:'event-b'})).toContain('Postur mendatar');
 expect(cameraNote({...camera,active:true},event)).not.toContain('sedang berjalan');
 expect(cameraNote({...camera,active:true,event_uid:'event-a'},event)).toContain('sedang berjalan');
});
it('does not attach a real camera result to simulated events',()=>{
 expect(cameraNote(camera,{...event,evidence:'demo_state_mock'})).toContain('tidak dijalankan');
 expect(cameraNote(undefined,event)).toContain('belum tersedia');
});
