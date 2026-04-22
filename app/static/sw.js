const CACHE_NAME = 'pypg-mail-v1';
const PRECACHE_URLS = [
    '/',
    '/inbox',
    '/static/manifest.json'
];

self.addEventListener('install', event => {
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;
    if (event.request.url.includes('/auth/') ||
        event.request.url.includes('/login') ||
        event.request.url.includes('/logout')) return;

    event.respondWith(
        fetch(event.request).then(response => {
            if (response.ok && response.type === 'basic') {
                const clone = response.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
            }
            return response;
        }).catch(() => caches.match(event.request))
    );
});