// Actual ProduccionPage SFC mounted with Vue's virtual renderer. API, routing
// and Vuetify widgets are unit boundaries; this is not a DOM/browser test.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse, compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`

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
const wastePanel = root => all(root, node => node.type === 'production-waste-panel')[0]
async function flush() { for (let index = 0; index < 12; index += 1) await Vue.nextTick() }

function production({reversal = null, edition = 'integral', waste = undefined} = {}) {
    return {
        produced_at: '2026-10-25T12:00:00+02:00',
        edition,
        movement_ids: edition === 'integral' ? [31, 32] : [],
        stock_changed: edition === 'integral',
        ...(reversal ? {reversal} : {}),
        ...(waste === undefined ? {} : {waste_classification: waste}),
    }
}

function service({state = 'produced', reversal = null, edition = 'integral', waste = undefined} = {}) {
    return {
        id: 17,
        title: 'Banquete sintético',
        covers: '24',
        service_date: '2026-10-25',
        state,
        snapshot: {
            needs: [{food_id: 4, food_name: 'Aceite', quantity: '1.25', unit_name: 'L'}],
            production: production({reversal, edition, waste}),
        },
    }
}

function wasteClassification() {
    return {
        schema_version: 1,
        policy: 'declared_yield_estimate',
        classification_only: true,
        included_in_gross_needs: true,
        additional_stock_movement: false,
        coverage: 'declared_yields_only',
        status: 'declared',
        recorded_by: 5,
        recorded_at: '2026-10-25T12:00:00+02:00',
        lines: [{
            ingredient_id: 11, food_id: 4, food_name: 'Aceite', unit_id: 8, unit_name: 'L',
            quantity_basis: 'net_usable', yield_ratio: '0.8', purchased_quantity: '0.5',
            useful_quantity: '0.4', waste_quantity: '0.1', cause: 'declared_yield',
        }],
    }
}

