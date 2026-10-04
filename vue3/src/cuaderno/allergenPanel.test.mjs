// Actual ProduccionPage SFC mounted with Vue's virtual renderer. API, routing,
// Vuetify and the assessment renderer are unit boundaries; this is not a DOM test.
import test from 'node:test'
import assert from 'node:assert/strict'
import {existsSync, readFileSync} from 'node:fs'
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
const field = (root, label) => all(root, node => node.props?.label === label)[0]
const lastField = (root, label) => all(root, node => node.props?.label === label).at(-1)
const button = (root, label) => all(root, node => node.type === 'button' && textOf(node).includes(label))[0]
const panels = (root, source) => all(root, node => node.type === 'allergen-assessment-panel'
    && (!source || node.props.source === source))
async function flush() { for (let index = 0; index < 14; index += 1) await Vue.nextTick() }

function assessment(type, id, name, state = 'unknown') {
    const declared = state === 'declared'
    return {
        scope: {type, id, name},
        assessment: state,
        undeclared_means_absent: false,
        unknown_ingredients: false,
        foods: [{
            id: type === 'food' ? id : id + 100,
            name: type === 'food' ? name : 'Ingrediente de receta',
            declarations: declared ? [{id: id + 200, name: 'Gluten', state: 'declared'}] : [],
        }],
    }
}

function service(id, allergens = undefined) {
    return {
        id,
        title: `Servicio ${id}`,
        covers: '4',
        service_date: '2026-10-25',
        state: 'confirmed',
        snapshot: {needs: [], ...(allergens === undefined ? {} : {allergens})},
    }
}

