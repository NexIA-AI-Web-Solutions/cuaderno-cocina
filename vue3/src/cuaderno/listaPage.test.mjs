import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse, compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
function renderer() {
    return Vue.createRenderer({
        createElement: type => ({type, props: {}, children: [], parent: null}),
        createText: text => ({type: '#text', text, children: [], parent: null}),
        createComment: text => ({type: '#comment', text, children: [], parent: null}),
        setText: (node, text) => { node.text = text },
        setElementText: (node, text) => { node.children = [{type: '#text', text, children: [], parent: node}] },
        parentNode: node => node.parent, nextSibling: () => null,
        insert(node, parent) { node.parent = parent; parent.children.push(node) },
        remove(node) { if (node.parent) node.parent.children = node.parent.children.filter(child => child !== node) },
        patchProp: (node, key, _old, value) => { node.props[key] = value },
        setScopeId: () => {}, insertStaticContent: () => assert.fail('No static HTML'),
    })
}
function all(root, predicate) {
    const found = []
    const visit = node => { if (predicate(node)) found.push(node); for (const child of node.children || []) visit(child) }
    visit(root); return found
}
const textOf = root => all(root, node => node.type === '#text').map(node => node.text).join(' ')
const button = (root, label) => all(root, node => node.type === 'button' && textOf(node).includes(label))[0]
const checkbox = root => all(root, node => node.type === 'checkbox')[0]
async function flush() { for (let index = 0; index < 12; index += 1) await Vue.nextTick() }

const initialRevision = '2026-10-04T10:00:00.123456+02:00'
const entry = (checked = false, updated_at = initialRevision) => ({
    id: 3, amount: '1.5', checked, updated_at, food: {id: 8, name: 'Arroz'},
    unit: {id: 5, name: 'kg'}, shopping_lists: [{id: 2}], list_recipe_data: {recipe: {name: 'Paella'}},
})

