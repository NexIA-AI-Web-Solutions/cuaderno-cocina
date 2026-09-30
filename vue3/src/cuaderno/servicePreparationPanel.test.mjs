// Actual SFC/script/template mounted with Vue's virtual renderer. API and
// Vuetify widgets are unit-test boundaries; this is not a DOM/browser test.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse, compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const helper = moduleUrl(ts.transpileModule(
    readFileSync(new URL('./servicePreparationUi.ts', import.meta.url), 'utf8'),
    {compilerOptions: {module: ts.ModuleKind.ESNext}},
).outputText)

function virtualRenderer() {
    return Vue.createRenderer({
        createElement: type => ({type, props: {}, children: [], parent: null}),
        createText: text => ({type: '#text', text, children: [], parent: null}),
        createComment: text => ({type: '#comment', text, children: [], parent: null}),
        setText: (node, text) => { node.text = text },
        setElementText: (node, text) => { node.children = [{type: '#text', text, children: [], parent: node}] },
        parentNode: node => node.parent,
        nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
        insert(node, parent, anchor = null) {
            if (node.parent) {
                const old = node.parent.children.indexOf(node)
                if (old >= 0) node.parent.children.splice(old, 1)
            }
            node.parent = parent
            const index = anchor ? parent.children.indexOf(anchor) : -1
            if (index < 0) parent.children.push(node)
            else parent.children.splice(index, 0, node)
        },
        remove(node) {
            if (!node.parent) return
            const index = node.parent.children.indexOf(node)
            if (index >= 0) node.parent.children.splice(index, 1)
            node.parent = null
        },
        patchProp: (node, key, _previous, value) => { node.props[key] = value },
        setScopeId: () => {},
        insertStaticContent: () => assert.fail('Static HTML must remain disabled for this virtual renderer'),
    })
}

function all(root, predicate) {
    const found = []
    function visit(node) {
        if (predicate(node)) found.push(node)
        for (const child of node.children || []) visit(child)
    }
    visit(root)
    return found
}
const textOf = root => all(root, node => node.type === '#text').map(node => node.text).join(' ')
const button = (root, text) => all(root, node => node.type === 'button' && textOf(node).includes(text))[0]
const checkbox = root => all(root, node => node.type === 'checkbox')[0]
async function flush() { for (let index = 0; index < 8; index += 1) await Vue.nextTick() }

function payload(serviceId = 12, checked = false, revision = 'a'.repeat(64)) {
    return {
        service_id: serviceId, state: 'confirmed', can_edit: true, revision,
        items: [{
            id: serviceId * 10, source_step_id: 5, position: 0, recipe_id: 9,
            name: 'Preparar <arroz>', instruction: '{{ globalThis.prepExecuted = true }}\n<script>unsafe()</script>',
            checked, checked_at: checked ? '2026-09-30T10:15:30+02:00' : null,
            updated_by: checked ? 7 : null,
        }],
    }
}

let nextId = 0
async function mount(transport) {
    const id = ++nextId
    globalThis.__cuadernoPreparationUnit ??= new Map()
    const calls = []
    globalThis.__cuadernoPreparationUnit.set(id, async (url, options = {}) => {
        calls.push({url, options})
        return transport(url, options)
    })
    const api = moduleUrl(`
        export const cuadernoFetch = (url, options) => globalThis.__cuadernoPreparationUnit.get(${id})(url, options);
        export const readJson = async response => response;
    `)
    const errors = moduleUrl('export const apiError = status => `HTTP ${status}`;')
    const filename = 'ServicePreparationPanel.vue'
    const source = readFileSync(new URL('./components/ServicePreparationPanel.vue', import.meta.url), 'utf8')
    const {descriptor, errors: parseErrors} = parse(source, {filename})
    assert.deepEqual(parseErrors, [])
    const script = compileScript(descriptor, {
        id: `preparation-unit-${id}`, inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}},
    }).content
    let code = ts.transpileModule(script, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
    const replacements = new Map([
        ['vue', import.meta.resolve('vue')], ['@/cuaderno/api', api],
        ['@/cuaderno/forms', errors], ['@/cuaderno/servicePreparationUi', helper],
    ])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, quote, name) => {
        assert.ok(replacements.has(name), `Unexpected dependency ${name}`)
        return `from ${JSON.stringify(replacements.get(name))}`
    })
    const component = (await import(moduleUrl(code))).default
    const props = Vue.reactive({serviceId: 12, serviceState: 'confirmed'})
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = virtualRenderer().createApp({setup: () => () => Vue.h(component, props)})
    // Real panel logic/render; transparent widget stubs retain event handlers.
    for (const name of ['v-btn', 'v-alert', 'v-progress-linear', 'v-row', 'v-col', 'v-card', 'v-card-text', 'v-checkbox-btn']) {
        const type = name === 'v-btn' ? 'button' : name === 'v-checkbox-btn' ? 'checkbox' : name
        app.component(name, Vue.defineComponent({
            inheritAttrs: false,
            props: name === 'v-checkbox-btn' ? {modelValue: {default: undefined}} : {},
            setup(props, context) {
                return () => Vue.h(type, {...context.attrs, ...props}, [context.slots.default?.(), context.slots.append?.()])
            },
        }))
    }
    app.mount(root)
    await flush()
    return {root, props, calls, close() { app.unmount(); globalThis.__cuadernoPreparationUnit.delete(id) }}
}