let nextId = 0
async function mount(transport, serviceRows = [], edition = 'integral', operationalRole = {
    code: 'user', label: 'Cocina', space: 1, can_operate_cuaderno: true,
    can_manage_edition: false, native_permissions_preserved: true,
}) {
    const id = ++nextId
    const calls = []
    globalThis.__cuadernoAllergenPanelUnit ??= new Map()
    globalThis.__cuadernoAllergenPanelUnit.set(id, {transport, calls})
    const vueUrl = import.meta.resolve('vue')
    const api = moduleUrl(`
        export const cuadernoFetch = (url, options = {}) => {
            const state = globalThis.__cuadernoAllergenPanelUnit.get(${id});
            state.calls.push({url, options});
            if (url === '/api/cuaderno/edition/') return Promise.resolve({ok: true, status: 200, data: {
                edition: ${JSON.stringify(edition)}, operational_role: ${JSON.stringify(operationalRole)},
            }});
            return state.transport(url, options);
        };
        export const readJson = async response => response;
    `)
    const forms = moduleUrl(`
        export const apiError = status => \`HTTP \${status}\`;
        export const productionUsage = () => null;
        export const productionWarning = value => String(value?.code || value || '');
        export const serviceCovers = (base, extra, cancelled) => {
            if (!/^\\d+$/.test(base) || !/^\\d+$/.test(extra) || !/^\\d+$/.test(cancelled)) return null;
            if (BigInt(base) + BigInt(extra) - BigInt(cancelled) < 1n) return null;
            return {base_covers: base, extra, cancelled};
        };
        export const serviceBody = (title, covers, date, recipe) => title && /^\\d+$/.test(covers) && /^\\d{4}-\\d{2}-\\d{2}$/.test(date)
            ? {title, covers, service_date: date, ...(recipe ? {recipe} : {})}
            : null;
        export const yieldBody = () => null;
        export const confirmedCostLabel = () => '—';
    `)
    const requests = moduleUrl(`
        export const inventoryRequests = () => ({key: (scope, payload) => scope + ':' + JSON.stringify(payload)});
    `)
    const finance = moduleUrl(`
        export const financeMoneyLabel = value => value ?? '—';
        export const financeRatioLabel = value => value ?? '—';
        export const financeWarningLabel = value => String(value);
        export const pricePolicyLabel = value => value ?? 'sin elegir';
    `)
    const modelSelect = moduleUrl(`
        import {defineComponent, h} from ${JSON.stringify(vueUrl)};
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
    const panel = moduleUrl(`
        import {defineComponent, h} from ${JSON.stringify(vueUrl)};
        export default defineComponent({
            inheritAttrs: false,
            props: {
                assessment: {default: null}, source: String, title: String,
                loading: Boolean, error: {default: ''}, legacy: Boolean,
            },
            setup: (props, context) => () => h('allergen-assessment-panel', {...context.attrs, ...props}),
        });
    `)
    const helperPath = new URL('./allergenUi.ts', import.meta.url)
    const helper = existsSync(helperPath)
        ? moduleUrl(ts.transpileModule(readFileSync(helperPath, 'utf8'), {
            compilerOptions: {module: ts.ModuleKind.ESNext},
        }).outputText)
        : moduleUrl(`
            export const allergenAssessmentEnvelope = value => value;
            export const unknownAllergenAssessment = () => ({assessment: 'unknown', undeclared_means_absent: false, unknown_ingredients: true, foods: []});
            export const ALLERGEN_SAFETY_NOTICE = 'Sin declaraciones registradas no significa que el alimento o la receta estén libres de alérgenos.';
        `)
    const emptyComponent = moduleUrl(`export default {render: () => null};`)
    const filename = 'ProduccionPage.vue'
    const source = readFileSync(new URL('./pages/ProduccionPage.vue', import.meta.url), 'utf8')
    const {descriptor, errors: parseErrors} = parse(source, {filename})
    assert.deepEqual(parseErrors, [])
    const script = compileScript(descriptor, {
        id: `allergen-panel-unit-${id}`,
        inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}},
    }).content
    let code = ts.transpileModule(script, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
    const replacements = new Map([
        ['vue', vueUrl],
        ['@/cuaderno/api', api],
        ['@/components/inputs/VModelSelect.vue', modelSelect],
        ['@/cuaderno/components/ServicePreparationPanel.vue', emptyComponent],
        ['@/cuaderno/components/AllergenAssessmentPanel.vue', panel],
        ['@/cuaderno/components/ProductionWastePanel.vue', emptyComponent],
        ['@/cuaderno/forms', forms],
        ['@/cuaderno/inventoryRequests', requests],
        ['@/cuaderno/financeUi', finance],
        ['@/cuaderno/allergenUi', helper],
        ['@/cuaderno/operationalRoleUi', moduleUrl(ts.transpileModule(
            readFileSync(new URL('./operationalRoleUi.ts', import.meta.url), 'utf8'),
            {compilerOptions: {module: ts.ModuleKind.ESNext}},
        ).outputText)],
        ['@/cuaderno/navigationUi', moduleUrl(ts.transpileModule(
            readFileSync(new URL('./navigationUi.ts', import.meta.url), 'utf8'),
            {compilerOptions: {module: ts.ModuleKind.ESNext}},
        ).outputText)],
        ['@/cuaderno/productionWasteUi', moduleUrl(ts.transpileModule(
            readFileSync(new URL('./productionWasteUi.ts', import.meta.url), 'utf8'),
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
    for (const name of [
        'v-container', 'v-btn', 'v-alert', 'v-row', 'v-col', 'v-card', 'v-card-title',
        'v-card-text', 'v-card-actions', 'v-list', 'v-list-item', 'v-dialog', 'v-select',
        'v-text-field', 'v-model-select', 'service-preparation-panel',
    ]) {
        const type = name === 'v-btn' ? 'button' : name
        app.component(name, Vue.defineComponent({
            inheritAttrs: false,
            props: {
                modelValue: {default: undefined}, label: {default: undefined},
                disabled: Boolean, loading: Boolean,
            },
            emits: ['update:modelValue'],
            setup(props, context) {
                return () => Vue.h(type, {
                    ...context.attrs, ...props,
                    'onUpdate:modelValue': value => context.emit('update:modelValue', value),
                }, [context.slots.default?.(), context.slots.append?.()])
            },
        }))
    }
    app.mount(root)
    await flush()
    if (edition !== 'esencial') assert.ok(calls.some(call => call.url === '/api/cuaderno/services/'))
    return {
        root, calls,
        close() { app.unmount(); globalThis.__cuadernoAllergenPanelUnit.delete(id) },
    }
}

test('Esencial never requests services or mounts the production operation tree for any role', async () => {
    const roles = [
        {code: 'guest', label: 'Consulta', can_operate_cuaderno: false, can_manage_edition: false},
        {code: 'user', label: 'Cocina', can_operate_cuaderno: true, can_manage_edition: false},
        {code: 'admin', label: 'Responsable', can_operate_cuaderno: true, can_manage_edition: true},
    ]
    for (const operationalRole of roles) {
        const mounted = await mount(
            url => assert.fail(`Esencial must not request ${url}`), [], 'esencial',
            {...operationalRole, space: 1, native_permissions_preserved: true},
        )
        try {
            assert.deepEqual(mounted.calls.map(call => call.url), ['/api/cuaderno/edition/'])
            assert.match(textOf(mounted.root), /La producción está disponible en las ediciones Profesional e Integral\./)
            assert.equal(all(mounted.root, node => node.type === 'model-select').length, 0)
            assert.equal(button(mounted.root, 'Actualizar servicios'), undefined)
            assert.equal(button(mounted.root, 'Anotar servicio'), undefined)
        } finally { mounted.close() }
    }
})

test('Profesional Consulta loads readable services and keeps the complete operation tree disabled', async () => {
    const mounted = await mount(
        url => url === '/api/cuaderno/services/'
            ? {ok: true, status: 200, data: []}
            : assert.fail(`Unexpected request ${url}`),
        [], 'profesional',
        {code: 'guest', label: 'Consulta', space: 1, can_operate_cuaderno: false,
            can_manage_edition: false, native_permissions_preserved: true},
    )
    try {
        assert.deepEqual(mounted.calls.map(call => call.url), [
            '/api/cuaderno/edition/', '/api/cuaderno/services/',
        ])
        const readonly = all(mounted.root, node => node.type === 'v-alert'
            && textOf(node).includes('Modo Consulta: las fichas están disponibles solo para lectura.'))[0]
        assert.equal(readonly.props.role, 'status')
        assert.equal(all(mounted.root, node => node.type === 'fieldset')[0].props.disabled, true)
        assert.ok(button(mounted.root, 'Actualizar servicios'))
    } finally { mounted.close() }
})

test('changing food aborts and clears the previous assessment; late data cannot cross selections', async () => {
    let releaseFirst
    const first = assessment('food', 11, 'Harina vieja', 'declared')
    const second = assessment('food', 12, 'Harina nueva', 'unknown')
    const mounted = await mount((url, options) => {
        if (url === '/api/cuaderno/services/') return {ok: true, status: 200, data: []}
        if (url === '/api/cuaderno/allergens/?food=11') {
            return new Promise(resolve => { releaseFirst = () => resolve({ok: true, status: 200, data: first}) })
        }
        if (url === '/api/cuaderno/allergens/?food=12') return {ok: true, status: 200, data: second}
        return assert.fail(`Unexpected request ${url} ${options.method || 'GET'}`)
    })
    try {
        const food = field(mounted.root, 'Alimento')
        food.props['onUpdate:modelValue']({id: 11, name: 'Harina vieja'})
        await flush()
        const firstCall = mounted.calls.find(call => call.url.endsWith('food=11'))
        assert.ok(firstCall)
        food.props['onUpdate:modelValue']({id: 12, name: 'Harina nueva'})
        assert.equal(panels(mounted.root, 'food').at(-1)?.props.assessment ?? null, null)
        await flush()
        assert.equal(panels(mounted.root, 'food').at(-1).props.assessment.scope.id, 12)
        assert.equal(firstCall.options.signal?.aborted, true)
        releaseFirst()
        await flush()
        assert.equal(panels(mounted.root, 'food').at(-1).props.assessment.scope.id, 12)
    } finally { mounted.close() }
})

test('successful declaration reloads selected food and service recipe without touching frozen cards', async () => {
    const counts = {food: 0, recipe: 0, post: 0}
    const mounted = await mount((url, options) => {
        if (url === '/api/cuaderno/services/') return {ok: true, status: 200, data: []}
        if (url === '/api/cuaderno/allergens/?food=7') {
            counts.food += 1
            return {ok: true, status: 200, data: assessment('food', 7, 'Harina')}
        }
        if (url === '/api/cuaderno/allergens/?recipe=21') {
            counts.recipe += 1
            return {ok: true, status: 200, data: assessment('recipe', 21, 'Sopa')}
        }
        if (url === '/api/cuaderno/allergens/' && options.method === 'POST') {
            counts.post += 1
            return {ok: true, status: 201, data: {id: 91, state: 'declared', undeclared_means_absent: false}}
        }
        return assert.fail(`Unexpected request ${url}`)
    })
    try {
        field(mounted.root, 'Alimento').props['onUpdate:modelValue']({id: 7, name: 'Harina'})
        field(mounted.root, 'Receta del servicio').props['onUpdate:modelValue']({id: 21, name: 'Sopa'})
        await flush()
        lastField(mounted.root, 'Nombre').props['onUpdate:modelValue']('Gluten')
        field(mounted.root, 'Estado').props['onUpdate:modelValue']('declared')
        await button(mounted.root, 'Declarar').props.onClick()
        await flush()
        assert.deepEqual(counts, {food: 2, recipe: 2, post: 1})
        assert.equal(panels(mounted.root, 'food').at(-1).props.assessment.scope.id, 7)
        assert.equal(panels(mounted.root, 'recipe').at(-1).props.assessment.scope.id, 21)
    } finally { mounted.close() }
})

test('malformed successful declaration response preserves the form and does not reload live assessments', async () => {
    let reads = 0
    const mounted = await mount((url, options) => {
        if (url === '/api/cuaderno/services/') return {ok: true, status: 200, data: []}
        if (url === '/api/cuaderno/allergens/?food=7') {
            reads += 1
            return {ok: true, status: 200, data: assessment('food', 7, 'Harina')}
        }
        if (url === '/api/cuaderno/allergens/' && options.method === 'POST') {
            return {ok: true, status: 201, data: {id: true, state: 'safe', undeclared_means_absent: true}}
        }
        return assert.fail(`Unexpected request ${url}`)
    })
    try {
        field(mounted.root, 'Alimento').props['onUpdate:modelValue']({id: 7, name: 'Harina'})
        await flush()
        const name = lastField(mounted.root, 'Nombre')
        name.props['onUpdate:modelValue']('Gluten')
        await button(mounted.root, 'Declarar').props.onClick()
        await flush()
        assert.equal(reads, 1)
        assert.equal(lastField(mounted.root, 'Nombre').props.modelValue, 'Gluten')
        assert.match(textOf(mounted.root), /respuesta.+incompleta o incoherente/iu)
    } finally { mounted.close() }
})

test('invalid controlled or unpaired-surrogate names never reach the declaration endpoint', async () => {
    let writes = 0
    const mounted = await mount((url, options) => {
        if (url === '/api/cuaderno/services/') return {ok: true, status: 200, data: []}
        if (url === '/api/cuaderno/allergens/?food=7') {
            return {ok: true, status: 200, data: assessment('food', 7, 'Harina')}
        }
        if (url === '/api/cuaderno/allergens/' && options.method === 'POST') {
            writes += 1
            return assert.fail('Invalid names must be rejected before POST')
        }
        return assert.fail(`Unexpected request ${url}`)
    })
    try {
        field(mounted.root, 'Alimento').props['onUpdate:modelValue']({id: 7, name: 'Harina'})
        await flush()
        for (const invalid of ['Gluten\u0000oculto', 'Soja\u0085', 'Huevo\ud800']) {
            lastField(mounted.root, 'Nombre').props['onUpdate:modelValue'](invalid)
            await button(mounted.root, 'Declarar').props.onClick()
            await flush()
            assert.equal(writes, 0)
            assert.equal(lastField(mounted.root, 'Nombre').props.modelValue, invalid)
            assert.match(textOf(mounted.root), /nombre.+válido|caracteres no permitidos/iu)
        }
    } finally { mounted.close() }
})

test('unsafe selected identifiers never trigger allergen reads or writes and report a local error', async () => {
    let allergenRequests = 0
    const mounted = await mount((url) => {
        if (url === '/api/cuaderno/services/') return {ok: true, status: 200, data: []}
        if (url.includes('/api/cuaderno/allergens/')) {
            allergenRequests += 1
            return {ok: false, status: 400, data: {detail: 'must not be requested'}}
        }
        return assert.fail(`Unexpected request ${url}`)
    })
    try {
        const unsafe = 9007199254740992
        field(mounted.root, 'Alimento').props['onUpdate:modelValue']({id: unsafe, name: 'Fuera de rango'})
        field(mounted.root, 'Receta del servicio').props['onUpdate:modelValue']({id: unsafe, name: 'Fuera de rango'})
        await flush()
        assert.equal(allergenRequests, 0)

        lastField(mounted.root, 'Nombre').props['onUpdate:modelValue']('Gluten')
        await button(mounted.root, 'Declarar').props.onClick()
        await flush()
        assert.equal(allergenRequests, 0)
        assert.match(textOf(mounted.root), /selecciona.+alimento.+válido|identificador.+válido/iu)
    } finally { mounted.close() }
})

test('service cards render only frozen assessments and legacy snapshots stay unknown without live fetches', async () => {
    const frozen = assessment('recipe', 31, 'Servicio congelado', 'declared')
    const mounted = await mount((url) => {
        if (url === '/api/cuaderno/services/') {
            return {ok: true, status: 200, data: [service(31, frozen), service(32)]}
        }
        return assert.fail(`Service cards must not refetch live allergens: ${url}`)
    }, [service(31, frozen), service(32)])
    try {
        const snapshotPanels = panels(mounted.root, 'snapshot')
        assert.equal(snapshotPanels.length, 2)
        assert.deepEqual(snapshotPanels[0].props.assessment, frozen)
        assert.equal(snapshotPanels[0].props.legacy, false)
        assert.equal(snapshotPanels[1].props.assessment, null)
        assert.equal(snapshotPanels[1].props.legacy, true)
        assert.equal(mounted.calls.filter(call => call.url.includes('/allergens/')).length, 0)

        const liveFormRow = all(mounted.root, node => node.type === 'v-row'
            && textOf(node).includes('Declarar'))[0]
        assert.match(String(liveFormRow.props.class || ''), /\bno-print\b/)
        for (const live of [...panels(mounted.root, 'food'), ...panels(mounted.root, 'recipe')]) {
            assert.match(String(live.props.class || ''), /\bno-print\b/)
        }
        for (const frozenPanel of snapshotPanels) {
            assert.doesNotMatch(String(frozenPanel.props.class || ''), /\bno-print\b/)
        }
        const printToolbar = all(mounted.root, node => node.type === 'div'
            && textOf(node).includes('Actualizar servicios')
            && textOf(node).includes('Imprimir fichas'))[0]
        assert.match(String(printToolbar.props.class || ''), /\bno-print\b/)
    } finally { mounted.close() }
})

test('service form shows the cover breakdown and submits the three native counters', async () => {
    let submitted
    const mounted = await mount((url, options) => {
        if (url === '/api/cuaderno/services/' && options.method === 'POST') {
            submitted = JSON.parse(options.body)
            return {ok: true, status: 201, data: {covers: '10', stock_changed: false, meal_plan: 'created'}}
        }
        if (url === '/api/cuaderno/services/') return {ok: true, status: 200, data: []}
        return assert.fail(`Unexpected request ${url}`)
    })
    try {
        field(mounted.root, 'Nombre').props['onUpdate:modelValue']('Cena')
        field(mounted.root, 'Fecha del servicio').props['onUpdate:modelValue']('2026-10-25')
        field(mounted.root, 'Comensales previstos').props['onUpdate:modelValue']('12')
        field(mounted.root, 'Altas').props['onUpdate:modelValue']('1')
        field(mounted.root, 'Cancelaciones').props['onUpdate:modelValue']('3')
        await flush()
        assert.match(textOf(mounted.root), /Total del servicio:\s*10 comensales/)
        await button(mounted.root, 'Anotar servicio').props.onClick()
        await flush()
        assert.deepEqual(submitted, {
            title: 'Cena', service_date: '2026-10-25',
            base_covers: '12', extra: '1', cancelled: '3',
        })
    } finally { mounted.close() }
})