let nextId = 0
async function mount(transport, role = 'user') {
    const id = ++nextId
    const calls = []
    globalThis.__cuadernoListaUnit ??= new Map()
    globalThis.__cuadernoListaUnit.set(id, {transport, calls})
    const api = moduleUrl(`
        export const cuadernoFetch = async (url, options = {}) => {
            const state = globalThis.__cuadernoListaUnit.get(${id}); state.calls.push({url, options});
            if (url === '/api/cuaderno/edition/') return {ok: true, status: 200, data: {operational_role: {
                code: ${JSON.stringify(role)}, label: ${JSON.stringify(role === 'guest' ? 'Consulta' : 'Cocina')},
                can_manage_edition: false, can_operate_cuaderno: ${role !== 'guest'},
                space: 1, native_permissions_preserved: true,
            }}};
            return state.transport(url, options);
        };
        export const readJson = async response => response;
    `)
    const forms = moduleUrl(`
        export const apiError = status => status === 409 ? 'Conflicto; actualiza antes de reintentar.' : \`HTTP \${status}\`;
        export const decimalInput = value => String(value || '') || null;
        export const shoppingCheckBody = checked => ({checked});
    `)
    const shopping = moduleUrl(ts.transpileModule(readFileSync(new URL('./shoppingUi.ts', import.meta.url), 'utf8'),
        {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText)
    const roles = moduleUrl(ts.transpileModule(readFileSync(new URL('./operationalRoleUi.ts', import.meta.url), 'utf8'),
        {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText)
    const filename = 'ListaPage.vue'
    const {descriptor, errors} = parse(readFileSync(new URL('./pages/ListaPage.vue', import.meta.url), 'utf8'), {filename})
    assert.deepEqual(errors, [])
    let code = compileScript(descriptor, {id: `lista-${id}`, inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    code = ts.transpileModule(code, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
    const replacements = new Map([['vue', import.meta.resolve('vue')], ['@/cuaderno/api', api],
        ['@/cuaderno/forms', forms], ['@/cuaderno/shoppingUi', shopping], ['@/cuaderno/operationalRoleUi', roles]])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, _quote, name) => {
        assert.ok(replacements.has(name), `Unexpected dependency ${name}`)
        return `from ${JSON.stringify(replacements.get(name))}`
    })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = renderer().createApp(component)
    for (const name of ['v-container', 'v-btn', 'v-row', 'v-col', 'v-text-field', 'v-select',
        'v-progress-linear', 'v-list', 'v-list-subheader', 'v-list-item', 'v-list-item-title',
        'v-list-item-subtitle', 'v-checkbox-btn', 'v-alert']) {
        const type = name === 'v-btn' ? 'button' : name === 'v-checkbox-btn' ? 'checkbox' : name
        app.component(name, Vue.defineComponent({inheritAttrs: false,
            props: {modelValue: {default: undefined}, disabled: Boolean, loading: Boolean},
            emits: ['update:modelValue'],
            setup(props, context) { return () => Vue.h(type, {...context.attrs, ...props,
                'onUpdate:modelValue': value => context.emit('update:modelValue', value)},
            [context.slots.default?.(), context.slots.prepend?.()]) }}))
    }
    app.mount(root); await flush()
    return {root, calls, close() { app.unmount(); globalThis.__cuadernoListaUnit.delete(id) }}
}

test('toggle and undo send the exact successive revisions through If-Match', async () => {
    let current = entry()
    const mounted = await mount((url, options) => {
        if (url === '/api/shopping-list/') return {ok: true, status: 200, data: [{id: 2, name: 'Compra'}]}
        if (url.startsWith('/api/shopping-list-entry/?')) return {ok: true, status: 200, data: [current]}
        if (options.method === 'PATCH') {
            const checked = JSON.parse(options.body).checked
            current = entry(checked, checked ? '2026-10-04T10:01:00.000001+02:00' : '2026-10-04T10:02:00.000001+02:00')
            return {ok: true, status: 200, data: current}
        }
        return assert.fail(`Unexpected request ${url}`)
    })
    try {
        assert.match(textOf(mounted.root), /1.5 kg.+Arroz/)
        assert.match(textOf(mounted.root), /Receta: Paella/)
        await checkbox(mounted.root).props['onUpdate:modelValue'](true); await flush()
        const firstPatch = mounted.calls.find(call => call.options.method === 'PATCH')
        assert.equal(new Headers(firstPatch.options.headers).get('If-Match'), `"${initialRevision}"`)
        await button(mounted.root, 'Deshacer').props.onClick(); await flush()
        const patches = mounted.calls.filter(call => call.options.method === 'PATCH')
        assert.equal(new Headers(patches[1].options.headers).get('If-Match'), '"2026-10-04T10:01:00.000001+02:00"')
    } finally { mounted.close() }
})

test('409 preserves the conflict message and refreshes without a blind retry', async () => {
    let reads = 0
    const mounted = await mount((url, options) => {
        if (url === '/api/shopping-list/') return {ok: true, status: 200, data: [{id: 2, name: 'Compra'}]}
        if (url.startsWith('/api/shopping-list-entry/?')) { reads += 1; return {ok: true, status: 200, data: [entry(true, '2026-10-04T11:00:00+02:00')]} }
        if (options.method === 'PATCH') return {ok: false, status: 409, data: {detail: 'stale', updated_at: '2026-10-04T11:00:00+02:00', checked: true}}
        return assert.fail(`Unexpected request ${url}`)
    })
    try {
        await checkbox(mounted.root).props['onUpdate:modelValue'](false); await flush()
        assert.equal(mounted.calls.filter(call => call.options.method === 'PATCH').length, 1)
        assert.equal(reads, 2)
        assert.match(textOf(mounted.root), /Conflicto; actualiza/)
    } finally { mounted.close() }
})

test('Consulta can read the quick list but cannot create, add or toggle', async () => {
    const mounted = await mount((url) => {
        if (url === '/api/shopping-list/') return {ok: true, status: 200, data: [{id: 2, name: 'Compra'}]}
        if (url.startsWith('/api/shopping-list-entry/?')) return {ok: true, status: 200, data: [entry()]}
        return assert.fail(`Consulta must not write ${url}`)
    }, 'guest')
    try {
        assert.match(textOf(mounted.root), /Modo Consulta/)
        assert.equal(button(mounted.root, 'Crear').props.disabled, true)
        assert.equal(button(mounted.root, 'Añadir').props.disabled, true)
        assert.equal(checkbox(mounted.root).props.disabled, true)
        await button(mounted.root, 'Crear').props.onClick?.()
        await checkbox(mounted.root).props['onUpdate:modelValue'](true)
        await flush()
        assert.equal(mounted.calls.some(call => ['POST', 'PATCH'].includes(call.options.method)), false)
    } finally { mounted.close() }
})