test('lazy real panel blocks reload during PUT and edits during GET, then releases controls', async () => {
    let releasePut
    const mounted = await mount((_url, options) => options.method === 'PUT'
        ? new Promise(resolve => { releasePut = resolve })
        : {ok: true, status: 200, data: payload()})
    try {
        assert.equal(mounted.calls.length, 0)
        button(mounted.root, 'Ver preparación').props.onClick()
        await flush()
        assert.equal(mounted.calls.length, 1)
        assert.match(textOf(mounted.root), /<script>unsafe\(\)<\/script>/)
        assert.equal(all(mounted.root, node => node.type === 'script').length, 0)
        checkbox(mounted.root).props['onUpdate:modelValue'](true)
        await flush()
        assert.equal(mounted.calls.length, 2)
        assert.equal(checkbox(mounted.root).props.disabled, true)
        assert.equal(button(mounted.root, 'Recargar').props.disabled, true)
        button(mounted.root, 'Recargar').props.onClick()
        await flush()
        assert.equal(mounted.calls.length, 2, 'Guard must also prevent programmatic reload during PUT')
        releasePut({ok: true, status: 200, data: payload(12, true, 'b'.repeat(64))})
        await flush()
        assert.equal(checkbox(mounted.root).props.modelValue, true)
        assert.equal(checkbox(mounted.root).props.disabled, false)
        assert.match(textOf(mounted.root), /Cambio guardado/)
        const savedNotice = all(mounted.root, node => node.type === 'v-alert' && textOf(node).includes('Cambio guardado'))[0]
        assert.equal(savedNotice.props.type, 'success', 'Successful persistence must not be rendered as an error')
        assert.equal(savedNotice.props.role, 'status')
    } finally { mounted.close() }
})

test('409 preserves displayed state and blocks writes until explicit valid reload', async () => {
    let server = payload()
    const mounted = await mount((_url, options) => options.method === 'PUT'
        ? {ok: false, status: 409, data: {revision: 'conflict'}}
        : {ok: true, status: 200, data: server})
    try {
        button(mounted.root, 'Ver preparación').props.onClick()
        await flush()
        checkbox(mounted.root).props['onUpdate:modelValue'](true)
        await flush()
        assert.equal(checkbox(mounted.root).props.modelValue, false)
        assert.equal(checkbox(mounted.root).props.disabled, true)
        assert.match(textOf(mounted.root), /Otra persona cambió/)
        checkbox(mounted.root).props['onUpdate:modelValue'](true)
        await flush()
        assert.equal(mounted.calls.length, 2)
        server = payload(12, true, 'c'.repeat(64))
        button(mounted.root, 'Recargar').props.onClick()
        await flush()
        assert.equal(checkbox(mounted.root).props.modelValue, true)
        assert.equal(checkbox(mounted.root).props.disabled, false)
    } finally { mounted.close() }
})

test('late PUT from prior service cannot replace newly opened service context', async () => {
    let releasePut
    const mounted = await mount((url, options) => options.method === 'PUT'
        ? new Promise(resolve => { releasePut = resolve })
        : {ok: true, status: 200, data: payload(url.includes('/13/') ? 13 : 12)})
    try {
        button(mounted.root, 'Ver preparación').props.onClick()
        await flush()
        checkbox(mounted.root).props['onUpdate:modelValue'](true)
        await flush()
        mounted.props.serviceId = 13
        await flush()
        button(mounted.root, 'Ver preparación').props.onClick()
        await flush()
        releasePut({ok: true, status: 200, data: payload(12, true, 'b'.repeat(64))})
        await flush()
        assert.equal(checkbox(mounted.root).props.modelValue, false)
        assert.equal(checkbox(mounted.root).props.disabled, false)
        assert.equal(mounted.calls.at(-1).url, '/api/cuaderno/services/13/preparation/')
    } finally { mounted.close() }
})
