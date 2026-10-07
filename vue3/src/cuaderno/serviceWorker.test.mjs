import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'

function worker(scope = 'https://cocina.example/cuaderno-cocina/', deferClaim = false, manifest) {
    const routes = [], events = {}, deleted = [], pending = [], shifted = []
    let fallback, precached, cacheDetails
    let claims = 0, releaseClaim
    const claim = deferClaim ? new Promise(resolve => { releaseClaim = resolve }) : Promise.resolve()
    class Strategy {
        constructor(options = {}) { this.options = options; this.kind = this.constructor.name }
    }
    class Queue {
        constructor(name, options) { this.name = name; this.options = options; pending.push(this); this.entries = [{request: 'legacy-private-write'}] }
        async shiftRequest() { const entry = this.entries.shift(); if (entry) shifted.push(entry); return entry }
        async replayRequests() { throw new Error('Offline requests must never be replayed') }
        async getAll() { return this.entries }
    }
    const context = {
        URL, Request, Response, console,
        registerRoute: (match, handler, method = 'GET') => routes.push({match, handler, method}),
        setCatchHandler: fn => { fallback = fn }, precacheAndRoute: entries => { precached = entries }, cleanupOutdatedCaches: () => {}, clientsClaim: () => {},
        setCacheNameDetails: details => { cacheDetails = details },
        CacheFirst: class CacheFirst extends Strategy {}, NetworkFirst: class NetworkFirst extends Strategy {},
        NetworkOnly: class NetworkOnly extends Strategy {}, StaleWhileRevalidate: class StaleWhileRevalidate extends Strategy {},
        ExpirationPlugin: class {}, BackgroundSyncPlugin: class {}, Queue,
        caches: {delete: async name => { deleted.push(name); return true }},
        addEventListener: (name, fn) => { (events[name] ??= []).push(fn) },
    }
    context.self = {
        __WB_MANIFEST: manifest ?? [{url: 'assets/main.js', revision: '1'}, {url: 'assets/cuaderno-logo-123abc.svg', revision: '2'}, {url: '/static/foreign.js', revision: '3'}, {url: '/cuaderno-cocina/api/private/', revision: '4'}, {url: 'https://other.example/static/foreign.js', revision: '5'}, {url: '/cuaderno-cocina/media/private.jpg', revision: '6'}], location: {origin: 'https://cocina.example'},
        registration: {scope}, skipWaiting: () => {},
        clients: {claim: () => { claims++; return claim }},
        addEventListener: context.addEventListener,
    }
    const source = readFileSync(new URL('../service-worker.ts', import.meta.url), 'utf8').replace(/^import .*?from .*?;?\r?$/gm, '')
    // The worker only uses these two TypeScript declarations; no build dependency is needed.
    const js = source.replace(/^declare let self: ServiceWorkerGlobalScope$/m, '').replace('({queue}: {queue: Queue})', '({queue})').replace(/ as const/g, '')
    vm.runInNewContext(js, context)
    function route(path, destination = '', method = 'GET') {
        const url = new URL(path, context.self.location.origin)
        const request = {url: url.href, destination, method}
        return routes.find(r => r.method === method && (typeof r.match === 'function' ? r.match({request, url, sameOrigin: url.origin === context.self.location.origin}) : r.match.test(url.href)))
    }
    return {route, routes, events, deleted, pending, shifted, fallback, precached, cacheDetails, claims: () => claims, releaseClaim}
}

test('authenticated API, media and HTML never enter a runtime cache', () => {
    const w = worker()
    for (const [url, destination] of [['/cuaderno-cocina/api/recipe/1/', ''], ['/cuaderno-cocina/api/cuaderno/services/', ''], ['/cuaderno-cocina/media/recipes/private.jpg', 'image'], ['/cuaderno-cocina/recipe/1/', 'document'], ['/cuaderno-cocina/accounts/logout/', 'document'], ['/cuaderno-cocina/accounts/login/', 'document'], ['https://bucket.example/private.jpg', 'image']]) {
        assert.equal(w.route(url, destination)?.handler.kind, 'NetworkOnly', url)
    }
    assert.equal(w.route('/cuaderno-cocina/static/vue3/logo.png', 'image')?.handler.kind, 'CacheFirst')
})

test('offline writes are network-only and cannot enqueue another session’s changes', () => {
    const w = worker()
    for (const method of ['POST', 'PATCH', 'PUT', 'DELETE']) {
        const route = w.route('/cuaderno-cocina/api/shopping-list-entry/1/', '', method)
        assert.equal(route?.handler.kind, 'NetworkOnly', method)
        assert.equal(route.handler.options.plugins?.some(p => p.fetchDidFail), undefined)
    }
})

