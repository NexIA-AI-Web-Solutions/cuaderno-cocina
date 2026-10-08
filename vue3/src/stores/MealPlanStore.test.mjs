import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
import {createPinia, setActivePinia} from 'pinia'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`

test('failed native calendar fetch stops loading, reports the error and permits an exact-period retry', async () => {
    const failure = new Error('Synthetic native network failure')
    const requests = [], errors = []
    const bridge = '__cuadernoNativeMealPlanFailureTest'
    globalThis[bridge] = {
        errors,
        list(request) {
            requests.push(request)
            return requests.length === 1 ? Promise.reject(failure)
                : Promise.resolve({results: [{id: 7, title: 'Synthetic native plan'}], next: null})
        },
    }
    try {
        const dependencies = new Map([
            ['pinia', import.meta.resolve('pinia')], ['vue', import.meta.resolve('vue')],
            ['luxon', import.meta.resolve('luxon')],
            ['@/openapi', moduleUrl(`export class ApiApi {
                apiMealPlanList(request) {return globalThis.${bridge}.list(request)}
            }`)],
            ['@/stores/MessageStore', moduleUrl(`
                export const ErrorMessageType = {FETCH_ERROR: 'fetch'};
                export const PreparedMessage = {}, MessageType = {};
                export const useMessageStore = () => ({addError: (...args) => globalThis.${bridge}.errors.push(args)});
            `)],
        ])
        const source = readFileSync(new URL('./MealPlanStore.ts', import.meta.url), 'utf8')
        let code = ts.transpileModule(source, {compilerOptions: {
            module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
        }}).outputText
        code = code.replace(/from (["'])([^"']+)\1/g, (original, quote, name) => {
            assert.ok(dependencies.has(name), `Unexpected native store dependency: ${name}`)
            return `from ${JSON.stringify(dependencies.get(name))}`
        })
        setActivePinia(createPinia())
        const {useMealPlanStore} = await import(moduleUrl(code))
        const store = useMealPlanStore()
        const from = new Date('2026-10-05T12:00:00Z'), to = new Date('2026-10-25T12:00:00Z')
        const first = store.refreshFromAPI(from, to)
        assert.equal(store.loading, true)
        await first
        assert.equal(store.loading, false, 'a failed native period must not leave the calendar loading forever')
        assert.deepEqual(store.currently_updating.map(date => date.getTime()), [0, 0])
        assert.equal(errors.length, 1)
        assert.equal(errors[0][0], 'fetch')
        assert.equal(errors[0][1], failure)
        const retry = store.refreshFromAPI(from, to)
        assert.equal(requests.length, 2, 'the same Date objects must remain retryable after failure')
        assert.equal(store.loading, true)
        await retry
        assert.equal(store.loading, false)
        assert.equal(store.planList[0].id, 7)
        assert.equal(errors.length, 1)
        assert.equal(requests[1].fromDate, '2026-10-05')
        assert.equal(requests[1].toDate, '2026-10-25')
    } finally {
        delete globalThis[bridge]
    }
})
