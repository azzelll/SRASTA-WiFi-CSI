import React, { lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import { keyboardDemoRequested } from './keyboard-demo-state';
import './style.css';
// The browser demo never loads the live connection/auth/command module.
const View = lazy(() => keyboardDemoRequested(window.location.search)
  ? import('./keyboard-demo').then(module => ({ default: module.KeyboardDemo }))
  : import('./app').then(module => ({ default: module.App })));
createRoot(document.getElementById('root')!).render(<React.StrictMode><Suspense fallback={<p>Memuat SRASTA…</p>}><View/></Suspense></React.StrictMode>);
if('serviceWorker' in navigator && import.meta.env.PROD) navigator.serviceWorker.register('/sw.js').catch(()=>{});
