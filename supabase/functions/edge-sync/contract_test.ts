import assert from 'node:assert/strict';
import { payload } from './contract.ts';
import snapshot from './fixtures/pi-live-summary.json' with { type: 'json' };

const summary=()=>({device_id:'00000000-0000-4000-8000-000000000001',snapshot:structuredClone(snapshot),events:[],receipts:[]});

Deno.test('Pi live summary is accepted with unavailable features preserved',()=>{
 const result=payload.safeParse(summary());
 assert.equal(result.success,true,result.success ? '' : result.error.message);
 if(result.success) assert.deepEqual(result.data.snapshot,snapshot);
});

Deno.test('older summaries remain compatible',()=>{
 const input=summary();
 for(const field of ['presence','inactivity','stationary_duration_s','breathing_condition']) Reflect.deleteProperty(input.snapshot,field);
 assert.equal(payload.safeParse(input).success,true);
});

Deno.test('feature values are validated without coercion',()=>{
 for(const [field,value] of [['presence','sleep'],['inactivity','false'],['stationary_duration_s',-1],['stationary_duration_s',Infinity],['breathing_condition','moving'],['breathing_condition',12]]) {
  const input=summary();
  Reflect.set(input.snapshot,field,value);
  assert.equal(payload.safeParse(input).success,false,`${field} accepted ${value}`);
 }
 const input=summary();
 Object.assign(input.snapshot,{presence:'present',inactivity:true,stationary_duration_s:120,breathing_condition:'sleep'});
 assert.equal(payload.safeParse(input).success,true);
});

Deno.test('raw CSI is rejected at every summary boundary',()=>{
 for(const container of ['envelope','snapshot','model']) {
  const input=summary();
  Reflect.set(container==='envelope' ? input : container==='snapshot' ? input.snapshot : input.snapshot.model,'iq_bytes',[1,2]);
  assert.equal(payload.safeParse(input).success,false,`${container} accepted raw CSI`);
 }
});

Deno.test('camera sends only event-linked summaries, without arbitrary keypoints or images',()=>{
 const input=summary();
 const id='00000000-0000-4000-8000-000000000002';
 const row={event_uid:id,checked_at_s:1800000000,outcome:'uncertain',result:'Keypoint tubuh kurang andal',latency_ms:1800};
 Object.assign(input.snapshot.camera,{available:true,event_uid:id,validations:[row]});
 assert.equal(payload.safeParse(input).success,true);
 for(const field of ['image','keypoints','iq_bytes']) {
  const changed=structuredClone(input);
  Reflect.set(changed.snapshot.camera,field,[1,2]);
  assert.equal(payload.safeParse(changed).success,false);
 }
 const changed=structuredClone(input);
 Reflect.set(changed.snapshot.camera,'validations',[{...row,keypoints:[1,2]}]);
 assert.equal(payload.safeParse(changed).success,false);
 Reflect.set(changed.snapshot.camera,'validations',[{...row,outcome:'confirmed_fall'}]);
 assert.equal(payload.safeParse(changed).success,false);
});

Deno.test('camera accepts exactly 17 normalized pose points and rejects images or invalid coordinates',()=>{
 const input=summary();
 const pose={format:'movenet-coco17',keypoints:Array.from({length:17},()=>[.2,.4,.9])};
 const row={event_uid:'00000000-0000-4000-8000-000000000002',checked_at_s:1800000000,outcome:'horizontal',result:'Postur mendatar',latency_ms:1800,pose};
 Reflect.set(input.snapshot.camera,'validations',[row]);
 assert.equal(payload.safeParse(input).success,true);
 for(const invalid of [
  {...pose,keypoints:pose.keypoints.slice(1)}, {...pose,keypoints:[...pose.keypoints,[.2,.4,.9]]},
  {...pose,format:'unknown'}, {...pose,image:'pixels'},
  ...[-.1,1.1,Infinity,NaN,'0.5',true].map(value=>({...pose,keypoints:[[value,.4,.9],...pose.keypoints.slice(1)]})),
  {...pose,keypoints:[[.2,.4,.9,.8],...pose.keypoints.slice(1)]},
 ]) {
  Reflect.set(input.snapshot.camera,'validations',[{...row,pose:invalid}]);
  assert.equal(payload.safeParse(input).success,false);
 }
 Reflect.set(input.snapshot.camera,'validations',[{...row,pose:null}]);
 assert.equal(payload.safeParse(input).success,true);
});
