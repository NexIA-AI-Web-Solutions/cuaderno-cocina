import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {compileScript, parse} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const helperUrl = name => moduleUrl(ts.transpileModule(readFileSync(new URL(name, import.meta.url), 'utf8'),
    {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText)
function renderer() {
    return Vue.createRenderer({createElement: type => ({type, props: {}, children: [], parent: null}),
        createText: text => ({type: '#text', text, children: [], parent: null}), createComment: text => ({type: '#comment', text, children: [], parent: null}),
        setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.children = [{type: '#text', text, children: [], parent: node}] },
        parentNode: node => node.parent, nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
        insert(node, parent, anchor = null) { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = parent; const index = anchor ? parent.children.indexOf(anchor) : -1; index < 0 ? parent.children.push(node) : parent.children.splice(index, 0, node) },
        remove(node) { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1) },
        patchProp: (node, key, _old, value) => { node.props[key] = value }, setScopeId: () => {}, insertStaticContent: () => assert.fail('No static HTML')})
}
function all(root, predicate) { const found = []; const visit = node => { if (predicate(node)) found.push(node); for (const child of node.children || []) visit(child) }; visit(root); return found }
const textOf = root => all(root, node => node.type === '#text').map(node => node.text).join(' ')
const button = (root, label) => all(root, node => node.type === 'button' && textOf(node).includes(label))[0]
const field = (root, label) => all(root, node => node.props?.label === label)[0]
async function flush() { for (let index = 0; index < 15; index += 1) await Vue.nextTick() }

test('Consulta preserves service refresh, print and lazy preparation while writes stay disabled', async () => {
    const calls = []
    let prints = 0
    globalThis.window = {print: () => { prints += 1 }}
    globalThis.__productionReadOnly = (url, options = {}) => {
        calls.push({url, options})
        if (url === '/api/cuaderno/edition/') return {ok: true, status: 200, data: {edition: 'profesional', operational_role: {
            code: 'guest', label: 'Consulta', space: 1, can_operate_cuaderno: false, can_manage_edition: false, native_permissions_preserved: true,
        }}}
        if (url === '/api/cuaderno/services/') return {ok: true, status: 200, data: [{
            id: 7, title: 'Servicio lectura', covers: '20', service_date: '2026-10-04', state: 'confirmed', snapshot: {needs: []},
        }]}
        return assert.fail(`Unexpected ${options.method || 'GET'} ${url}`)
    }
    const api = moduleUrl(`export const cuadernoFetch = (url, options = {}) => globalThis.__productionReadOnly(url, options); export const readJson = async value => value;`)
    const model = moduleUrl(`import {defineComponent,h} from ${JSON.stringify(import.meta.resolve('vue'))}; export default defineComponent({inheritAttrs:false,props:{modelValue:{default:null},label:String,disabled:Boolean},emits:['update:modelValue'],setup:(props,ctx)=>()=>h('model-select',{...ctx.attrs,...props,'onUpdate:modelValue':v=>ctx.emit('update:modelValue',v)})})`)
    const preparation = moduleUrl(`import {defineComponent,h} from ${JSON.stringify(import.meta.resolve('vue'))}; export default defineComponent({props:{serviceId:Number,serviceState:String,canOperate:Boolean},setup:props=>()=>h('service-preparation-panel',props)})`)
    const empty = moduleUrl('export default {render: () => null}')
    const filename = 'ProduccionPage.vue'
    const {descriptor, errors} = parse(readFileSync(new URL('./pages/ProduccionPage.vue', import.meta.url), 'utf8'), {filename})
    assert.deepEqual(errors, [])
    let code = compileScript(descriptor, {id: 'production-read-only', inlineTemplate: true, templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    code = ts.transpileModule(code, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText
    const replacements = new Map([
        ['vue', import.meta.resolve('vue')], ['@/cuaderno/api', api], ['@/components/inputs/VModelSelect.vue', model],
        ['@/cuaderno/components/ServicePreparationPanel.vue', preparation], ['@/cuaderno/components/AllergenAssessmentPanel.vue', empty],
        ['@/cuaderno/components/ProductionWastePanel.vue', empty], ['@/cuaderno/forms', helperUrl('./forms.ts')],
        ['@/cuaderno/inventoryRequests', helperUrl('./inventoryRequests.ts')], ['@/cuaderno/operationalRoleUi', helperUrl('./operationalRoleUi.ts')],
        ['@/cuaderno/navigationUi', helperUrl('./navigationUi.ts')], ['@/cuaderno/financeUi', helperUrl('./financeUi.ts')],
        ['@/cuaderno/allergenUi', helperUrl('./allergenUi.ts')], ['@/cuaderno/productionWasteUi', helperUrl('./productionWasteUi.ts')],
    ])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, _quote, name) => { assert.ok(replacements.has(name), `Unexpected ${name}`); return `from ${JSON.stringify(replacements.get(name))}` })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = renderer().createApp(component)
    for (const name of ['v-container', 'v-btn', 'v-alert', 'v-row', 'v-col', 'v-card', 'v-card-title', 'v-card-text', 'v-card-actions',
        'v-text-field', 'v-select', 'v-list', 'v-list-item', 'v-dialog']) {
        app.component(name, Vue.defineComponent({inheritAttrs: false, props: {modelValue: {default: null}, label: String, disabled: Boolean, loading: Boolean}, emits: ['update:modelValue'],
            setup(props, context) { return () => Vue.h(name === 'v-btn' ? 'button' : name, {...context.attrs, ...props, 'onUpdate:modelValue': value => context.emit('update:modelValue', value)}, [context.slots.default?.(), context.slots.append?.()]) }}))
    }
    app.mount(root); await flush()
    try {
        assert.equal(all(root, node => node.type === 'fieldset' && node.props.disabled).length, 0)
        assert.equal(button(root, 'Actualizar servicios').props.disabled, false)
        assert.equal(button(root, 'Imprimir fichas').props.disabled, false)
        await button(root, 'Actualizar servicios').props.onClick(); await flush()
        button(root, 'Imprimir fichas').props.onClick()
        assert.equal(calls.filter(call => call.url === '/api/cuaderno/services/' && !call.options.method).length, 2)
        assert.equal(prints, 1)
        const panel = all(root, node => node.type === 'service-preparation-panel')[0]
        assert.equal(panel.props.canOperate, false)
        for (const label of ['Recetas', 'Receta', 'Cantidad obtenida', 'Nombre', 'Componente y unidad', 'Alimento', 'Estado']) {
            assert.equal(field(root, label).props.disabled, true, label)
        }
        for (const label of ['Calcular necesidades', 'Guardar rendimiento', 'Anotar servicio', 'Añadir línea', 'Consolidar', 'Declarar', 'Producir', 'Cancelar servicio']) {
            assert.equal(button(root, label).props.disabled, true, label)
        }
        await button(root, 'Anotar servicio').props.onClick(); await flush()
        assert.equal(calls.some(call => call.options.method && call.options.method !== 'GET'), false)
    } finally { app.unmount(); delete globalThis.__productionReadOnly; delete globalThis.window }
})
