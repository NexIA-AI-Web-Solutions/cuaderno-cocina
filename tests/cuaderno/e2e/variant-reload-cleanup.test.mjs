// Synchronization regression for the actual variant spec, not a browser/API substitute.
import test from 'node:test'
import assert from 'node:assert/strict'
import {EventEmitter} from 'node:events'
import {readFileSync} from 'node:fs'
import {createRequire, stripTypeScriptTypes} from 'node:module'
import {pathToFileURL} from 'node:url'

const require = createRequire(import.meta.url)
const playwrightUrl = JSON.stringify(pathToFileURL(require.resolve('@playwright/test')).href)
const {expect: nativeExpect} = require('@playwright/test')
let barrierSource = stripTypeScriptTypes(readFileSync(new URL('./native-read-barrier.ts', import.meta.url), 'utf8'))
barrierSource = barrierSource.replace(/import \{expect,[^}]*\} from '@playwright\/test'/,
    `import playwright from ${playwrightUrl}; const {expect} = playwright`)
barrierSource = barrierSource.replace("import {appPath} from './contracts.js'", "const appPath = suffix => '/cuaderno-cocina' + suffix")
const {withAuthenticatedReadBarrier} = await import('data:text/javascript;base64,' + Buffer.from(barrierSource).toString('base64'))
const source = stripTypeScriptTypes(readFileSync(new URL('./functional-extensions-acceptance.spec.ts', import.meta.url), 'utf8'))
const variantStart = source.indexOf("test('extras: variante usa la copia nativa y conserva el vínculo tras recarga'")
const variantEnd = source.indexOf("test('planificación: calendario nativo cinco semanas", variantStart)
assert.ok(variantStart >= 0 && variantEnd > variantStart)
const variant = source.slice(variantStart, variantEnd)
const linkAssertion = "await expect(page.locator('.recipe-extras').getByRole('link', {name: recipe.name, exact: true})).toBeVisible()"
const reloadStart = variant.indexOf(linkAssertion) + linkAssertion.length
assert.ok(reloadStart >= linkAssertion.length)
const reloadAndCleanup = variant.slice(reloadStart, variant.lastIndexOf('\n})'))
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const actualReloadAndCleanup = new AsyncFunction('page', 'recipe', 'copy', 'readExtras', 'removeRecipe', 'expect', 'withAuthenticatedReadBarrier',
    'try {' + reloadAndCleanup)
const deferred = () => {let resolve; const promise = new Promise(done => {resolve = done}); return {promise, resolve}}
const flush = async () => {for (let i = 0; i < 24; i++) await Promise.resolve()}

test('actual variant reload finishes late authenticated GETs and view-log POST before deleting its fixtures', async () => {
    process.env.BASE_URL = 'https://127.0.0.1:18443/cuaderno-cocina/'
    const recipe = {id: 52, name: 'CUADERNO-E2E extras source'}, copy = {id: 53, name: 'CUADERNO-E2E extras source(Copiar)'}
    const page = new EventEmitter(), lateMounted = deferred(), extrasBody = deferred(), yieldsBody = deferred(), postBody = deferred()
    const uiReady = deferred(), deleted = [], requests = []
    const frame = {}
    page.mainFrame = () => frame
    const link = {variantLink: true}
    let reloaded = false
    const emit = (method, path, body, status) => {
        requests.push({method, path, status})
        page.emit('request', {method: () => method, url: () => process.env.BASE_URL.replace(/\/$/, '') + path,
            isNavigationRequest: () => false, frame: () => frame,
            response: async () => ({status: () => status, finished: () => body})})
    }
    page.reload = async () => {
        reloaded = true
        page.emit('request', {method: () => 'GET', url: () => process.env.BASE_URL + 'recipe/53',
            isNavigationRequest: () => true, frame: () => frame})
        emit('GET', '/api/user-preference/', Promise.resolve(null), 200)
        emit('GET', '/api/recipe/53/', Promise.resolve(null), 200)
        // Original trace: extras and view-log mount after user-preference resolves,
        // while direct API assertions can already read the persisted variant.
        setImmediate(() => {
            const exists = !deleted.includes(53)
            emit('GET', '/api/recipe/flat/', Promise.resolve(null), 200)
            emit('GET', '/api/cuaderno/recipes/53/extras/', extrasBody.promise, exists ? 200 : 404)
            emit('GET', '/api/cuaderno/recipes/53/ingredient-yields/', yieldsBody.promise, exists ? 200 : 404)
            emit('POST', '/api/view-log/', postBody.promise, exists ? 201 : 400)
            void extrasBody.promise.then(() => uiReady.resolve(exists))
            lateMounted.resolve()
        })
    }
    page.locator = selector => {
        assert.equal(selector, '.recipe-extras')
        return {getByRole(role, options) {
            assert.equal(role, 'link'); assert.equal(options.name, recipe.name); assert.equal(options.exact, true)
            return link
        }}
    }
    const expect = value => value === link ? {async toBeVisible() {assert.equal(await uiReady.promise, true)}} : nativeExpect(value)
    const readExtras = async (_page, id) => id === copy.id ? {variant_of: recipe} : {variants: [copy]}
    const removeRecipe = async (_page, item) => {deleted.push(item.id)}
    const run = actualReloadAndCleanup(page, recipe, copy, readExtras, removeRecipe, expect, withAuthenticatedReadBarrier)
    void run.catch(() => {})
    try {
        await lateMounted.promise; await flush()
        assert.equal(reloaded, true)
        assert.deepEqual(deleted, [], 'reload and direct API reads must not permit cleanup before authenticated UI requests start')
        extrasBody.resolve(null); await flush()
        assert.deepEqual(deleted, [], 'rendered variant link does not prove ingredient-yields or view-log body completion')
        yieldsBody.resolve(null); await flush()
        assert.deepEqual(deleted, [], 'native GET completion must not permit cleanup while view-log POST is unfinished')
        postBody.resolve(null); await run
        assert.deepEqual(deleted, [copy.id, recipe.id])
        assert.deepEqual(requests.map(row => row.status), [200, 200, 200, 200, 200, 201])
        assert.equal(page.listenerCount('request'), 0)
    } finally {
        extrasBody.resolve(null); yieldsBody.resolve(null); postBody.resolve(null)
        await run
    }
})
