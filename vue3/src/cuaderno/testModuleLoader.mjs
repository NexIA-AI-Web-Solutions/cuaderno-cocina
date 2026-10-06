import {readFileSync} from 'node:fs'

let transpile
try {
    const {default: ts} = await import('typescript')
    transpile = source => ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
} catch {
    const {stripTypeScriptTypes} = await import('node:module')
    transpile = source => stripTypeScriptTypes(source, {mode: 'transform'})
}
const moduleUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const cache = new Map()
const stubs = {
    vue: 'export const ref = value => ({value});',
    '@/openapi': 'export const RecipeFromSourceResponseFromJSON = x => x, RecipeImageFromJSON = x => x, UserFileFromJSON = x => x; export class ResponseError extends Error { constructor(response) {super(); this.response = response} }',
    '@/stores/MessageStore': 'export const ErrorMessageType = {UPDATE_ERROR: 1}; export const useMessageStore = () => ({addError() {}});',
    luxon: 'export const DateTime = {};',
}
const aliases = {
    '@/utils/cookie': '../utils/cookie.ts',
    '@/utils/djangoConfig': '../utils/djangoConfig.ts',
    '@/composables/useDjangoUrls': '../composables/useDjangoUrls.ts',
}
/** Lightweight transport tests; no Vue build, browser, or dependency installation. */
export async function loadTestModule(relative) {
    if (cache.has(relative)) return cache.get(relative)
    let source = transpile(readFileSync(new URL(relative, import.meta.url), 'utf8'))
    for (const [alias, target] of Object.entries(aliases)) {
        if (source.includes(alias)) source = source.replaceAll(`"${alias}"`, JSON.stringify(await loadTestModule(target)))
    }
    for (const [alias, stub] of Object.entries(stubs)) source = source.replaceAll(`"${alias}"`, JSON.stringify(moduleUrl(stub)))
    const url = moduleUrl(source)
    cache.set(relative, url)
    return url
}
