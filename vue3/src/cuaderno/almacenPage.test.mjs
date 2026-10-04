// Actual AlmacenPage SFC mounted with Vue's virtual renderer. API, routing and
// Vuetify widgets are unit-test boundaries; this is not a DOM/browser test.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse, compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const stockHelper = moduleUrl(ts.transpileModule(
    readFileSync(new URL('./stockMovementUi.ts', import.meta.url), 'utf8'),
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
const field = (root, label) => all(root, node => node.props?.label === label)[0]
async function flush() { for (let index = 0; index < 8; index += 1) await Vue.nextTick() }

let nextId = 0
async function mount(transport, {edition = 'integral', role = 'user'} = {}) {
    const id = ++nextId
    const calls = []
    const completed = []
    const mountedBoundaries = []
    globalThis.__cuadernoAlmacenUnit ??= new Map()
    globalThis.__cuadernoAlmacenUnit.set(id, {transport, calls, completed, mountedBoundaries})
    const api = moduleUrl(`
        export const cuadernoFetch = (url, options = {}) => {
            const state = globalThis.__cuadernoAlmacenUnit.get(${id});
            state.calls.push({url, options});
            if (url === '/api/cuaderno/edition/') return {ok: true, status: 200, data: {edition: ${JSON.stringify(edition)}, operational_role: {code: ${JSON.stringify(role)}, label: ${JSON.stringify({guest: 'Consulta', user: 'Cocina', admin: 'Responsable'}[role])}, space: 1, can_operate_cuaderno: ${role !== 'guest'}, can_manage_edition: ${role === 'admin'}, native_permissions_preserved: true}}};
            return state.transport(url, options);
        };
        export const readJson = async response => response;
    `)
    const forms = moduleUrl(`
        export const apiError = status => \`HTTP \${status}\`;
        export const decimalInput = value => {
            if (typeof value !== 'string') return null;
            const normalized = value.trim().replace(',', '.');
            return /^(?:0*[1-9]\\d*)(?:\\.\\d+)?$/.test(normalized) ? normalized : null;
        };
    `)
    const requests = moduleUrl(`
        export const inventoryRequests = () => ({
            key: (_scope, payload) => \`key:\${JSON.stringify(payload)}\`,
            complete: (_scope, payload) => globalThis.__cuadernoAlmacenUnit.get(${id}).completed.push(payload),
        });
    `)
    const modelSelect = moduleUrl(`
        import {defineComponent, h} from ${JSON.stringify(import.meta.resolve('vue'))};
        export default defineComponent({
            inheritAttrs: false,
            props: {modelValue: {default: undefined}, label: {default: undefined}, disabled: Boolean},
            emits: ['update:modelValue'],
            setup: (props, context) => () => h('model-select', {
                ...context.attrs, ...props,
                'onUpdate:modelValue': value => context.emit('update:modelValue', value),
            }),
        });
    `)
    const purchasingPanel = moduleUrl(`
        export default {setup() {
            globalThis.__cuadernoAlmacenUnit.get(${id}).mountedBoundaries.push('purchasing-panel');
            return () => null;
        }};
    `)
    const filename = 'AlmacenPage.vue'
    const source = readFileSync(new URL('./pages/AlmacenPage.vue', import.meta.url), 'utf8')
    const {descriptor, errors: parseErrors} = parse(source, {filename})
    assert.deepEqual(parseErrors, [])
    const script = compileScript(descriptor, {
        id: `almacen-unit-${id}`, inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}},
    }).content
    let code = ts.transpileModule(script, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
    const replacements = new Map([
        ['vue', import.meta.resolve('vue')],
        ['@/components/inputs/VModelSelect.vue', modelSelect],
        ['@/cuaderno/components/PurchasingPanel.vue', purchasingPanel],
        ['@/cuaderno/api', api],
        ['@/cuaderno/forms', forms],
        ['@/cuaderno/inventoryRequests', requests],
        ['@/cuaderno/stockMovementUi', stockHelper],
        ['@/cuaderno/navigationUi', moduleUrl(ts.transpileModule(
            readFileSync(new URL('./navigationUi.ts', import.meta.url), 'utf8'),
            {compilerOptions: {module: ts.ModuleKind.ESNext}},
        ).outputText)],
        ['@/cuaderno/operationalRoleUi', moduleUrl(ts.transpileModule(
            readFileSync(new URL('./operationalRoleUi.ts', import.meta.url), 'utf8'),
            {compilerOptions: {module: ts.ModuleKind.ESNext}},
        ).outputText)],
    ])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, quote, name) => {
        assert.ok(replacements.has(name), `Unexpected dependency ${name}`)
        return `from ${JSON.stringify(replacements.get(name))}`
    })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = virtualRenderer().createApp(component)
    const widgets = [
        'v-container', 'v-btn', 'v-alert', 'v-row', 'v-col', 'v-card', 'v-card-title',
        'v-card-subtitle', 'v-card-text', 'v-model-select', 'v-select', 'v-text-field',
        'v-list', 'v-list-item', 'v-list-item-title', 'v-list-item-subtitle', 'v-dialog',
        'v-card-actions', 'purchasing-panel',
    ]
    for (const name of widgets) {
        const type = name === 'v-btn' ? 'button' : name
        app.component(name, Vue.defineComponent({
            inheritAttrs: false,
            props: {modelValue: {default: undefined}, label: {default: undefined}, disabled: Boolean, loading: Boolean},
            emits: ['update:modelValue'],
            setup(props, context) {
                return () => Vue.h(type, {...context.attrs, ...props, 'onUpdate:modelValue': value => context.emit('update:modelValue', value)}, [
                    context.slots.default?.(), context.slots.append?.(),
                ])
            },
        }))
    }
    app.mount(root)
    await flush()
    return {root, calls, completed, mountedBoundaries, close() { app.unmount(); globalThis.__cuadernoAlmacenUnit.delete(id) }}
}

