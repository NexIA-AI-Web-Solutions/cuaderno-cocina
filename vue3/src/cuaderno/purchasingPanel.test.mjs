import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse, compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const helperUrl = name => moduleUrl(ts.transpileModule(readFileSync(new URL(name, import.meta.url), 'utf8'),
    {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText)
function renderer() {
    return Vue.createRenderer({createElement: type => ({type, props: {}, children: [], parent: null}),
        createText: text => ({type: '#text', text, children: [], parent: null}), createComment: text => ({type: '#comment', text, children: [], parent: null}),
        setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.children = [{type: '#text', text, children: [], parent: node}] },
        parentNode: node => node.parent,
        nextSibling(node) {
            const index = node?.parent?.children.indexOf(node) ?? -1
            return index >= 0 ? node.parent.children[index + 1] ?? null : null
        },
        insert(node, parent, anchor = null) {
            if (node.parent) {
                const oldIndex = node.parent.children.indexOf(node)
                if (oldIndex >= 0) node.parent.children.splice(oldIndex, 1)
            }
            node.parent = parent
            const anchorIndex = anchor ? parent.children.indexOf(anchor) : -1
            if (anchorIndex >= 0) parent.children.splice(anchorIndex, 0, node)
            else parent.children.push(node)
        },
        remove(node) {
            if (!node?.parent) return
            const index = node.parent.children.indexOf(node)
            if (index >= 0) node.parent.children.splice(index, 1)
            node.parent = null
        },
        patchProp: (node, key, _old, value) => { node.props[key] = value }, setScopeId: () => {}, insertStaticContent: () => assert.fail('No static HTML')})
}
function all(root, predicate) { const found = []; const visit = node => { if (predicate(node)) found.push(node); for (const child of node.children || []) visit(child) }; visit(root); return found }
const textOf = root => all(root, node => node.type === '#text').map(node => node.text).join(' ')
const buttons = (root, label) => all(root, node => node.type === 'button' && textOf(node).includes(label))
const field = (root, label) => all(root, node => node.props?.label === label)[0]
async function flush() { for (let index = 0; index < 12; index += 1) await Vue.nextTick() }

const order = id => ({id, quantity: '10', received_quantity: '0', unit: 5, supplier_name: `Proveedor ${id}`,
    package: null, price_snapshot: null, currency_snapshot: 'EUR', state: 'ordered'})

test('pending receipt locks context controls and clears only its unchanged draft', async () => {
    let releaseReceipt
    const calls = []
    globalThis.__purchasePanelTransport = (url, options = {}) => {
        calls.push({url, options})
        if (url === '/api/cuaderno/packages/' || url === '/api/cuaderno/purchase-offers/') return {ok: true, status: 200, data: []}
        if (url === '/api/cuaderno/purchase-orders/' && !options.method) return {ok: true, status: 200, data: [order(10), order(11)]}
        if (url.includes('/receipts/') && options.method === 'POST') return new Promise(resolve => { releaseReceipt = resolve })
        if (url.includes('/receipts/')) return {ok: true, status: 200, data: []}
        return assert.fail(`Unexpected request ${url}`)
    }
    const api = moduleUrl(`export const cuadernoFetch = (url, options = {}) => globalThis.__purchasePanelTransport(url, options); export const readJson = async value => value;`)
    const forms = moduleUrl(`export const apiError = status => \`HTTP \${status}\`; export const decimalInput = value => /^\\d+(?:[.,]\\d+)?$/.test(String(value)) && /[1-9]/.test(String(value)) ? String(value).replace(',', '.') : null;`)
    const empty = moduleUrl('export default {render: () => null}')
    const modelSelect = moduleUrl(`import {defineComponent,h} from ${JSON.stringify(import.meta.resolve('vue'))}; export default defineComponent({inheritAttrs:false, props:{modelValue:{default:null},label:String,disabled:Boolean,searchOnLoad:Boolean}, emits:['update:modelValue'], setup:(props,ctx)=>()=>h('model-select',{...ctx.attrs,...props,'onUpdate:modelValue':v=>ctx.emit('update:modelValue',v)})})`)
    const filename = 'PurchasingPanel.vue'
    const {descriptor, errors} = parse(readFileSync(new URL('./components/PurchasingPanel.vue', import.meta.url), 'utf8'), {filename})
    assert.deepEqual(errors, [])
    let code = compileScript(descriptor, {id: 'purchase-panel', inlineTemplate: true, templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    code = ts.transpileModule(code, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText
    const replacements = new Map([['vue', import.meta.resolve('vue')], ['@/components/inputs/VModelSelect.vue', modelSelect],
        ['@/cuaderno/components/StockMinimumPanel.vue', empty], ['@/cuaderno/api', api], ['@/cuaderno/forms', forms],
        ['@/cuaderno/inventoryRequests', helperUrl('./inventoryRequests.ts')], ['@/cuaderno/stockMinimumUi', helperUrl('./stockMinimumUi.ts')],
        ['@/cuaderno/priceHistoryUi', helperUrl('./priceHistoryUi.ts')], ['@/cuaderno/purchasingUi', helperUrl('./purchasingUi.ts')]])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, _quote, name) => { assert.ok(replacements.has(name), `Unexpected ${name}`); return `from ${JSON.stringify(replacements.get(name))}` })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = renderer().createApp(component)
    for (const name of ['v-row', 'v-col', 'v-card', 'v-card-title', 'v-card-subtitle', 'v-card-text', 'v-select', 'v-text-field', 'v-checkbox',
        'v-btn', 'v-alert', 'v-spacer', 'v-list', 'v-list-item', 'v-list-item-title', 'v-list-item-subtitle', 'v-progress-linear', 'v-table']) {
        app.component(name, Vue.defineComponent({inheritAttrs: false, props: {modelValue: {default: null}, label: String, disabled: Boolean, loading: Boolean}, emits: ['update:modelValue'],
            setup(props, context) { return () => Vue.h(name === 'v-btn' ? 'button' : name, {...context.attrs, ...props, 'onUpdate:modelValue': value => context.emit('update:modelValue', value)}, [context.slots.default?.(), context.slots.append?.()]) }}))
    }
    app.mount(root); await flush()
    try {
        const suppliers = all(root, node => node.type === 'model-select' && node.props.label === 'Proveedor')
        assert.equal(suppliers.length, 2)
        for (const supplier of suppliers) assert.equal(supplier.props.searchOnLoad, true)
        buttons(root, 'Recibir')[0].props.onClick(); await flush()
        field(root, 'Existencia de destino').props['onUpdate:modelValue']({id: 17})
        field(root, 'Cantidad recibida (unidad 5)').props['onUpdate:modelValue']('2,5')
        const pending = buttons(root, 'Confirmar recepción')[0].props.onClick()
        for (let index = 0; index < 20 && !releaseReceipt; index += 1) await Vue.nextTick()
        await flush()
        assert.equal(buttons(root, 'Cerrar')[0].props.disabled, true)
        for (const receive of buttons(root, 'Recibir')) assert.equal(receive.props.disabled, true)
        assert.equal(field(root, 'Existencia de destino').props.disabled, true)
        releaseReceipt({ok: true, status: 201, data: {id: 20, quantity: '2.5', movement: 21, reversed_by: null}})
        await pending; await flush()
        assert.equal(field(root, 'Cantidad recibida (unidad 5)').props.modelValue, '')
        const post = calls.find(call => call.options.method === 'POST')
        assert.equal(JSON.parse(post.options.body).quantity, '2.5')
    } finally { app.unmount(); delete globalThis.__purchasePanelTransport }
})

test('Consulta keeps purchase history readable while every write control is disabled', async () => {
    const calls = []
    globalThis.__purchasePanelTransport = (url, options = {}) => {
        calls.push({url, options})
        if (url === '/api/cuaderno/packages/') return {ok: true, status: 200, data: []}
        if (url === '/api/cuaderno/purchase-offers/') return {ok: true, status: 200, data: []}
        if (url === '/api/cuaderno/purchase-orders/') return {ok: true, status: 200, data: [order(10)]}
        if (url === '/api/cuaderno/purchase-orders/10/receipts/') {
            return {ok: true, status: 200, data: [{id: 30, quantity: '2', movement: 31, reversed_by: null}]}
        }
        return assert.fail(`Unexpected request ${url}`)
    }
    const api = moduleUrl(`export const cuadernoFetch = (url, options = {}) => globalThis.__purchasePanelTransport(url, options); export const readJson = async value => value;`)
    const forms = moduleUrl(`export const apiError = status => \`HTTP \${status}\`; export const decimalInput = value => String(value);`)
    const stockMinimum = moduleUrl(`import {defineComponent,h} from ${JSON.stringify(import.meta.resolve('vue'))}; export default defineComponent({inheritAttrs:false,props:{canOperate:Boolean},setup:props=>()=>h('stock-minimum-panel',props)})`)
    const modelSelect = moduleUrl(`import {defineComponent,h} from ${JSON.stringify(import.meta.resolve('vue'))}; export default defineComponent({inheritAttrs:false, props:{modelValue:{default:null},label:String,disabled:Boolean,searchOnLoad:Boolean}, emits:['update:modelValue'], setup:(props,ctx)=>()=>h('model-select',{...ctx.attrs,...props,'onUpdate:modelValue':v=>ctx.emit('update:modelValue',v)})})`)
    const filename = 'PurchasingPanel.vue'
    const {descriptor, errors} = parse(readFileSync(new URL('./components/PurchasingPanel.vue', import.meta.url), 'utf8'), {filename})
    assert.deepEqual(errors, [])
    let code = compileScript(descriptor, {id: 'purchase-panel-consulta', inlineTemplate: true, templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    code = ts.transpileModule(code, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText
    const replacements = new Map([['vue', import.meta.resolve('vue')], ['@/components/inputs/VModelSelect.vue', modelSelect],
        ['@/cuaderno/components/StockMinimumPanel.vue', stockMinimum], ['@/cuaderno/api', api], ['@/cuaderno/forms', forms],
        ['@/cuaderno/inventoryRequests', helperUrl('./inventoryRequests.ts')], ['@/cuaderno/stockMinimumUi', helperUrl('./stockMinimumUi.ts')],
        ['@/cuaderno/priceHistoryUi', helperUrl('./priceHistoryUi.ts')], ['@/cuaderno/purchasingUi', helperUrl('./purchasingUi.ts')]])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, _quote, name) => { assert.ok(replacements.has(name), `Unexpected ${name}`); return `from ${JSON.stringify(replacements.get(name))}` })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = renderer().createApp(component, {canOperate: false})
    for (const name of ['v-row', 'v-col', 'v-card', 'v-card-title', 'v-card-subtitle', 'v-card-text', 'v-select', 'v-text-field', 'v-checkbox',
        'v-btn', 'v-alert', 'v-spacer', 'v-list', 'v-list-item', 'v-list-item-title', 'v-list-item-subtitle', 'v-progress-linear', 'v-table']) {
        app.component(name, Vue.defineComponent({inheritAttrs: false, props: {modelValue: {default: null}, label: String, disabled: Boolean, loading: Boolean}, emits: ['update:modelValue'],
            setup(props, context) { return () => Vue.h(name === 'v-btn' ? 'button' : name, {...context.attrs, ...props, 'onUpdate:modelValue': value => context.emit('update:modelValue', value)}, [context.slots.default?.(), context.slots.append?.()]) }}))
    }
    app.mount(root); await flush()
    try {
        assert.equal(all(root, node => node.props?.inert !== undefined).length, 0)
        const suppliers = all(root, node => node.type === 'model-select' && node.props.label === 'Proveedor')
        assert.equal(suppliers.length, 2)
        for (const supplier of suppliers) assert.equal(supplier.props.searchOnLoad, false)
        for (const label of ['Formato de compra', 'Proveedor', 'Precio por envase', 'Oferta expresamente gratuita', 'Formato', 'Oferta (opcional)', 'Número de envases']) {
            assert.equal(field(root, label).props.disabled, true, label)
        }
        for (const label of ['Guardar oferta', 'Crear borrador', 'Cancelar', 'Recibir', 'Calcular desde servicios confirmados']) {
            for (const control of buttons(root, label)) assert.equal(control.props.disabled, true, label)
        }
        assert.equal(all(root, node => node.type === 'stock-minimum-panel')[0].props.canOperate, false)
        assert.equal(buttons(root, 'Actualizar')[0].props.disabled, false)
        assert.equal(buttons(root, 'Recepciones')[0].props.disabled, false)
        await buttons(root, 'Recepciones')[0].props.onClick(); await flush()
        assert.ok(calls.some(call => call.url === '/api/cuaderno/purchase-orders/10/receipts/' && !call.options.method))
        assert.equal(buttons(root, 'Revertir recepción')[0].props.disabled, true)
        await buttons(root, 'Calcular desde servicios confirmados')[0].props.onClick(); await flush()
        assert.equal(calls.some(call => call.options.method === 'POST'), false)
    } finally { app.unmount(); delete globalThis.__purchasePanelTransport }
})