let nextId = 0
async function mount(transport, initial = service()) {
    const id = ++nextId
    const calls = []
    globalThis.__cuadernoProductionReversalUnit ??= new Map()
    globalThis.__cuadernoProductionReversalUnit.set(id, {transport, calls})
    const api = moduleUrl(`
        export const cuadernoFetch = (url, options = {}) => {
            const state = globalThis.__cuadernoProductionReversalUnit.get(${id});
            state.calls.push({url, options});
            return state.transport(url, options);
        };
        export const readJson = async response => response;
    `)
    const forms = moduleUrl(`
        export const apiError = status => \`HTTP \${status}\`;
        export const productionUsage = () => null;
        export const productionWarning = value => String(value?.code || value || '');
        export const serviceBody = () => null;
        export const yieldBody = () => null;
        export const confirmedCostLabel = () => '—';
    `)
    const requests = moduleUrl(`
        export const inventoryRequests = () => ({
            key: (scope, payload) => \`\${scope}:\${JSON.stringify(payload)}\`,
        });
    `)
    const finance = moduleUrl(`
        export const financeMoneyLabel = value => value ?? '—';
        export const financeRatioLabel = value => value ?? '—';
        export const financeWarningLabel = value => String(value);
        export const pricePolicyLabel = value => value ?? 'sin elegir';
    `)
    const vueUrl = import.meta.resolve('vue')
    const emptyComponent = moduleUrl(`import {h} from ${JSON.stringify(vueUrl)}; export default {render: () => h('empty-component')};`)
    const allergens = moduleUrl(ts.transpileModule(
        readFileSync(new URL('./allergenUi.ts', import.meta.url), 'utf8'),
        {compilerOptions: {module: ts.ModuleKind.ESNext}},
    ).outputText)
    const wasteHelper = moduleUrl(ts.transpileModule(
        readFileSync(new URL('./productionWasteUi.ts', import.meta.url), 'utf8'),
        {compilerOptions: {module: ts.ModuleKind.ESNext}},
    ).outputText)
    const wasteComponent = moduleUrl(`
        import {defineComponent, h} from ${JSON.stringify(vueUrl)};
        export default defineComponent({
            props: {classification: {default: null}},
            setup: props => () => h('production-waste-panel', {classification: props.classification}),
        });
    `)
    const filename = 'ProduccionPage.vue'
    const source = readFileSync(new URL('./pages/ProduccionPage.vue', import.meta.url), 'utf8')
    const {descriptor, errors: parseErrors} = parse(source, {filename})
    assert.deepEqual(parseErrors, [])
    const script = compileScript(descriptor, {
        id: `production-reversal-unit-${id}`,
        inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}},
    }).content
    let code = ts.transpileModule(script, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
    const replacements = new Map([
        ['vue', vueUrl],
        ['@/cuaderno/api', api],
        ['@/components/inputs/VModelSelect.vue', emptyComponent],
        ['@/cuaderno/components/ServicePreparationPanel.vue', emptyComponent],
        ['@/cuaderno/components/AllergenAssessmentPanel.vue', emptyComponent],
        ['@/cuaderno/components/ProductionWastePanel.vue', wasteComponent],
        ['@/cuaderno/allergenUi', allergens],
        ['@/cuaderno/productionWasteUi', wasteHelper],
        ['@/cuaderno/forms', forms],
        ['@/cuaderno/inventoryRequests', requests],
        ['@/cuaderno/financeUi', finance],
    ])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, quote, name) => {
        assert.ok(replacements.has(name), `Unexpected dependency ${name}`)
        return `from ${JSON.stringify(replacements.get(name))}`
    })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = virtualRenderer().createApp(component)
    for (const name of [
        'v-container', 'v-btn', 'v-alert', 'v-row', 'v-col', 'v-card', 'v-card-title',
        'v-card-text', 'v-card-actions', 'v-list', 'v-list-item', 'v-dialog', 'v-select',
        'v-text-field', 'v-model-select', 'service-preparation-panel',
    ]) {
        const type = name === 'v-btn' ? 'button' : name
        app.component(name, Vue.defineComponent({
            inheritAttrs: false,
            props: {modelValue: {default: undefined}, disabled: Boolean, loading: Boolean},
            emits: ['update:modelValue'],
            setup(props, context) {
                return () => Vue.h(type, {
                    ...context.attrs,
                    ...props,
                    'onUpdate:modelValue': value => context.emit('update:modelValue', value),
                }, [context.slots.default?.(), context.slots.append?.()])
            },
        }))
    }
    app.mount(root)
    await flush()
    assert.equal(calls[0].url, '/api/cuaderno/services/')
    return {root, calls, close() { app.unmount(); globalThis.__cuadernoProductionReversalUnit.delete(id) }}
}

function listThen(initial, post) {
    return (url, options) => options.method === 'POST'
        ? post(url, options)
        : {ok: true, status: 200, data: [initial]}
}

async function openAndConfirm(mounted) {
    button(mounted.root, 'Revertir producción').props.onClick()
    await flush()
    return button(mounted.root, 'Confirmar reversión').props.onClick()
}

test('produced service requires explicit full-reversal confirmation and sends stable action payload', async () => {
    const initial = service()
    const reversed = service({state: 'cancelled', reversal: {
        reversed_at: '2026-10-25T13:00:00+02:00', reversed_by: 5,
        original_movement_ids: [31, 32], movement_ids: [41, 42], key_sha256: 'a'.repeat(64),
    }})
    const mounted = await mount(listThen(initial, () => ({
        ok: true, status: 200, data: {...reversed, reversal_movement_ids: [41, 42], stock_changed: true},
    })), initial)
    try {
        button(mounted.root, 'Revertir producción').props.onClick()
        await flush()
        const dialogText = textOf(mounted.root)
        assert.match(dialogText, /todas las asignaciones/iu)
        assert.match(dialogText, /necesidad bruta/iu)
        assert.match(dialogText, /movimientos originales.+historial/iu)
        assert.match(dialogText, /Profesional.+no.+stock/iu)
        const confirm = button(mounted.root, 'Confirmar reversión')
        assert.equal(String(confirm.props.minHeight ?? confirm.props['min-height']), '44')
        await confirm.props.onClick()
        await flush()
        const request = mounted.calls.at(-1)
        assert.equal(request.url, '/api/cuaderno/services/17/')
        assert.deepEqual(JSON.parse(request.options.body), {
            action: 'reverse',
            idempotency_key: 'reverse-service:{"plan":17}',
        })
        assert.match(textOf(mounted.root), /existencias restauradas/iu)
    } finally { mounted.close() }
})