async function enterWaste(root, {quantity = '1,50', cause = '  Rotura en cámara  '} = {}) {
    field(root, 'Existencia del inventario').props['onUpdate:modelValue']({id: 17})
    field(root, 'Tipo').props['onUpdate:modelValue']('waste')
    await flush()
    field(root, 'Cantidad').props['onUpdate:modelValue'](quantity)
    field(root, 'Motivo del desperdicio').props['onUpdate:modelValue'](cause)
}

async function confirmWaste(mounted) {
    button(mounted.root, 'Aplicar movimiento').props.onClick()
    await flush()
    return button(mounted.root, 'Confirmar').props.onClick()
}

test('direct navigation outside Integral explains the edition and mounts no warehouse boundary', async () => {
    for (const edition of ['esencial', 'profesional']) {
        const mounted = await mount(() => assert.fail('A protected warehouse request must not run.'), {edition})
        try {
            assert.deepEqual(mounted.calls.map(call => call.url), ['/api/cuaderno/edition/'])
            assert.match(textOf(mounted.root), /El almacén está disponible en la edición Integral/)
            assert.equal(field(mounted.root, 'Existencia del inventario'), undefined)
            assert.equal(button(mounted.root, 'Actualizar historial'), undefined)
            assert.deepEqual(mounted.mountedBoundaries, [])
        } finally { mounted.close() }
    }
})

test('Integral mounts warehouse boundaries and loads history after checking the edition', async () => {
    const mounted = await mount(() => ({ok: true, status: 200, data: []}))
    try {
        assert.deepEqual(mounted.calls.map(call => call.url), [
            '/api/cuaderno/edition/', '/api/cuaderno/movements/',
        ])
        assert.ok(field(mounted.root, 'Existencia del inventario'))
        assert.deepEqual(mounted.mountedBoundaries, ['purchasing-panel'])
    } finally { mounted.close() }
})

test('waste POST uses normalized cause and stable key; 409 preserves the complete draft', async () => {
    const mounted = await mount((url, options) => options.method === 'POST'
        ? {ok: false, status: 409, data: {detail: 'conflict'}}
        : {ok: true, status: 200, data: []})
    try {
        await enterWaste(mounted.root)
        await confirmWaste(mounted)
        await flush()
        const first = JSON.parse(mounted.calls.at(-1).options.body)
        assert.deepEqual(first, {
            entry: 17, kind: 'waste', quantity: '1.50', cause: 'Rotura en cámara',
            idempotency_key: 'key:{"entry":17,"kind":"waste","quantity":"1.50","cause":"Rotura en cámara"}',
        })
        assert.equal(field(mounted.root, 'Cantidad').props.modelValue, '1,50')
        assert.equal(field(mounted.root, 'Motivo del desperdicio').props.modelValue, '  Rotura en cámara  ')
        await confirmWaste(mounted)
        await flush()
        assert.equal(JSON.parse(mounted.calls.at(-1).options.body).idempotency_key, first.idempotency_key)
    } finally { mounted.close() }
})

