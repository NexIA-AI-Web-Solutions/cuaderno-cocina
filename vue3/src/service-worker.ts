/// <reference lib="webworker" />
// Cache only built/public assets. Authenticated data is always network-only.
import {precacheAndRoute} from 'workbox-precaching';
import {registerRoute, setCatchHandler} from 'workbox-routing';
import {CacheFirst, NetworkFirst, NetworkOnly} from 'workbox-strategies';
import {ExpirationPlugin} from 'workbox-expiration';
import {Queue} from 'workbox-background-sync';
import {clientsClaim, setCacheNameDetails} from 'workbox-core';

declare let self: ServiceWorkerGlobalScope
const scope = new URL(self.registration.scope)
if (scope.origin !== self.location.origin || scope.pathname === '/' || !scope.pathname.endsWith('/')) {
    throw new Error('Cuaderno service worker requires a same-origin deployment prefix')
}
const namespace = `cuaderno-${encodeURIComponent(scope.pathname)}`
const staticPath = `${scope.pathname}static/`
const builtAssets = new URL('static/vue3/', scope)
setCacheNameDetails({prefix: namespace, suffix: 'v1', precache: 'precache', runtime: 'runtime'})
// The worker is served beside the application, while Vite emits build-relative URLs.
// Reject any manifest entry outside this application's public static directory.
const publicManifest = self.__WB_MANIFEST.flatMap(entry => {
    const url = new URL(typeof entry === 'string' ? entry : entry.url, builtAssets)
    if (url.origin !== scope.origin || !url.pathname.startsWith(staticPath)) return []
    return [typeof entry === 'string' ? url.href : {...entry, url: url.href}]
})
precacheAndRoute(publicManifest)
self.skipWaiting()
clientsClaim()

// Pending writes belong only to this deployment and are discarded, never replayed.
async function discardQueuedWrites({queue}: {queue: Queue}) {
    while (await queue.shiftRequest()) { /* intentionally no fetch/replay */ }
}
const queue = new Queue(`${namespace}-shopping-sync-queue`, {onSync: discardQueuedWrites})
self.addEventListener('activate', event => {
    event.waitUntil(discardQueuedWrites({queue}))
})

setCatchHandler(async ({request}) => {
    if (request.destination === 'document') {
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
        (url.origin === scope.origin && (url.pathname.startsWith(`${scope.pathname}api/`) ||
            url.pathname.startsWith(`${scope.pathname}media/`))) ||
        (request.destination === 'image' &&
            (url.origin !== self.location.origin || !url.pathname.startsWith(staticPath))),
    new NetworkOnly(),
)
for (const method of ['POST', 'PATCH', 'PUT', 'DELETE'] as const) {
    registerRoute(({url}) => url.origin === scope.origin && url.pathname.startsWith(scope.pathname), new NetworkOnly(), method)
}
registerRoute(
    ({request, url}) => request.destination === 'image' &&
        url.origin === self.location.origin && url.pathname.startsWith(staticPath),
    new CacheFirst({cacheName: `${namespace}-public-images`, plugins: [new ExpirationPlugin({maxEntries: 20})]}),
)
registerRoute(
    ({request, url}) => url.origin === self.location.origin && url.pathname.startsWith(staticPath) &&
        (request.destination === 'script' || request.destination === 'style'),
    new NetworkFirst({cacheName: `${namespace}-assets`, plugins: [new ExpirationPlugin({
        maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 7,
    })]}),
)
self.addEventListener('message', event => {
    const port = event.ports[0]
    if (event.data?.type === 'BGSYNC_REPLAY_REQUESTS') {
        event.waitUntil(discardQueuedWrites({queue}).then(() => port?.postMessage('REPLAY_DISABLED')))
    } else if (event.data?.type === 'BGSYNC_COUNT_QUEUE') {
        event.waitUntil(discardQueuedWrites({queue}).then(() => port?.postMessage(0)))
    }
})
