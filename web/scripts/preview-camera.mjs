// Local visual QA only. This route/plugin is absent from production builds.
import { createServer } from 'vite';

const plugin = {
 name:'srasta-local-camera-preview',
 configureServer(server) {
  server.middlewares.use(async (req,res,next)=>{
   if(req.url?.split('?')[0]!=='/__camera-preview') return next();
   const page=`<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SRASTA — Pratinjau skeleton</title><body><div id="root"></div><script type="module">
import React from 'react';
import {createRoot} from 'react-dom/client';
import {CameraPanel} from '/src/dashboard.tsx';
import '/src/style.css';
const h=React.createElement, now=Date.now()/1000;
const points=[[.16,.5,.95],[.15,.47,.9],[.15,.53,.9],[.16,.44,.9],[.16,.56,.9],[.3,.4,.95],[.3,.6,.95],[.45,.34,.9],[.45,.66,.9],[.57,.3,.9],[.57,.7,.9],[.55,.44,.95],[.55,.56,.95],[.73,.44,.9],[.73,.57,.9],[.9,.42,.9],[.9,.59,.9]];
const event={id:1,event_uid:'preview-event',timestamp_s:now,state:'suspected_fall',evidence:'model',confidence:.8,motion_energy:.01,acknowledged_at_s:null,ack_source:null};
function panel(mode) {
 const outcome=mode==='Berbaring'?'horizontal':mode==='Tegak'?'not_horizontal':'uncertain';
 const pose={format:'movenet-coco17',keypoints:mode==='Berbaring'?points.map(([y,x,s])=>[x,1-y,s]):points.map(([y,x,s])=>[y,x,mode==='Belum jelas'?.1:s])};
 const result={event_uid:event.event_uid,checked_at_s:now,outcome,result:'Keypoint tubuh kurang andal',latency_ms:2000,pose};
 const camera={available:true,active:mode==='Memproses',event_uid:event.event_uid,result:'Siap',validations:['Memproses','Nonaktif'].includes(mode)?[]:[result]};
 return h('div',{key:mode,style:{maxWidth:585,width:'100%'}},h('p',{style:{fontSize:12,color:'#64748b',margin:'0 0 12px'}},mode),h(CameraPanel,{active:true,snapshot:{source:'live',simulation:false,state:'anomaly',events:[event],camera}}));
}
createRoot(document.getElementById('root')).render(h('main',{style:{padding:24,maxWidth:1250,margin:'auto'}},h('p',{style:{fontSize:12,color:'#64748b',marginBottom:8}},'PRATINJAU PENGEMBANGAN · DATA SINTETIS'),h('h1',{style:{fontSize:24,marginBottom:8}},'Panel validasi kamera'),h('p',{style:{fontSize:14,color:'#64748b',marginBottom:24}},'Contoh untuk pemeriksaan UI. Bukan hasil kamera atau deteksi lansia.'),h('div',{style:{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,360px),1fr))',gap:24}},['Berbaring','Tegak','Belum jelas','Memproses','Nonaktif'].map(panel))));
</script></body></html>`;
   res.statusCode=200;res.setHeader('Content-Type','text/html');res.end(await server.transformIndexHtml(req.url,page));
  });
 },
};
const server=await createServer({plugins:[plugin],server:{host:'127.0.0.1',port:5317,strictPort:true}});
await server.listen();
console.log('Local synthetic visual QA: http://127.0.0.1:5317/__camera-preview');
