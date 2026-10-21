// Local component QA. This plugin/route is absent from production builds.
import { createServer } from 'vite';
const plugin={name:'srasta-event-preview',configureServer(server){
 server.middlewares.use(async(req,res,next)=>{
  if(req.url?.split('?')[0]!=='/__event-preview')return next();
  const html=`<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SRASTA — Detail kejadian</title><body><div id="root"></div><script type="module">
import React,{useState} from 'react';import{createRoot}from'react-dom/client';
import{EventCard}from'/src/event-detail.tsx';import'/src/style.css';
const h=React.createElement,now=Date.now()/1000;
const points=[[.16,.5,.95],[.15,.47,.9],[.15,.53,.9],[.16,.44,.9],[.16,.56,.9],[.3,.4,.95],[.3,.6,.95],[.45,.34,.9],[.45,.66,.9],[.57,.3,.9],[.57,.7,.9],[.55,.44,.95],[.55,.56,.95],[.73,.44,.9],[.73,.57,.9],[.9,.42,.9],[.9,.59,.9]];
const event={id:1,event_uid:'local-ui-preview',timestamp_s:now,state:'suspected_fall',evidence:'model',confidence:.81,motion_energy:.01,acknowledged_at_s:null,ack_source:null};
function Preview(){const[status,setStatus]=useState('none'),[action,setAction]=useState('acknowledge'),[view,setView]=useState('horizontal');
const pose={format:'movenet-coco17',keypoints:points.map(([y,x,s])=>[x,1-y,s])};
const validation={event_uid:event.event_uid,checked_at_s:now+1,outcome:view,result:view==='horizontal'?'Postur mendatar; perlu diperiksa caregiver · konsisten 3/3 cuplikan':view==='error'?'Validasi kamera gagal; periksa kondisi secara langsung':'Postur berubah antarcuplikan; periksa kondisi secara langsung',latency_ms:2000,pose:view==='error'?null:pose};
const snapshot={source:'live',simulation:false,camera:{available:true,active:false,result:'Siap',validations:[validation]}};
return h('main',{style:{padding:'24px',maxWidth:1050,margin:'auto'}},h('p',{style:{fontSize:12,color:'#64748b',marginBottom:8}},'PRATINJAU PENGEMBANGAN · DATA SINTETIS'),h('h1',{style:{fontSize:24,marginBottom:8}},'Detail kejadian caregiver'),h('p',{style:{fontSize:14,color:'#64748b',marginBottom:24}},'Contoh komponen app. Tidak mengirim perintah, notifikasi, atau gambar ke cloud.'),
h('div',{className:'filter-row'},['horizontal','uncertain','error'].map((mode,index)=>h('button',{key:mode,onClick:()=>setView(mode)},['Berbaring','Postur belum jelas','Kamera gagal'][index])),h('button',{onClick:()=>setStatus('applied')},'Simulasikan konfirmasi perangkat'),h('button',{onClick:()=>setStatus('expired')},'Simulasikan kedaluwarsa'),h('button',{onClick:()=>setStatus('none')},'Reset pratinjau')),
h(EventCard,{event,snapshot,receipts:status==='none'?[]:[{id:'preview-receipt',event_uid:event.event_uid,action,status}],busy:false,room:'Ruang contoh',emergency:'',onAction:(_,next)=>{setAction(next);setStatus('pending')},onSetupEmergency:()=>{}}));}
createRoot(document.getElementById('root')).render(h(Preview));
</script></body></html>`;
 res.setHeader('Content-Type','text/html; charset=utf-8');res.end(await server.transformIndexHtml(req.url,html));
 });
}};
const server=await createServer({plugins:[plugin],server:{host:'127.0.0.1',port:5318,strictPort:true}});await server.listen();console.log('Synthetic UI QA: http://127.0.0.1:5318/__event-preview');
