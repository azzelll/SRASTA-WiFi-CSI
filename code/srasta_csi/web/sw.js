const CACHE='srasta-shell-v1';const ASSETS=['/','/static/style.css','/static/app.js','/static/icon.svg','/static/manifest.webmanifest'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(event.request.method!=='GET'||url.origin!==location.origin||!ASSETS.includes(url.pathname))return;event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)));});
