// Real ExchangePanel SFC mounted with Vue's virtual renderer. Vuetify widgets
// and HTTP are unit boundaries; this is not a browser or persistence test.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse, compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const exchangeUi = moduleUrl(ts.transpileModule(
    readFileSync(new URL('./exchangeUi.ts', import.meta.url), 'utf8'),
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
const byType = (root, type) => all(root, node => node.type === type)
const button = (root, text) => all(root, node => node.type === 'button' && textOf(node).includes(text))[0]
async function flush() { for (let index = 0; index < 12; index += 1) await Vue.nextTick() }

function portableDocument({conversions = true} = {}) {
    const catalog = {
        foods: [{ref: 'food:4', id: 4, name: 'Aceite'}],
        units: [
            {ref: 'unit:7', id: 7, name: 'g', base_unit: 'g', plural_name: '', description: ''},
            {ref: 'unit:8', id: 8, name: 'mL', base_unit: 'ml', plural_name: '', description: ''},
        ],
        packages: [],
    }
    if (conversions) catalog.conversions = [{
        ref: 'conversion:21', id: 21, food_ref: 'food:4',
        base_unit_ref: 'unit:7', converted_unit_ref: 'unit:8',
        base_amount: '920.0000000000000000', converted_amount: '1000.0000000000000000',
    }]
    return {
        format: 'cuaderno-recipes-v2', source: 'synthetic', source_space: 3,
        recipes: [{external_id: 'recipe:1', name: 'Receta sintética', servings: '1', steps: []}],
        catalog,
        media: {included: false, method: 'native-tandoor-zip', url_downloads: false},
        warnings: [],
    }
}

function fileFor(payload) {
    const text = JSON.stringify(payload)
    return {name: 'portable.json', size: text.length, text: async () => text}
}

let nextId = 0
async function mount(transport) {
    const id = ++nextId
    const calls = []
    globalThis.__cuadernoExchangeUnit ??= new Map()
    globalThis.__cuadernoExchangeUnit.set(id, async (url, options = {}) => {
        calls.push({url, options})
        return transport(url, options)
    })
    const api = moduleUrl(`
        export const cuadernoFetch = (url, options) => globalThis.__cuadernoExchangeUnit.get(${id})(url, options);
        export const readJson = async response => response;
    `)
    const forms = moduleUrl('export const apiError = status => `HTTP ${status}`;')
    const vueUrl = import.meta.resolve('vue')
    const modelSelect = moduleUrl(`
        import {defineComponent, h} from ${JSON.stringify(vueUrl)};
        export default defineComponent({inheritAttrs: false, props: {modelValue: {default: null}, model: String},
            setup(props, context) { return () => h('model-select', {...context.attrs, ...props}, context.slots.default?.()) }});
    `)
    const filename = 'ExchangePanel.vue'
    const source = readFileSync(new URL('./components/ExchangePanel.vue', import.meta.url), 'utf8')
    const {descriptor, errors} = parse(source, {filename})
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, {
        id: `exchange-unit-${id}`, inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}},
    }).content
    let code = ts.transpileModule(script, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
    const replacements = new Map([
        ['vue', vueUrl], ['@/components/inputs/VModelSelect.vue', modelSelect],
        ['@/cuaderno/api', api], ['@/cuaderno/forms', forms], ['@/cuaderno/exchangeUi', exchangeUi],
    ])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, quote, name) => {
        assert.ok(replacements.has(name), `Unexpected dependency ${name}`)
        return `from ${JSON.stringify(replacements.get(name))}`
    })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = virtualRenderer().createApp(component)
    const renderErrors = []
    app.config.errorHandler = error => { renderErrors.push(error) }
    const widgets = new Map([
        ['v-btn', 'button'], ['v-file-input', 'file-input'], ['v-radio-group', 'radio-group'],
        ['v-select', 'select'], ['v-alert', 'alert'],
    ])
    for (const name of [
        'v-expansion-panels', 'v-expansion-panel', 'v-expansion-panel-title', 'v-expansion-panel-text',
        'v-icon', 'v-divider', 'v-radio', 'v-textarea', 'v-card', 'v-card-title', 'v-card-text',
        'v-list', 'v-list-item', ...widgets.keys(),
    ]) {
        const type = widgets.get(name) || name
        app.component(name, Vue.defineComponent({
            inheritAttrs: false,
            props: {modelValue: {default: undefined}},
            setup(props, context) {
                return () => Vue.h(type, {...context.attrs, ...props}, [context.slots.default?.()])
            },
        }))
    }
    app.mount(root)
    await flush()
    return {root, calls, renderErrors, close() { app.unmount(); globalThis.__cuadernoExchangeUnit.delete(id) }}
}

async function loadFile(mounted, payload) {
    byType(mounted.root, 'file-input')[0].props['onUpdate:modelValue'](fileFor(payload))
    await flush()
}

test('conversion reuse sends the native UnitConversion identity in preview mapping', async () => {
    const mounted = await mount((url) => url === '/api/cuaderno/packages/'
        ? {ok: true, status: 200, data: []}
        : {ok: true, status: 200, data: {count: 1, preview: [], writes: 0, preview_sha256: 'a'.repeat(64)}})
    try {
        await loadFile(mounted, portableDocument())
        const conversionGroup = byType(mounted.root, 'radio-group').at(-1)
        conversionGroup.props['onUpdate:modelValue']('reuse')
        await flush()
        const selector = byType(mounted.root, 'model-select').find(node => node.props.model === 'UnitConversion')
        assert.ok(selector, 'Conversion reuse must use Tandoor native UnitConversion selector')
        selector.props['onUpdate:modelValue']({id: 77})
        await flush()
        button(mounted.root, 'Previsualizar').props.onClick()
        await flush()
        const preview = mounted.calls.find(call => call.url.endsWith('?preview=1'))
        assert.ok(preview, `Preview request missing: ${textOf(mounted.root)}`)
        assert.deepEqual(JSON.parse(preview.options.body).mapping.conversions, {'conversion:21': 77})
    } finally { mounted.close() }
})

