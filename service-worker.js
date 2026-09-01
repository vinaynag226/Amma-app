const CACHE_NAME = 'anantha-shree-v2'; // bumped from v1 — clears out every stale cached copy on this one update
const APP_SHELL = [
  './',
  './index.html',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

/* Only handle same-origin GET requests for the app shell itself. Everything
   else — Firebase Realtime Database, auth, CDN scripts — passes straight
   through to the network untouched, never cached or intercepted, so live
   booking/tiffin/rate data always stays live and never goes stale. */
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  /* Network-first: always tries to fetch the latest file when the phone is
     online, and only falls back to the cached copy if that fetch genuinely
     fails (actually offline). This is the opposite of the previous
     behavior, which served the OLD cached copy first even when online and
     a newer file had already been uploaded — the exact cause of updates
     appearing not to take effect. The cache still exists and still gets
     refreshed on every successful fetch, so offline use still works; it's
     just no longer served in preference to a fresh copy when one's available. */
  event.respondWith(
    fetch(event.request).then(response => {
      if (response && response.status === 200) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
      }
      return response;
    }).catch(() => caches.match(event.request))
  );
});
