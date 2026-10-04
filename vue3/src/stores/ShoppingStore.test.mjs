import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
import {createPinia, setActivePinia} from 'pinia'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const vueUrl = import.meta.resolve('vue')
const piniaUrl = import.meta.resolve('pinia')
const luxonUrl = import.meta.resolve('luxon')

let unitId = 0
async function createStore(api) {
    const id = ++unitId
    const timers = new Map()
    let nextTimer = 0
    globalThis.__shoppingStoreUnit ??= new Map()
    globalThis.__shoppingStoreUnit.set(id, {api})
    Object.defineProperty(globalThis, 'navigator', {configurable: true, value: {onLine: true}})
    Object.defineProperty(globalThis, 'document', {configurable: true, value: {location: {href: 'https://example.test/shopping'}}})
    globalThis.window = {
        setTimeout(callback) {
            const timer = ++nextTimer
            timers.set(timer, callback)
            return timer
        },
    }
    globalThis.clearTimeout = timer => timers.delete(timer)

    const openapi = moduleUrl(`
        export class ResponseError extends Error {
            name = 'ResponseError';
            constructor(response, message = 'Response returned an error code') { super(message); this.response = response; }
        }
        export class FetchError extends Error {
            name = 'FetchError';
            constructor(cause, message = 'The request failed') { super(message); this.cause = cause; }
        }
        export class ApiApi {
            apiShoppingListEntryBulkCreate(request) { return globalThis.__shoppingStoreUnit.get(${id}).api.bulk(request); }
            apiShoppingListEntryRetrieve(request) { return globalThis.__shoppingStoreUnit.get(${id}).api.retrieve(request); }
        }
    `)
    const shoppingTypes = moduleUrl(`export const ShoppingGroupingOptions = {CATEGORY: 'Category', CREATED_BY: 'CreatedBy', RECIPE: 'Recipe'};`)
    const messages = moduleUrl(`
        export const ErrorMessageType = {UPDATE_ERROR: 'update', FETCH_ERROR: 'fetch'};
        export const PreparedMessage = {};
        export const useMessageStore = () => ({addError: error => globalThis.__shoppingStoreUnit.get(${id}).api.errors.push(error), addPreparedMessage() {}});
    `)
    const preferences = moduleUrl(`
        const store = {deviceSettings: {
            shopping_selected_grouping: 'Category', shopping_selected_supermarket: null,
            shopping_show_selected_supermarket_only: false,
        }, userSettings: {}};
        export const useUserPreferenceStore = () => store;
    `)
    const logic = moduleUrl(`export const isEntryVisible = () => true; export const isDelayed = () => false;`)
    const replacements = new Map([
        ['pinia', piniaUrl], ['vue', vueUrl], ['luxon', luxonUrl],
        ['@/openapi', openapi], ['@/types/Shopping', shoppingTypes],
        ['@/stores/MessageStore', messages], ['@/stores/UserPreferenceStore', preferences],
        ['@/utils/logic_utils', logic],
    ])
    const source = readFileSync(new URL('./ShoppingStore.ts', import.meta.url), 'utf8')
    let code = ts.transpileModule(source, {compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    }}).outputText
    code = code.replace(/from (["'])([^"']+)\1/g, (original, quote, name) => {
        assert.ok(replacements.has(name), `Unexpected dependency ${name}`)
        return `from ${JSON.stringify(replacements.get(name))}`
    })
    setActivePinia(createPinia())
    const [{useShoppingStore}, {ResponseError, FetchError}] = await Promise.all([
        import(moduleUrl(code)), import(openapi),
    ])
    const store = useShoppingStore()
    return {
        store,
        ResponseError,
        FetchError,
        timers,
        async runLatest() {
            const scheduled = [...timers.entries()].at(-1)
            assert.ok(scheduled, 'expected a queued synchronization')
            timers.delete(scheduled[0])
            scheduled[1]()
            for (let index = 0; index < 30; index += 1) {
                await new Promise(resolve => setImmediate(resolve))
            }
        },
        close() { timers.clear(); globalThis.__shoppingStoreUnit.delete(id) },
    }
}

function entry(id, revision = `opaque-${id}`) {
    return {
        id, revision, checked: false, amount: 1, shoppingLists: [],
        food: {id, name: `Food ${id}`, supermarketCategory: null},
        createdBy: {displayName: 'Cocina'},
    }
}

test('offline double toggle stays FIFO and keeps the original revision until a write succeeds', async () => {
    const calls = []
    const mounted = await createStore({bulk: request => { calls.push(request); return Promise.resolve({}) }, retrieve: assert.fail, errors: []})
    try {
        navigator.onLine = false
        const item = entry(1, '2026-10-04T12:30:00.123456Z')
        mounted.store.entries.set(1, item)
        mounted.store.setEntriesCheckedState([item], true, true)
        mounted.store.setEntriesCheckedState([item], false, true)
        await mounted.runLatest()
        assert.equal(calls.length, 0)
        assert.deepEqual(mounted.store.itemCheckSyncQueue.map(operation => ({checked: operation.checked, revision: operation.revisions['1']})), [
            {checked: true, revision: '2026-10-04T12:30:00.123456Z'},
            {checked: false, revision: '2026-10-04T12:30:00.123456Z'},
        ])
    } finally { mounted.close() }
})

