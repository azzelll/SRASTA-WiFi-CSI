const CACHE = 'srasta-shell-v3-figma';
const PRECACHE_ASSETS = [];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(['/', '/icon.svg', '/icon-192.png', '/manifest.webmanifest', ...PRECACHE_ASSETS]))); self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))); self.clients.claim(); });
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // No CSI, snapshots, authenticated API, or cloud traffic is stored in Cache.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || ['/api','/demo','/technical','/health','/status','/csi','/events','/metrics'].some(path => url.pathname.startsWith(path))) return;
  if (event.request.mode === 'navigate') event.respondWith(fetch(event.request).then(response => { if(response.ok) caches.open(CACHE).then(cache => cache.put('/',response.clone())); return response; }).catch(() => caches.match('/')));
  else if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/figma/') || url.pathname.startsWith('/icon') || url.pathname === '/manifest.webmanifest') event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request).then(response => { if(response.ok) caches.open(CACHE).then(cache => cache.put(event.request,response.clone())); return response; })));
});
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data?.json() || {}; } catch { /* A malformed push still opens the app safely. */ }
  const critical = ['critical','confirmed_fall'].includes(data.state);
  const title = data.simulation ? 'SRASTA · Uji simulasi' : critical ? 'SRASTA · Kondisi kritis' : 'SRASTA · Perlu perhatian';
  event.waitUntil(self.registration.showNotification(title, {body:data.simulation?'Peringatan ini dibuat untuk pengujian.':critical?'Segera periksa kondisi. Ketuk untuk merespons.':'Periksa kondisi dan tindak lanjuti peringatan.',icon:'/icon-192.png',badge:'/icon-192.png',tag:data.event_uid || 'srasta-alert',data:{device_id:data.device_id,event_uid:data.event_uid},requireInteraction:true}));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const data = event.notification.data || {}, uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const target = new URL('/', self.location.origin);
  if(uuid.test(data.device_id || '') && uuid.test(data.event_uid || '')) {
    target.searchParams.set('device', data.device_id);
    target.searchParams.set('event', data.event_uid);
  }
  event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async clients => {
    const existing = clients.find(client => new URL(client.url).origin === self.location.origin);
    if(existing) { await existing.navigate(target.href); return existing.focus(); }
    return self.clients.openWindow(target.href);
  }));
});