test('changing a conversion target invalidates an already successful preview', async () => {
    const mounted = await mount((url) => url === '/api/cuaderno/packages/'
        ? {ok: true, status: 200, data: []}
        : {ok: true, status: 200, data: {count: 1, preview: [], writes: 0, preview_sha256: 'b'.repeat(64)}})
    try {
        await loadFile(mounted, portableDocument())
        byType(mounted.root, 'radio-group').at(-1).props['onUpdate:modelValue']('reuse')
        await flush()
        const selector = byType(mounted.root, 'model-select').find(node => node.props.model === 'UnitConversion')
        selector.props['onUpdate:modelValue']({id: 77})
        await flush()
        button(mounted.root, 'Previsualizar').props.onClick()
        await flush()
        assert.ok(button(mounted.root, 'Confirmar importación'))
        selector.props['onUpdate:modelValue']({id: 78})
        await flush()
        assert.equal(button(mounted.root, 'Confirmar importación'), undefined)
    } finally { mounted.close() }
})

test('preview then confirm keeps exact conversion text, mapping and preview identity', async () => {
    const previewHash = 'c'.repeat(64)
    const payload = portableDocument()
    payload.catalog.conversions[0].base_amount = '9999999999999999.1234567890123456'
    payload.catalog.conversions[0].converted_amount = '0.0000000000000001'
    const mounted = await mount((url) => {
        if (url === '/api/cuaderno/packages/') return {ok: true, status: 200, data: []}
        if (url.endsWith('?preview=1')) {
            return {ok: true, status: 200, data: {count: 1, preview: [], writes: 0, preview_sha256: previewHash}}
        }
        return {ok: true, status: 201, data: {created: [91], replayed: [], rejected: []}}
    })
    try {
        await loadFile(mounted, payload)
        assert.match(
            textOf(mounted.root),
            /9999999999999999\.1234567890123456 g → 0\.0000000000000001 mL · Aceite/,
        )
        byType(mounted.root, 'radio-group').at(-1).props['onUpdate:modelValue']('reuse')
        await flush()
        const selector = byType(mounted.root, 'model-select').find(node => node.props.model === 'UnitConversion')
        selector.props['onUpdate:modelValue']({id: 77})
        await flush()
        button(mounted.root, 'Previsualizar').props.onClick()
        await flush()
        button(mounted.root, 'Confirmar importación').props.onClick()
        await flush()

        const confirmation = mounted.calls.find(call => call.url === '/api/cuaderno/exchange/')
        assert.ok(confirmation, 'A cloneable raw document must reach the confirmation POST')
        const body = JSON.parse(confirmation.options.body)
        assert.equal(body.preview_sha256, previewHash)
        assert.deepEqual(body.mapping.conversions, {'conversion:21': 77})
        assert.equal(
            body.catalog.conversions[0].base_amount,
            '9999999999999999.1234567890123456',
        )
        assert.equal(body.catalog.conversions[0].converted_amount, '0.0000000000000001')
    } finally { mounted.close() }
})

test('older v2 documents without conversions remain importable and request manual review', async () => {
    const mounted = await mount(() => ({ok: true, status: 200, data: []}))
    try {
        await loadFile(mounted, portableDocument({conversions: false}))
        assert.equal(byType(mounted.root, 'model-select').some(node => node.props.model === 'UnitConversion'), false)
        assert.match(textOf(mounted.root), /no contiene conversiones.+revis/iu)
        assert.doesNotMatch(textOf(mounted.root), /No se ha podido leer/)
        assert.ok(button(mounted.root, 'Previsualizar'))
    } finally { mounted.close() }
})

test('v2 documents may omit every optional catalog collection', async () => {
    const mounted = await mount(() => ({ok: true, status: 200, data: []}))
    try {
        const payload = portableDocument({conversions: false})
        payload.catalog = {}
        await loadFile(mounted, payload)
        assert.deepEqual(mounted.renderErrors, [])
        assert.ok(button(mounted.root, 'Previsualizar'))
        assert.doesNotMatch(textOf(mounted.root), /catálogo.+mal formado/iu)
    } finally { mounted.close() }
})

test('malformed conversion collections are rejected atomically before preview', async () => {
    for (const conversions of [[null], {ref: 'conversion:invalid'}]) {
        const mounted = await mount(() => ({ok: true, status: 200, data: []}))
        try {
            const payload = portableDocument()
            payload.catalog.conversions = conversions
            await loadFile(mounted, payload)
            assert.deepEqual(mounted.renderErrors, [], 'Malformed input must not reach Vue rendering')
            assert.match(textOf(mounted.root), /catálogo.+mal formado/iu)
            assert.equal(button(mounted.root, 'Previsualizar'), undefined)
            assert.equal(byType(mounted.root, 'model-select').some(node => node.props.model === 'UnitConversion'), false)
        } finally { mounted.close() }
    }
})