test('successful revision propagates to the next intent and undo uses its own latest precondition', async () => {
    const calls = []
    const revisions = ['opaque-r1', 'opaque-r2']
    const mounted = await createStore({
        bulk(request) {
            calls.push(structuredClone(request.shoppingListEntryBulk))
            return Promise.resolve({revisions: {'1': revisions[calls.length - 1]}, timestamp: new Date('2026-10-04T12:30:00Z')})
        },
        retrieve: assert.fail, errors: [],
    })
    try {
        const item = entry(1, '2026-10-04T12:30:00.123456Z')
        mounted.store.entries.set(1, item)
        mounted.store.setEntriesCheckedState([item], true, true)
        await mounted.runLatest()
        assert.equal(mounted.store.entries.get(1).revision, 'opaque-r1')
        mounted.store.undoChange()
        await mounted.runLatest()
        assert.deepEqual(calls.map(call => ({checked: call.checked, revision: call.revisions['1']})), [
            {checked: true, revision: '2026-10-04T12:30:00.123456Z'},
            {checked: false, revision: 'opaque-r1'},
        ])
        assert.equal(mounted.store.entries.get(1).revision, 'opaque-r2')
    } finally { mounted.close() }
})

test('a conflict drops every causally overlapping context and refreshes without an automatic write', async () => {
    const calls = []
    const retrieved = []
    const errors = []
    const api = {
        failure: null,
        bulk(request) { calls.push(request); return Promise.reject(this.failure) },
        retrieve({id}) { retrieved.push(id); return Promise.resolve({...entry(id, `server-${id}`), checked: true}) },
        errors,
    }
    const mounted = await createStore(api)
    try {
        api.failure = new mounted.ResponseError(new Response(null, {status: 409}))
        const first = entry(1)
        const second = entry(2)
        mounted.store.entries.set(1, first)
        mounted.store.entries.set(2, second)
        mounted.store.setEntriesCheckedState([second], true, false)
        mounted.store.setEntriesCheckedState([first], true, false)
        mounted.store.setEntriesCheckedState([first, second], false, false)
        await mounted.runLatest()
        assert.equal(calls.length, 1)
        assert.deepEqual(retrieved.sort(), [1, 2], JSON.stringify({calls, queue: mounted.store.itemCheckSyncQueue, errors: errors.map(String)}))
        assert.equal(mounted.store.itemCheckSyncQueue.length, 0)
        assert.equal(mounted.store.entries.get(1).revision, 'server-1')
        assert.equal(mounted.store.entries.get(2).revision, 'server-2')
    } finally { mounted.close() }
})

for (const status of [401, 403, 500]) {
    test(`HTTP ${status} retains queued intent and undo without refreshing`, async () => {
        const calls = []
        const retrieved = []
        const api = {
            failure: null,
            bulk(request) { calls.push(request); return Promise.reject(this.failure) },
            retrieve({id}) { retrieved.push(id); return Promise.resolve(entry(id, `server-${id}`)) },
            errors: [],
        }
        const mounted = await createStore(api)
        try {
            api.failure = new mounted.ResponseError(new Response(null, {status}))
            const item = entry(1)
            mounted.store.entries.set(1, item)
            mounted.store.setEntriesCheckedState([item], true, true)
            await mounted.runLatest()
            assert.equal(calls.length, 1)
            assert.deepEqual(retrieved, [])
            assert.equal(mounted.store.itemCheckSyncQueue.length, 1)
            assert.equal(mounted.store.itemCheckSyncQueue[0].status, 'waiting_failed_before')
            assert.equal(mounted.store.undoStack.length, 1)
            assert.equal(mounted.store.entries.get(1).checked, true)
        } finally { mounted.close() }
    })
}

test('FetchError retains queued intent and undo without refreshing', async () => {
    const calls = []
    const retrieved = []
    const api = {
        failure: null,
        bulk(request) { calls.push(request); return Promise.reject(this.failure) },
        retrieve({id}) { retrieved.push(id); return Promise.resolve(entry(id, `server-${id}`)) },
        errors: [],
    }
    const mounted = await createStore(api)
    try {
        api.failure = new mounted.FetchError(new Error('offline'))
        const item = entry(1)
        mounted.store.entries.set(1, item)
        mounted.store.setEntriesCheckedState([item], true, true)
        await mounted.runLatest()
        assert.equal(calls.length, 1)
        assert.deepEqual(retrieved, [])
        assert.equal(mounted.store.itemCheckSyncQueue.length, 1)
        assert.equal(mounted.store.itemCheckSyncQueue[0].status, 'waiting_failed_before')
        assert.equal(mounted.store.undoStack.length, 1)
        assert.equal(mounted.store.entries.get(1).checked, true)
    } finally { mounted.close() }
})