test('409 keeps confirmation open and retry uses the same idempotency key', async () => {
    const initial = service()
    let attempts = 0
    const mounted = await mount(listThen(initial, () => {
        attempts += 1
        if (attempts === 1) return {ok: false, status: 409, data: {detail: 'conflict'}}
        return {
            ok: true, status: 200,
            data: {...service({state: 'cancelled', reversal: {
                reversed_at: '2026-10-25T13:00:00+02:00', reversed_by: 5,
                original_movement_ids: [31, 32], movement_ids: [41, 42], key_sha256: 'b'.repeat(64),
            }}), reversal_movement_ids: [41, 42], stock_changed: true},
        }
    }), initial)
    try {
        await openAndConfirm(mounted)
        await flush()
        assert.ok(button(mounted.root, 'Confirmar reversión'), '409 must retain the explicit confirmation')
        assert.match(textOf(mounted.root), /HTTP 409/)
        await button(mounted.root, 'Confirmar reversión').props.onClick()
        await flush()
        const bodies = mounted.calls.filter(call => call.options.method === 'POST').map(call => JSON.parse(call.options.body))
        assert.equal(bodies.length, 2)
        assert.equal(bodies[0].idempotency_key, bodies[1].idempotency_key)
        assert.equal(button(mounted.root, 'Confirmar reversión'), undefined)
    } finally { mounted.close() }
})

test('unexpected request exception releases busy state and retains confirmation for safe retry', async () => {
    const initial = service()
    const mounted = await mount(listThen(initial, () => Promise.reject(new Error('adapter failure'))), initial)
    try {
        await openAndConfirm(mounted)
        await flush()
        const retry = button(mounted.root, 'Confirmar reversión')
        assert.ok(retry)
        assert.equal(retry.props.loading, false)
        assert.equal(retry.props.disabled, false)
        assert.match(textOf(mounted.root), /No se pudo revertir la producción/)
    } finally { mounted.close() }
})

test('cancelled service renders frozen reversal audit, including professional no-stock completion', async () => {
    const reversed = service({state: 'cancelled', edition: 'profesional', reversal: {
        reversed_at: '2026-10-25T13:00:00+02:00', reversed_by: 5,
        original_movement_ids: [], movement_ids: [], key_sha256: 'c'.repeat(64),
    }})
    const mounted = await mount(listThen(reversed, () => assert.fail('No mutation expected')), reversed)
    try {
        const content = textOf(mounted.root)
        assert.match(content, /Producción revertida/)
        assert.match(content, /Profesional.+sin movimientos de existencias/iu)
        assert.match(content, /historial original/iu)
        assert.equal(button(mounted.root, 'Revertir producción'), undefined)
    } finally { mounted.close() }
})

