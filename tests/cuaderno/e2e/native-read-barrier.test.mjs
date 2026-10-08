// Synchronization unit boundary only; real browser collectors remain mandatory.
import test from 'node:test'
import assert from 'node:assert/strict'
import {EventEmitter} from 'node:events'
import {readFileSync} from 'node:fs'
import {createRequire, stripTypeScriptTypes} from 'node:module'
import {pathToFileURL} from 'node:url'

const require = createRequire(import.meta.url)
let source = stripTypeScriptTypes(readFileSync(new URL('./native-read-barrier.ts', import.meta.url), 'utf8'))
source = source.replace(/import \{expect,[^}]*\} from '@playwright\/test'/,
    `import playwright from ${JSON.stringify(pathToFileURL(require.resolve('@playwright/test')).href)}; const {expect} = playwright`)
source = source.replace("import {appPath} from './contracts.js'", "const appPath = suffix => '/cuaderno-cocina' + suffix")
const {withNativeReadBarrier} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
const deferred = () => {let resolve; const promise = new Promise(done => {resolve = done}); return {promise, resolve}}
const flush = async () => {for (let i = 0; i < 24; i++) await Promise.resolve()}
const path = kind => '/api/' + kind + '/'
function request(page, kind, response) {
    page.emit('request', {method: () => 'GET', url: () => 'https://127.0.0.1:18443/cuaderno-cocina' + path(kind), response: () => response})
}
const completed = () => Promise.resolve({finished: async () => null})

test.beforeEach(() => {process.env.BASE_URL = 'https://127.0.0.1:18443/cuaderno-cocina/'})

test('waits for Food and Unit that start after a visible heading, including their bodies', async () => {
    const page = new EventEmitter(), food = deferred(), unit = deferred()
    let settled = false
    const barrier = withNativeReadBarrier(page, async () => 'heading', [path('food'), path('unit')])
    void barrier.then(() => {settled = true}, () => {})
    await flush(); assert.equal(settled, false, 'a heading does not prove the selectors have requested their data')
    request(page, 'food', food.promise); request(page, 'unit', unit.promise)
    food.resolve(await completed()); await flush(); assert.equal(settled, false)
    const body = deferred(); unit.resolve({finished: () => body.promise})
    await flush(); assert.equal(settled, false, 'response headers do not prove its body completed')
    body.resolve(null); assert.equal(await barrier, 'heading'); assert.equal(page.listenerCount('request'), 0)
})

test('navigation keeps its own budget and native reads receive eight seconds afterwards', async t => {
    t.mock.timers.enable({apis: ['setTimeout']})
    const page = new EventEmitter(), navigation = deferred(), food = deferred()
    let failed = false
    const barrier = withNativeReadBarrier(page, () => navigation.promise, [path('food')])
    void barrier.catch(() => {failed = true})
    t.mock.timers.tick(9_000); await flush()
    assert.equal(failed, false, 'the read timer must not expire a still-authorized navigation')
    request(page, 'food', food.promise); navigation.resolve('loaded'); await flush()
    t.mock.timers.tick(7_999); await flush(); assert.equal(failed, false)
    food.resolve(await completed()); assert.equal(await barrier, 'loaded')
})

test('a missing required read fails within the unchanged eight-second read budget', async t => {
    t.mock.timers.enable({apis: ['setTimeout']})
    const page = new EventEmitter()
    const barrier = withNativeReadBarrier(page, async () => 'heading', [path('food')])
    const rejected = assert.rejects(barrier, /eight-second/)
    await flush(); t.mock.timers.tick(8_000); await rejected
    assert.equal(page.listenerCount('request'), 0)
})

test('canceled native GETs fail, whether required or an additional observed read', async () => {
    for (const required of [[], [path('food')]]) {
        const page = new EventEmitter()
        const barrier = withNativeReadBarrier(page, async () => {
            request(page, 'food', Promise.resolve(null)); return 'heading'
        }, required)
        await assert.rejects(barrier, /native GET receives a response/)
        assert.equal(page.listenerCount('request'), 0)
    }
})

