const CACHE_NAME = 'pypg-mail-v3';
const PRECACHE_URLS = [
    '/',
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

    // Only handle same-origin requests — let CDN requests pass through
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;

    event.respondWith(
        fetch(event.request).then(response => {
            // Don't cache redirects or errors — only cache successful 200 responses
            if (response.ok && response.status === 200 && response.type === 'basic') {
                const clone = response.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
            }
            return response;
        }).catch(() => caches.match(event.request))
    );
});