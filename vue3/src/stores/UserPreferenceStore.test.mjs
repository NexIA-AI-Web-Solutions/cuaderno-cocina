import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
import {createPinia, setActivePinia} from 'pinia'
import {reactive} from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const vueUrl = import.meta.resolve('vue')
const piniaUrl = import.meta.resolve('pinia')
const originalLocalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')

test.beforeEach(() => {
    const values = new Map()
    Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        value: {
            get length() { return values.size },
            clear() { values.clear() },
            getItem(key) { return values.get(String(key)) ?? null },
            key(index) { return [...values.keys()][index] ?? null },
            removeItem(key) { values.delete(String(key)) },
            setItem(key, value) { values.set(String(key), String(value)) },
        },
        writable: true,
    })
})

test.afterEach(() => {
    if (originalLocalStorage) {
        Object.defineProperty(globalThis, 'localStorage', originalLocalStorage)
    } else {
        delete globalThis.localStorage
    }
})

async function createStore(route) {
    let setupActive = true
    globalThis.__userPreferenceRoute = route
    globalThis.__userPreferenceSetupActive = () => setupActive

    const vueUse = moduleUrl(`
        import {ref} from ${JSON.stringify(vueUrl)};
        export const useStorage = (_key, initial) => ref(initial);
    `)
    const router = moduleUrl(`
        export const useRoute = () => {
            if (!globalThis.__userPreferenceSetupActive()) throw new Error('useRoute called after store setup');
            return globalThis.__userPreferenceRoute;
        };
        export const useRouter = () => ({push: () => Promise.resolve()});
    `)
    const vuetify = moduleUrl(`export const useTheme = () => ({change() {}});`)
    const openapi = moduleUrl(`export class ApiApi {}; export const ServerSettings = {}; export const Space = {}; export const Unit = {}; export const UserPreference = {}; export const UserSpace = {};`)
    const shopping = moduleUrl(`export const ShoppingGroupingOptions = {CATEGORY: 'Category'};`)
    const messages = moduleUrl(`export const ErrorMessageType = {}; export const PreparedMessage = {}; export const useMessageStore = () => ({addError() {}, addPreparedMessage() {}});`)
    const settings = moduleUrl(`export const DeviceSettings = {};`)
    const replacements = new Map([
        ['pinia', piniaUrl], ['vue', vueUrl], ['@vueuse/core', vueUse],
        ['vue-router', router], ['vuetify', vuetify], ['@/openapi', openapi],
        ['@/types/Shopping', shopping], ['@/stores/MessageStore', messages],
        ['@/types/settings', settings],
        ['@/cuaderno/storage', moduleUrl(ts.transpileModule(readFileSync(new URL('../cuaderno/storage.ts', import.meta.url), 'utf8'), {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText)],
        ['@/cuaderno/nativeRecipeWriteUi', moduleUrl(ts.transpileModule(readFileSync(new URL('../cuaderno/nativeRecipeWriteUi.ts', import.meta.url), 'utf8'), {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText)],
    ])
    const source = readFileSync(new URL('./UserPreferenceStore.ts', import.meta.url), 'utf8')
    let code = ts.transpileModule(source, {compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    }}).outputText
    code = code.replace(/from (["'])([^"']+)\1/g, (original, quote, name) => {
        assert.ok(replacements.has(name), `Unexpected dependency ${name}`)
        return `from ${JSON.stringify(replacements.get(name))}`
    })

    setActivePinia(createPinia())
    const {useUserPreferenceStore} = await import(moduleUrl(code))
    const store = useUserPreferenceStore()
    setupActive = false
    return store
}

test('print mode follows route query changes after the store setup context has ended', async () => {
    const route = reactive({query: {}})
    const store = await createStore(route)

    assert.equal(store.isPrintMode, false)
    route.query = {print: '1'}
    assert.equal(store.isPrintMode, true)
    route.query = {}
    assert.equal(store.isPrintMode, false)
})