test('Consulta can finish without Food or Unit while all observed native bodies remain checked', async () => {
    const page = new EventEmitter()
    assert.equal(await withNativeReadBarrier(page, async () => 'read-only'), 'read-only')
    const barrier = withNativeReadBarrier(page, async () => {
        page.emit('request', {method: () => 'GET', url: () => 'https://127.0.0.1:18443/cuaderno-cocina/api/cuaderno/edition/',
            response: async () => ({finished: async () => 'Load request cancelled'})})
    })
    await assert.rejects(barrier, /native GET body finishes/)
})

test('recipe readiness waits for required GET and POST bodies before the intentional next navigation', async () => {
    const page = new EventEmitter(), getBody = deferred(), postBody = deferred()
    let settled = false
    const barrier = withNativeReadBarrier(page, async () => 'photo-ready', [path('ingredient-yields')], [path('view-log')])
    void barrier.then(() => {settled = true}, () => {})
    request(page, 'ingredient-yields', Promise.resolve({finished: () => getBody.promise}))
    page.emit('request', {method: () => 'POST', url: () => 'https://127.0.0.1:18443/cuaderno-cocina' + path('view-log'),
        response: async () => ({finished: () => postBody.promise})})
    getBody.resolve(null); await flush()
    assert.equal(settled, false, 'the photo and GET completion must not allow navigation while view-log POST is unfinished')
    postBody.resolve(null); assert.equal(await barrier, 'photo-ready')
    assert.equal(page.listenerCount('request'), 0)
})

test('a GET on the required POST path does not satisfy the method-specific readiness signal', async () => {
    const page = new EventEmitter(), body = deferred()
    let settled = false
    const barrier = withNativeReadBarrier(page, async () => 'loaded', [], [path('view-log')])
    void barrier.then(() => {settled = true}, () => {})
    request(page, 'view-log', completed()); await flush()
    assert.equal(settled, false, 'the matching path must also have the expected POST method')
    page.emit('request', {method: () => 'POST', url: () => 'https://127.0.0.1:18443/cuaderno-cocina' + path('view-log'),
        response: async () => ({finished: () => body.promise})})
    await flush(); assert.equal(settled, false, 'POST response headers still leave its body pending')
    body.resolve(null); assert.equal(await barrier, 'loaded')
    assert.equal(page.listenerCount('request'), 0)
})

test('required POST shares the existing eight-second deadline even when it starts late', async t => {
    t.mock.timers.enable({apis: ['setTimeout']})
    const page = new EventEmitter(), body = deferred()
    const barrier = withNativeReadBarrier(page, async () => 'photo-ready', [path('ingredient-yields')], [path('view-log')])
    const rejected = assert.rejects(barrier, /eight-second/)
    request(page, 'ingredient-yields', completed()); await flush()
    t.mock.timers.tick(7_999); await flush()
    page.emit('request', {method: () => 'POST', url: () => 'https://127.0.0.1:18443/cuaderno-cocina' + path('view-log'),
        response: async () => ({finished: () => body.promise})})
    await flush(); t.mock.timers.tick(1); await rejected
    assert.equal(page.listenerCount('request'), 0)
    body.resolve(null); await flush()
})

test('canceled required POST response or body remains a failure and removes its listener', async () => {
    for (const response of [async () => null, async () => ({finished: async () => 'Load request cancelled'})]) {
        const page = new EventEmitter()
        const barrier = withNativeReadBarrier(page, async () => {
            page.emit('request', {method: () => 'POST', url: () => 'https://127.0.0.1:18443/cuaderno-cocina' + path('view-log'), response})
            return 'photo-ready'
        }, [], [path('view-log')])
        await assert.rejects(barrier, /native POST (receives a response|body finishes)/)
        assert.equal(page.listenerCount('request'), 0)
    }
})
