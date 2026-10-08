// PreciosPage mounted with Vue's virtual renderer. Network and Vuetify are
// boundaries; this verifies request reuse and stale-response protection, not DOM layout.
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
    visit(root)
    return found
}
const textOf = root => all(root, node => node.type === '#text').map(node => node.text).join(' ')
const button = (root, label) => all(root, node => node.type === 'button' && textOf(node).includes(label))[0]
const roleNotice = root => all(root, node => node.type === 'operational-role-notice')[0]
async function flush() { for (let index = 0; index < 12; index += 1) await Vue.nextTick() }

const role = code => ({
    guest: {code, label: 'Consulta', space: 4, can_operate_cuaderno: false, can_manage_edition: false, native_permissions_preserved: true},
    user: {code, label: 'Cocina', space: 4, can_operate_cuaderno: true, can_manage_edition: false, native_permissions_preserved: true},
    admin: {code, label: 'Responsable', space: 4, can_operate_cuaderno: true, can_manage_edition: true, native_permissions_preserved: true},
}[code])

let nextId = 0
async function mount(transport) {
    const id = ++nextId
    const calls = []
    globalThis.__cuadernoRolePageUnit ??= new Map()
    globalThis.__cuadernoRolePageUnit.set(id, {transport, calls})
    const vueUrl = import.meta.resolve('vue')
    const api = moduleUrl(`
        export const cuadernoFetch = (url, options = {}) => {
            const state = globalThis.__cuadernoRolePageUnit.get(${id});
            state.calls.push({url, options});
            return Promise.resolve(state.transport(url, options));
        };
        export const readJson = async response => response;
    `)
    const forms = moduleUrl(`
        export const apiError = status => \`HTTP \${status}\`;
        export const decimalInput = value => String(value || '') || null;
    `)
    const empty = moduleUrl(`export default {render: () => null};`)
    const history = moduleUrl(`
        import {defineComponent, h} from ${JSON.stringify(vueUrl)};
        export default defineComponent({props: {packageId: Number},
            setup: props => () => h('price-history-panel', {packageId: props.packageId})});
    `)
    const notice = moduleUrl(`
        import {defineComponent, h} from ${JSON.stringify(vueUrl)};
        export default defineComponent({props: {role: {default: null}},
            setup: props => () => h('operational-role-notice', {role: props.role})});
    `)
    const priceHelper = moduleUrl(ts.transpileModule(
        readFileSync(new URL('./priceHistoryUi.ts', import.meta.url), 'utf8'),
        {compilerOptions: {module: ts.ModuleKind.ESNext}},
    ).outputText)
    const roleHelper = moduleUrl(ts.transpileModule(
        readFileSync(new URL('./operationalRoleUi.ts', import.meta.url), 'utf8'),
        {compilerOptions: {module: ts.ModuleKind.ESNext}},
    ).outputText)
    const filename = 'PreciosPage.vue'
    const unitSource = readFileSync(new URL('./pages/PreciosPage.vue', import.meta.url), 'utf8')
        .replace('</script>', '\ndefineExpose({save})\n</script>')
    const {descriptor, errors} = parse(unitSource, {filename})
    assert.deepEqual(errors, [])
    let code = compileScript(descriptor, {id: `role-page-${id}`, inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    code = ts.transpileModule(code, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
    const replacements = new Map([
        ['vue', vueUrl], ['@/cuaderno/api', api], ['@/cuaderno/forms', forms],
        ['@/components/inputs/VModelSelect.vue', empty],
        ['@/cuaderno/components/PriceHistoryPanel.vue', history],
        ['@/cuaderno/components/OperationalRoleNotice.vue', notice],
        ['@/cuaderno/priceHistoryUi', priceHelper], ['@/cuaderno/operationalRoleUi', roleHelper],
    ])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, _quote, name) => {
        assert.ok(replacements.has(name), `Unexpected dependency ${name}`)
        return `from ${JSON.stringify(replacements.get(name))}`
    })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = renderer().createApp(component)
    for (const name of ['v-container', 'v-card', 'v-card-title', 'v-card-text', 'v-row', 'v-col',
        'v-btn', 'v-alert', 'v-divider', 'v-progress-linear', 'v-list', 'v-list-item',
        'v-list-item-title', 'v-list-item-subtitle', 'v-text-field', 'v-checkbox', 'v-table']) {
        app.component(name, Vue.defineComponent({inheritAttrs: false,
            setup(_props, context) { return () => Vue.h(name === 'v-btn' ? 'button' : name,
                context.attrs, [context.slots.default?.(), context.slots.append?.()]) }}))
    }
    const instance = app.mount(root)
    await flush()
    return {root, calls, submit: () => instance.save(), close() { app.unmount(); globalThis.__cuadernoRolePageUnit.delete(id) }}
}

test('uses the existing edition request and ignores a late role from an aborted load', async () => {
    let editionCount = 0
    let releaseOld
    const mounted = await mount((url, options) => {
        if (url === '/api/cuaderno/packages/') return {ok: true, status: 200, data: []}
        if (url === '/api/cuaderno/edition/') {
            editionCount += 1
            if (editionCount === 1) return new Promise(resolve => { releaseOld = () => resolve({
                ok: true, status: 200, data: {currency: 'EUR', operational_role: role('admin')},
            }) })
            return {ok: true, status: 200, data: {currency: 'EUR', operational_role: role('user')}}
        }
        return assert.fail(`Unexpected request ${url} ${options.method || 'GET'}`)
    })
    try {
        const firstEdition = mounted.calls.find(call => call.url === '/api/cuaderno/edition/')
        await button(mounted.root, 'Actualizar lista').props.onClick()
        await flush()
        assert.deepEqual(roleNotice(mounted.root).props.role, role('user'))
        assert.equal(firstEdition.options.signal.aborted, true)
        releaseOld()
        await flush()
        assert.deepEqual(roleNotice(mounted.root).props.role, role('user'))
        assert.deepEqual(mounted.calls.map(call => call.url), [
            '/api/cuaderno/packages/', '/api/cuaderno/edition/',
            '/api/cuaderno/packages/', '/api/cuaderno/edition/',
        ])
    } finally { mounted.close() }
})

test('a contradictory role fails closed without hiding native price content', async () => {
    const mounted = await mount(url => url === '/api/cuaderno/packages/'
        ? {ok: true, status: 200, data: []}
        : {ok: true, status: 200, data: {currency: 'EUR', operational_role: {...role('guest'), can_operate_cuaderno: true}}})
    try {
        assert.equal(roleNotice(mounted.root).props.role, null)
        assert.match(textOf(mounted.root), /Formatos guardados/)
        assert.deepEqual(mounted.calls.map(call => call.url), ['/api/cuaderno/packages/', '/api/cuaderno/edition/'])
    } finally { mounted.close() }
})

test('Consulta and unverified roles show reads first and cannot submit price writes while Cocina can', async () => {
    for (const [operationalRole, expectedDisabled] of [[role('guest'), true], [role('user'), false], [null, true]]) {
        const mounted = await mount((url, options) => {
            if (options.method) return assert.fail('Role gating must stop unauthorized POSTs')
            if (url === '/api/cuaderno/packages/') return {ok: true, status: 200, data: []}
            return operationalRole
                ? {ok: true, status: 200, data: {currency: 'EUR', operational_role: operationalRole}}
                : {ok: false, status: 503, data: {detail: 'offline'}}
        })
        try {
            if (expectedDisabled) assert.equal(Boolean(button(mounted.root, 'Guardar formato')), false, 'read-only roles must not mount a creation form')
            else assert.equal(button(mounted.root, 'Guardar formato').props.disabled, false)
            if (expectedDisabled) {
                await mounted.submit()
                await flush()
                assert.equal(mounted.calls.filter(call => call.options.method === 'POST').length, 0)
            }
        } finally { mounted.close() }
    }
})

test('Consulta can select a saved package and read its history without exposing price mutation controls', async () => {
    const row = {id: 8, food: 2, food_name: 'Aceite', unit: 3, unit_name: 'L', label: 'Garrafa',
        quantity: '5', is_reference: true, current_price: null}
    const mounted = await mount((url, options) => {
        if (options.method) return assert.fail('Consulta must not submit a price write')
        if (url === '/api/cuaderno/packages/') return {ok: true, status: 200, data: [row]}
        return {ok: true, status: 200, data: {currency: 'EUR', operational_role: role('guest')}}
    })
    try {
        assert.equal(Boolean(button(mounted.root, 'Guardar formato')), false)
        assert.match(textOf(mounted.root), /Modo Consulta: puedes revisar formatos, precios e historial/)
        const consult = button(mounted.root, 'Consultar historial')
        assert.ok(consult, 'the read action must remain available to Consulta')
        assert.notEqual(consult.props.disabled, true)
        await consult.props.onClick()
        await flush()
        const history = all(mounted.root, node => node.type === 'price-history-panel')[0]
        assert.equal(history.props.packageId, 8)
        assert.equal(button(mounted.root, 'Actualizar precio'), undefined)
        assert.equal(mounted.calls.filter(call => call.options.method === 'POST').length, 0)
    } finally { mounted.close() }
})

test('saved packages render envelope price, unit price and effective date in responsive representations', async () => {
    const validFrom = '2026-10-04T10:00:00+02:00'
    const row = {id: 1, food: 2, food_name: 'Aceite', unit: 3, unit_name: 'L', label: 'Garrafa',
        quantity: '5.0000000000000000', is_reference: true, current_price: {id: 4, amount: '32.0000000000000000', explicit_free: false, valid_from: validFrom}}
    const mounted = await mount(url => url === '/api/cuaderno/packages/'
        ? {ok: true, status: 200, data: [row]}
        : {ok: true, status: 200, data: {currency: 'EUR', operational_role: role('user')}})
    try {
        const text = textOf(mounted.root)
        assert.match(text, /Aceite.+Garrafa/)
        assert.match(text, /32,00 EUR/)
        assert.match(text, /5 L/)
        assert.doesNotMatch(text, /5\.0000000000000000/)
        const representations = [all(mounted.root, node => node.type === 'v-table')[0],
            all(mounted.root, node => String(node.props?.class || '').includes('package-cards'))[0]]
        for (const representation of representations) {
            assert.match(textOf(representation), /5 L/)
            assert.match(textOf(representation), /32,00 EUR/)
        }
        assert.match(text, /6,4000 EUR\/L/)
        assert.ok(text.includes(new Intl.DateTimeFormat('es-ES', {dateStyle: 'medium'}).format(new Date(validFrom))))
        assert.equal(all(mounted.root, node => node.type === 'v-table').length, 1)
        assert.equal(all(mounted.root, node => String(node.props?.class || '').includes('package-cards')).length, 1)
    } finally { mounted.close() }
})

test('Cocina retains invalid and rejected price drafts while history remains selected', async () => {
    const row = {id: 8, food: 2, food_name: 'Aceite', unit: 3, unit_name: 'L', label: 'Garrafa',
        quantity: '5', is_reference: true, current_price: null}
    const mounted = await mount((url, options) => {
        if (options.method === 'POST') {
            assert.equal(url, '/api/cuaderno/packages/8/prices/')
            assert.deepEqual(JSON.parse(options.body), {amount: '40.00', explicit_free: false})
            return {ok: false, status: 503, data: {detail: 'offline'}}
        }
        if (url === '/api/cuaderno/packages/') return {ok: true, status: 200, data: [row]}
        return {ok: true, status: 200, data: {currency: 'EUR', operational_role: role('user')}}
    })
    const priceField = () => all(mounted.root, node => node.props?.label === 'Nuevo precio EUR')[0]
    try {
        await button(mounted.root, 'Gestionar precio').props.onClick(); await flush()
        priceField().props['onUpdate:modelValue']('abc'); await flush()
        await button(mounted.root, 'Actualizar precio').props.onClick(); await flush()
        assert.equal(priceField().props.modelValue, 'abc')
        assert.match(textOf(mounted.root), /Introduce un decimal positivo/)
        assert.equal(mounted.calls.filter(call => call.options.method === 'POST').length, 0)
        priceField().props['onUpdate:modelValue']('40,00'); await flush()
        await button(mounted.root, 'Actualizar precio').props.onClick(); await flush()
        assert.equal(priceField().props.modelValue, '40,00')
        assert.match(textOf(mounted.root), /HTTP 503/)
        assert.equal(mounted.calls.filter(call => call.options.method === 'POST').length, 1)
        assert.equal(all(mounted.root, node => node.type === 'price-history-panel')[0].props.packageId, 8)
    } finally {mounted.close()}
})
