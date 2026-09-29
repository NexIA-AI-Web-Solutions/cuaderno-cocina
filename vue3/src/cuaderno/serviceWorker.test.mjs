import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function worker() {
    const routes = [], events = {}, deleted = [], pending = [], shifted = []
    let fallback
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
        setCatchHandler: fn => { fallback = fn }, precacheAndRoute: () => {}, cleanupOutdatedCaches: () => {}, clientsClaim: () => {},
        CacheFirst: class CacheFirst extends Strategy {}, NetworkFirst: class NetworkFirst extends Strategy {},
        NetworkOnly: class NetworkOnly extends Strategy {}, StaleWhileRevalidate: class StaleWhileRevalidate extends Strategy {},
        ExpirationPlugin: class {}, BackgroundSyncPlugin: class {}, Queue,
        caches: {delete: async name => { deleted.push(name); return true }},
        addEventListener: (name, fn) => { (events[name] ??= []).push(fn) },
    }
    context.self = {
        __WB_MANIFEST: [], location: {origin: 'https://cocina.example'},
        registration: {scope: 'https://cocina.example/'}, skipWaiting: () => {},
        addEventListener: context.addEventListener,
    }
    const source = readFileSync(new URL('../service-worker.ts', import.meta.url), 'utf8').replace(/^import .*?from .*?;?\r?$/gm, '')
    const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2022}}).outputText
    vm.runInNewContext(js, context)
    function route(path, destination = '', method = 'GET') {
        const url = new URL(path, context.self.location.origin)
        const request = {url: url.href, destination, method}
        return routes.find(r => r.method === method && (typeof r.match === 'function' ? r.match({request, url, sameOrigin: url.origin === context.self.location.origin}) : r.match.test(url.href)))
    }
    return {route, routes, events, deleted, pending, shifted, fallback}
}

test('authenticated API, media and HTML never enter a runtime cache', () => {
    const w = worker()
    for (const [url, destination] of [['/api/recipe/1/', ''], ['/api/cuaderno/services/', ''], ['/media/recipes/private.jpg', 'image'], ['/recipe/1/', 'document'], ['https://bucket.example/private.jpg', 'image']]) {
        assert.equal(w.route(url, destination)?.handler.kind, 'NetworkOnly', url)
    }
    assert.equal(w.route('/static/vue3/logo.png', 'image')?.handler.kind, 'CacheFirst')
})

test('offline writes are network-only and cannot enqueue another session’s changes', () => {
    const w = worker()
    for (const method of ['POST', 'PATCH', 'PUT', 'DELETE']) {
        const route = w.route('/api/shopping-list-entry/1/', '', method)
        assert.equal(route?.handler.kind, 'NetworkOnly', method)
        assert.equal(route.handler.options.plugins?.some(p => p.fetchDidFail), undefined)
    }
})

test('activation clears legacy private caches and discards, never replays, the old queue', async () => {
    const w = worker(), promises = []
    for (const fn of w.events.activate ?? []) fn({waitUntil: p => promises.push(p)})
    await Promise.all(promises)
    assert.deepEqual([...w.deleted].sort(), ['api', 'api-recipe', 'html', 'images', 'offline-html'])
    assert.equal(w.shifted.length, 1)
    assert.equal(w.pending[0].entries.length, 0)
    w.pending[0].entries.push({request: 'old'})
    await w.pending[0].options.onSync({queue: w.pending[0]})
    assert.equal(w.pending[0].entries.length, 0)
    assert.ok(!w.deleted.includes('assets'))
})

test('offline fallback is a public Spanish document without rendering a session', async () => {
    const response = await worker().fallback({event: {request: {destination: 'document'}}})
    assert.equal(response.status, 503)
    assert.match(await response.text(), /Sin conexión/)
    assert.equal(response.headers.get('Cache-Control'), 'no-store')
})