test('malformed 2xx reversal responses retain confirmation and retry the same key without applying state', async () => {
    const initial = service()
    const audit = {
        reversed_at: '2026-10-25T13:00:00+02:00', reversed_by: 5,
        original_movement_ids: [31, 32], movement_ids: [41, 42], key_sha256: 'd'.repeat(64),
    }
    const valid = {...service({state: 'cancelled', reversal: audit}), reversal_movement_ids: [41, 42], stock_changed: true}
    const malformed = [
        {...valid, id: 18},
        {...valid, state: 'produced'},
        {...valid, snapshot: {...valid.snapshot, production: {...valid.snapshot.production, reversal: undefined}}},
        {...valid, reversal_movement_ids: [41, 99]},
        {...valid, reversal_movement_ids: [41], snapshot: {...valid.snapshot, production: {
            ...valid.snapshot.production, reversal: {...audit, movement_ids: [41]},
        }}},
        {...valid, snapshot: {...valid.snapshot, production: {
            ...valid.snapshot.production,
            reversal: {...audit, original_movement_ids: [31, 99]},
        }}},
    ]
    for (const badResponse of malformed) {
        let attempts = 0
        const mounted = await mount(listThen(initial, () => {
            attempts += 1
            return {ok: true, status: 200, data: attempts === 1 ? badResponse : valid}
        }), initial)
        try {
            await openAndConfirm(mounted)
            await flush()
            assert.ok(button(mounted.root, 'Confirmar reversión'), 'Ambiguous 2xx must retain confirmation')
            assert.ok(button(mounted.root, 'Revertir producción'), 'Ambiguous 2xx must not apply cancelled state')
            assert.match(textOf(mounted.root), /respuesta.+incompleta o incoherente/iu)
            await button(mounted.root, 'Confirmar reversión').props.onClick()
            await flush()
            const bodies = mounted.calls.filter(call => call.options.method === 'POST').map(call => JSON.parse(call.options.body))
            assert.equal(bodies.length, 2)
            assert.equal(bodies[0].idempotency_key, bodies[1].idempotency_key)
            assert.equal(button(mounted.root, 'Confirmar reversión'), undefined)
        } finally { mounted.close() }
    }
})

test('successful reversal applies only state and audit, never overwriting frozen service fields', async () => {
    const initial = service()
    const audit = {
        reversed_at: '2026-10-25T13:00:00+02:00', reversed_by: 5,
        original_movement_ids: [31, 32], movement_ids: [41, 42], key_sha256: 'e'.repeat(64),
    }
    const response = {
        ...service({state: 'cancelled', reversal: audit}), title: 'Wrong title', covers: '999',
        service_date: '2099-12-31', reversal_movement_ids: [41, 42], stock_changed: true,
    }
    response.snapshot.needs = [{food_id: 99, food_name: 'Wrong food', quantity: '999', unit_name: 'kg'}]
    const mounted = await mount(listThen(initial, () => ({ok: true, status: 200, data: response})), initial)
    try {
        await openAndConfirm(mounted)
        await flush()
        assert.match(textOf(mounted.root), /Banquete sintético/)
        assert.match(textOf(mounted.root), /24 comensales/)
        assert.match(textOf(mounted.root), /2026-10-25/)
        assert.doesNotMatch(textOf(mounted.root), /Wrong title|999 comensales|2099-12-31/)
        const needs = all(mounted.root, node => node.type === 'v-list-item' && node.props.title === 'Aceite')
        assert.equal(needs.length, 1)
        assert.equal(needs[0].props.subtitle, '1.25 L')
        assert.match(textOf(mounted.root), /Producción revertida/)
        assert.equal(button(mounted.root, 'Confirmar reversión'), undefined)
    } finally { mounted.close() }
})

test('the frozen declared-loss classification remains attached after complete reversal', async () => {
    const waste = wasteClassification()
    const initial = service({waste})
    const audit = {
        reversed_at: '2026-10-25T13:00:00+02:00', reversed_by: 5,
        original_movement_ids: [31, 32], movement_ids: [41, 42], key_sha256: 'f'.repeat(64),
    }
    const response = {
        ...service({state: 'cancelled', reversal: audit, waste}),
        reversal_movement_ids: [41, 42], stock_changed: true,
    }
    const mounted = await mount(listThen(initial, () => ({ok: true, status: 200, data: response})), initial)
    try {
        assert.deepEqual(wastePanel(mounted.root).props.classification, waste)
        await openAndConfirm(mounted)
        await flush()
        assert.deepEqual(wastePanel(mounted.root).props.classification, waste)
    } finally { mounted.close() }
})

test('legacy or malformed classifications stay unknown and never trigger a live request', async () => {
    for (const initial of [service(), service({waste: {...wasteClassification(), recorded_by: true}})]) {
        const mounted = await mount(listThen(initial, () => assert.fail('No write expected')), initial)
        try {
            assert.equal(wastePanel(mounted.root).props.classification, null)
            assert.deepEqual(mounted.calls.map(call => call.url), ['/api/cuaderno/services/'])
        } finally { mounted.close() }
    }
})
