// Cache only built/public assets. Authenticated data is always network-only.
import {precacheAndRoute, cleanupOutdatedCaches} from 'workbox-precaching';
import {registerRoute, setCatchHandler} from 'workbox-routing';
import {CacheFirst, NetworkFirst, NetworkOnly, StaleWhileRevalidate} from 'workbox-strategies';
import {ExpirationPlugin} from 'workbox-expiration';
import {Queue} from 'workbox-background-sync';
import {clientsClaim} from 'workbox-core';

declare let self: ServiceWorkerGlobalScope
cleanupOutdatedCaches()
precacheAndRoute(self.__WB_MANIFEST)
self.skipWaiting()
clientsClaim()

// Keep the legacy identity only to discard pending writes, never to replay them.
async function discardQueuedWrites({queue}: {queue: Queue}) {
    while (await queue.shiftRequest()) { /* intentionally no fetch/replay */ }
}
const queue = new Queue('shopping-sync-queue', {onSync: discardQueuedWrites})
self.addEventListener('activate', event => {
    event.waitUntil(Promise.all([
        ...['images', 'api', 'api-recipe', 'html', 'offline-html'].map(name => caches.delete(name)),
        discardQueuedWrites({queue}),
    ]))
})

setCatchHandler(async ({event}) => {
    if (event.request.destination === 'document') {
        return new Response('<!doctype html><html lang="es"><meta charset="utf-8">' +
            '<meta name="viewport" content="width=device-width, initial-scale=1">' +
            '<title>Sin conexión · Cuaderno Cocina</title><main><h1>Sin conexión</h1>' +
            '<p>Conéctate para consultar tus recetas o guardar cambios. No se han encolado cambios.</p></main></html>', {
            status: 503, headers: {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store'},
        })
    }
    return Response.error()
})

// Must precede asset routes: protected data must never reach a runtime cache.
registerRoute(
    ({request, url}) => request.destination === 'document' ||
        url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/') ||
        (request.destination === 'image' &&
            (url.origin !== self.location.origin || !url.pathname.startsWith('/static/'))),
    new NetworkOnly(),
)
for (const method of ['POST', 'PATCH', 'PUT', 'DELETE'] as const) {
    registerRoute(({url}) => url.origin === self.location.origin, new NetworkOnly(), method)
}
registerRoute(
    ({request, url}) => request.destination === 'image' &&
        url.origin === self.location.origin && url.pathname.startsWith('/static/'),
    new CacheFirst({cacheName: 'public-images', plugins: [new ExpirationPlugin({maxEntries: 20})]}),
)
registerRoute(
    ({request, url}) => url.origin === self.location.origin && url.pathname.startsWith('/static/') &&
        (request.destination === 'script' || request.destination === 'style'),
    new NetworkFirst({cacheName: 'assets', plugins: [new ExpirationPlugin({
        maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 7,
    })]}),
)
registerRoute(
    ({url}) => url.origin === self.location.origin && /\/(jsreverse|jsi18n)\//.test(url.pathname),
    new StaleWhileRevalidate({cacheName: 'assets'}),
)
self.addEventListener('message', event => {
    const port = event.ports[0]
    if (event.data?.type === 'BGSYNC_REPLAY_REQUESTS') {
        event.waitUntil(discardQueuedWrites({queue}).then(() => port?.postMessage('REPLAY_DISABLED')))
    } else if (event.data?.type === 'BGSYNC_COUNT_QUEUE') {
        event.waitUntil(discardQueuedWrites({queue}).then(() => port?.postMessage(0)))
    }
})