test('activation preserves foreign caches and discards only the namespaced queue', async () => {
    const w = worker(), promises = []
    for (const fn of w.events.activate ?? []) fn({waitUntil: p => promises.push(p)})
    await Promise.all(promises)
    assert.deepEqual(w.deleted, [])
    assert.equal(w.pending[0].name, 'cuaderno-%2Fcuaderno-cocina%2F-shopping-sync-queue')
    assert.equal(w.shifted.length, 1)
    assert.equal(w.pending[0].entries.length, 0)
    w.pending[0].entries.push({request: 'old'})
    await w.pending[0].options.onSync({queue: w.pending[0]})
    assert.equal(w.pending[0].entries.length, 0)
    assert.ok(!w.deleted.includes('assets'))
})

test('offline fallback is a public Spanish document without rendering a session', async () => {
    const response = await worker().fallback({request: {destination: 'document'}})
    assert.equal(response.status, 503)
    assert.match(await response.text(), /Sin conexión/)
    assert.equal(response.headers.get('Cache-Control'), 'no-store')
})


test('precache contains the own public logo while lazy scripts keep their runtime route', () => {
    const w = worker()
    assert.deepEqual(Array.from(w.precached, entry => entry.url), [
        'https://cocina.example/cuaderno-cocina/static/vue3/assets/cuaderno-logo-123abc.svg',
    ])
    assert.equal(w.route('/cuaderno-cocina/static/vue3/assets/main.js', 'script')?.handler.kind, 'NetworkFirst')
    assert.equal(w.cacheDetails.prefix, 'cuaderno-%2Fcuaderno-cocina%2F')
    for (const route of w.routes) {
        if (route.handler.kind !== 'NetworkOnly') {
            assert.ok(route.handler.options.cacheName.startsWith(w.cacheDetails.prefix + '-'))
        }
    }
})

test('activation stays alive until the scoped client claim completes', async () => {
    const w = worker(undefined, true), promises = []
    for (const fn of w.events.activate ?? []) fn({waitUntil: p => promises.push(p)})
    assert.equal(w.claims(), 1)
    let settled = false
    const activation = Promise.all(promises).then(() => { settled = true })
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(settled, false, 'claim must belong to the activation lifetime')
    w.releaseClaim()
    await activation
    assert.equal(settled, true)
})

test('first installation does not fetch unused language and lazy page chunks', () => {
    const manifest = Array.from({length: 277}, (_, i) => ({url: `assets/page-${i}.js`, revision: String(i)}))
    manifest.push({url: 'assets/cuaderno-logo-candidate.svg', revision: 'logo'})
    const w = worker(undefined, false, manifest)
    assert.equal(w.precached.length, 1)
    assert.match(w.precached[0].url, /\/assets\/cuaderno-logo-candidate\.svg$/)
})

test('foreign root and sibling assets cannot match a Cuaderno cache route', () => {
    const w = worker()
    for (const path of ['/static/vue3/logo.png', '/other/static/main.js', '/cuaderno-cocina-other/static/main.js', '/jsi18n/', '/cuaderno-cocina/jsi18n/']) {
        for (const destination of ['image', 'script', 'style']) {
            const route = w.route(path, destination)
            assert.ok(!route || route.handler.kind === 'NetworkOnly', path)
        }
    }
})

test('scope and cache isolation follow another deployment prefix', () => {
    const w = worker('https://cocina.example/kitchen/')
    assert.equal(w.route('/kitchen/static/vue3/main.js', 'script')?.handler.kind, 'NetworkFirst')
    assert.equal(w.route('/cuaderno-cocina/static/vue3/main.js', 'script'), undefined)
    assert.equal(w.cacheDetails.prefix, 'cuaderno-%2Fkitchen%2F')
    assert.equal(w.pending[0].name, 'cuaderno-%2Fkitchen%2F-shopping-sync-queue')
})

test('a root scope cannot initialize a Cuaderno worker on a shared origin', () => {
    assert.throws(() => worker('https://cocina.example/'), /prefix/)
})


test('queue status and replay messages discard only own pending writes', async () => {
    const w = worker(), replies = [], promises = []
    for (const type of ['BGSYNC_COUNT_QUEUE', 'BGSYNC_REPLAY_REQUESTS']) {
        w.pending[0].entries.push({request: 'prior-session'})
        for (const handler of w.events.message) handler({
            data: {type}, ports: [{postMessage: reply => replies.push(reply)}],
            waitUntil: promise => promises.push(promise),
        })
        await Promise.all(promises)
        assert.equal(w.pending[0].entries.length, 0)
    }
    assert.deepEqual(replies, [0, 'REPLAY_DISABLED'])
    assert.equal(w.pending.length, 1)
    assert.ok(w.pending[0].name.startsWith(w.cacheDetails.prefix))
})