test('movement controls stay disabled and a later draft is not cleared by the pending POST', async () => {
    let releasePost
    const mounted = await mount((_url, options) => options.method === 'POST'
        ? new Promise(resolve => { releasePost = resolve })
        : {ok: true, status: 200, data: []})
    try {
        await enterWaste(mounted.root)
        const pending = confirmWaste(mounted)
        for (let index = 0; index < 20 && !releasePost; index += 1) await Vue.nextTick()
        assert.equal(typeof releasePost, 'function', 'POST must be pending before checking locked controls')
        await flush()
        for (const label of ['Existencia del inventario', 'Tipo', 'Cantidad', 'Motivo del desperdicio']) {
            assert.equal(field(mounted.root, label).props.disabled, true, `${label} must be locked during POST`)
        }
        assert.equal(button(mounted.root, 'Aplicar movimiento').props.disabled, true)
        field(mounted.root, 'Cantidad').props['onUpdate:modelValue']('3')
        field(mounted.root, 'Motivo del desperdicio').props['onUpdate:modelValue']('Nuevo borrador')
        await flush()
        releasePost({ok: true, status: 200, data: {balance: '8.50'}})
        await pending
        await flush()
        assert.equal(field(mounted.root, 'Cantidad').props.modelValue, '3')
        assert.equal(field(mounted.root, 'Motivo del desperdicio').props.modelValue, 'Nuevo borrador')
        assert.equal(button(mounted.root, 'Aplicar movimiento').props.disabled, false)
    } finally { mounted.close() }
})

test('unexpected request-adapter exception releases moving state and preserves the draft', async () => {
    const mounted = await mount((_url, options) => options.method === 'POST'
        ? Promise.reject(new Error('adapter failure'))
        : {ok: true, status: 200, data: []})
    try {
        await enterWaste(mounted.root, {quantity: '2', cause: 'Caída accidental'})
        await confirmWaste(mounted)
        await flush()
        assert.equal(button(mounted.root, 'Aplicar movimiento').props.loading, false)
        assert.equal(button(mounted.root, 'Aplicar movimiento').props.disabled, false)
        assert.equal(field(mounted.root, 'Cantidad').props.modelValue, '2')
        assert.equal(field(mounted.root, 'Motivo del desperdicio').props.modelValue, 'Caída accidental')
        assert.match(textOf(mounted.root), /No se pudo registrar el movimiento/)
    } finally { mounted.close() }
})

test('history exposes author and date, marks unknown legacy values and directs complete service reversal', async () => {
    const createdAt = '2026-09-30T12:00:00+00:00'
    const rows = [
        {id: 71, kind: 'consume', quantity: '1', entry: 17, balance: '0', reverses: null,
            created_by: 23, created_at: createdAt, metadata_snapshot: {origin: {type: 'service_plan', id: 42}}},
        {id: 72, kind: 'receipt', quantity: '1', entry: 17, balance: '1', reverses: null,
            created_by: null, created_at: null, metadata_snapshot: {}},
    ]
    const mounted = await mount(() => ({ok: true, status: 200, data: rows}))
    try {
        const text = textOf(mounted.root)
        assert.match(text, /Autor #23/)
        assert.ok(text.includes(new Date(createdAt).toLocaleString('es-ES')))
        assert.match(text, /Autor desconocido/)
        assert.match(text, /Fecha desconocida/)
        assert.doesNotMatch(text, /aún no está disponible/)
        const link = button(mounted.root, 'Ver servicio en Producción')
        assert.ok(link, 'The complete reversal belongs to the service, not a partial movement action')
        assert.deepEqual(link.props.to, {name: 'CuadernoProduccionPage'})
        const consumed = all(mounted.root, node => node.type === 'v-list-item'
            && textOf(node).includes('Movimiento de producción'))[0]
        assert.ok(consumed)
        assert.equal(button(consumed, 'Revertir'), undefined)
    } finally { mounted.close() }
})
