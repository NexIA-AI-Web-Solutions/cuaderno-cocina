import {readFileSync} from 'node:fs'
import {stripTypeScriptTypes} from 'node:module'
import vm from 'node:vm'

export const deferred = () => {
    let resolve, reject
    const promise = new Promise((yes, no) => {resolve = yes; reject = no})
    return {promise, resolve, reject}
}
export async function settle() { for (let i = 0; i < 12; i++) await Promise.resolve() }

// Execute the shipped script with synthetic business dependencies, without DOM or network.
export function component(path, names, {props = {}, api = {}, globals = {}} = {}) {
    const text = readFileSync(new URL('../../' + path, import.meta.url), 'utf8')
    const source = path.endsWith('.vue') ? text.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1] : text
    let code = stripTypeScriptTypes(source)
    code = code.replace(/^import[\s\S]*?\sfrom\s+['"][^'"]+['"];?\s*$/gm, '')
        .replace(/^import\s+['"][^'"]+['"];?\s*$/gm, '')
        .replace(/^export\s+/gm, '')
        .replace(/\bimport\.meta\b/g, 'globalThis.__moduleMeta')
    const hooks = {mounted: [], beforeMount: [], unmounted: [], watchers: []}
    const messages = [], navigations = [], timers = new Map()
    let nextTimer = 1
    const ref = value => ({value})
    const generic = {model: {isPaginated: true, localizationKey: 'Name'}, ...api}
    const store = {deviceSettings: {search_itemsPerPage: 25, search_visibleFilters: []}, activeSpace: {}, userSettings: {}, activeUserSpace: null}
    const context = vm.createContext({
        console: {log() {}, warn() {}, error() {}}, Promise, Map, Set, URL, URLSearchParams, FormData, Response, AbortController,
        __moduleMeta: {},
        ref, shallowRef: ref, useTitle: () => ref(''), computed: fn => ({get value() {return fn()}}), toRaw: x => x, markRaw: x => x,
        onMounted: fn => hooks.mounted.push(fn), onBeforeMount: fn => hooks.beforeMount.push(fn),
        onUnmounted: fn => hooks.unmounted.push(fn), onBeforeUnmount: fn => hooks.unmounted.push(fn),
        watch: (source, fn, options) => hooks.watchers.push({source, fn, options}), nextTick: fn => Promise.resolve().then(fn),
        defineEmits: () => (...args) => messages.push(['emit', ...args]), defineModel: () => ref(false),
        defineProps: schema => Object.fromEntries(Object.entries(schema).map(([key, spec]) => [key, key in props ? props[key] : spec.default])),
        useI18n: () => ({t: key => key}), useDisplay: () => ({mobile: ref(false), mdAndUp: ref(true)}),
        useDebounceFn: fn => fn, getGenericModelFromString: () => generic,
        ApiApi: function () {return api}, useUserPreferenceStore: () => store,
        useMessageStore: () => ({addError: (...x) => messages.push(x), addMessage: (...x) => messages.push(x), addPreparedMessage: (...x) => messages.push(x)}),
        ErrorMessageType: {FETCH_ERROR: 'fetch', UPDATE_ERROR: 'update', CREATE_ERROR: 'create', DELETE_ERROR: 'delete'},
        MessageType: {ERROR: 'error', WARNING: 'warning'}, PreparedMessage: {CREATE_SUCCESS: 'created', RATE_LIMIT: 'rate'},
        useRouter: () => ({push: x => {navigations.push(x);return Promise.resolve()}}),
        useUrlSearchParams: () => ({}), useRouteQuery: (_name, value) => ref(value),
        useDebouncedSearch: () => ({inputValue: ref(''), debouncedValue: ref(''), signal: ref(undefined), reset() {}, resetQuery() {}}),
        VSelect: {}, VDateInput: {}, VNumberInput: {}, VModelSelect: {}, RatingField: {},
        boolOrUndefinedTransformer() {}, numberOrUndefinedTransformer() {}, routeQueryDateTransformer() {}, toNumberArray() {},
        setTimeout: fn => {const id = nextTimer++;timers.set(id, fn);return id}, clearTimeout: id => timers.delete(id),
        window: {scrollTo() {}}, ...globals,
    })
    new vm.Script(code + '\n;globalThis.exposed = {' + names.join(',') + '};', {filename: path}).runInContext(context)
    return {exposed: context.exposed, hooks, messages, navigations, timers, store, context}
}

// Execute the actual template event expression with Vue-style top-level ref unwrapping.
export function templateEvent(path, pattern, values) {
    const text = readFileSync(new URL('../../' + path, import.meta.url), 'utf8')
    const expression = text.match(pattern)?.[1]
    if (!expression) throw new Error('Actual template event missing')
    const bindings = {}
    for (const [key, value] of Object.entries(values)) {
        Object.defineProperty(bindings, key, {enumerable: true, configurable: true,
            get: () => value && typeof value === 'object' && 'value' in value ? value.value : value,
            set: updated => {if (value && typeof value === 'object' && 'value' in value) value.value = updated;else values[key] = updated},
        })
    }
    const executable = expression.includes('=>') ? stripTypeScriptTypes('const handler = ' + expression + '; handler') : expression
    const result = new vm.Script(executable).runInNewContext(bindings)
    return typeof result === 'function' ? result(values.$event) : result
}
