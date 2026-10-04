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
    return Vue.createRenderer({
        createElement: type => ({type, props: {}, children: [], parent: null}),
        createText: text => ({type: '#text', text, children: [], parent: null}),
        createComment: text => ({type: '#comment', text, children: [], parent: null}),
        setText: (node, text) => { node.text = text },
        setElementText: (node, text) => { node.children = [{type: '#text', text, children: [], parent: node}] },
        parentNode: node => node.parent,
        nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
        insert(node, parent, anchor = null) {
            if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
            node.parent = parent
            const index = anchor ? parent.children.indexOf(anchor) : -1
            if (index < 0) parent.children.push(node)
            else parent.children.splice(index, 0, node)
        },
        remove(node) {
            if (!node.parent) return
            node.parent.children.splice(node.parent.children.indexOf(node), 1)
            node.parent = null
        },
        patchProp: (node, key, _old, value) => { node.props[key] = value },
        setScopeId: () => {},
        insertStaticContent: () => assert.fail('No static HTML'),
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
const field = (root, label) => all(root, node => node.props?.label === label)[0]
async function flush() { for (let index = 0; index < 12; index += 1) await Vue.nextTick() }

test('Consulta can refresh minimums but cannot enter or submit changes', async () => {
    const calls = []
    const envelope = {edition: 'integral', household: {id: 1, name: 'Cocina'}, locations: [], items: [{
        id: 4, household: 1, food: 2, food_name: 'Aceite', unit: 3, unit_name: 'L', location: null,
        location_name: null, quantity: '2', updated_by: 6, updated_at: '2026-10-04T00:00:00Z',
    }]}
    globalThis.__stockMinimumTransport = (url, options = {}) => {
        calls.push({url, options})
        if (url === '/api/cuaderno/stock-minimums/' && !options.method) return {ok: true, status: 200, data: envelope}
        return assert.fail(`Unexpected request ${url}`)
    }
    const api = moduleUrl(`export const cuadernoFetch = (url, options = {}) => globalThis.__stockMinimumTransport(url, options); export const readJson = async value => value;`)
    const forms = moduleUrl(`export const apiError = status => \`HTTP \${status}\`;`)
    const modelSelect = moduleUrl(`import {defineComponent,h} from ${JSON.stringify(import.meta.resolve('vue'))}; export default defineComponent({inheritAttrs:false,props:{modelValue:{default:null},label:String,disabled:Boolean},emits:['update:modelValue'],setup:(props,ctx)=>()=>h('model-select',{...ctx.attrs,...props,'onUpdate:modelValue':v=>ctx.emit('update:modelValue',v)})})`)
    const filename = 'StockMinimumPanel.vue'
    const {descriptor, errors} = parse(readFileSync(new URL('./components/StockMinimumPanel.vue', import.meta.url), 'utf8'), {filename})
    assert.deepEqual(errors, [])
    let code = compileScript(descriptor, {id: 'stock-minimum-consulta', inlineTemplate: true, templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    code = ts.transpileModule(code, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText
    const replacements = new Map([
        ['vue', import.meta.resolve('vue')], ['@/components/inputs/VModelSelect.vue', modelSelect],
        ['@/cuaderno/api', api], ['@/cuaderno/forms', forms], ['@/cuaderno/stockMinimumUi', helperUrl('./stockMinimumUi.ts')],
    ])
    code = code.replace(/from (["'])([^"']+)\1/g, (original, _quote, name) => { assert.ok(replacements.has(name), `Unexpected ${name}`); return `from ${JSON.stringify(replacements.get(name))}` })
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = renderer().createApp(component, {canOperate: false})
    for (const name of ['v-card', 'v-card-title', 'v-card-subtitle', 'v-card-text', 'v-spacer', 'v-btn', 'v-alert', 'v-row', 'v-col',
        'v-autocomplete', 'v-text-field', 'v-progress-linear', 'v-list', 'v-list-item', 'v-list-item-title', 'v-list-item-subtitle']) {
        app.component(name, Vue.defineComponent({inheritAttrs: false, props: {modelValue: {default: null}, label: String, disabled: Boolean, loading: Boolean}, emits: ['update:modelValue'],
            setup(props, context) { return () => Vue.h(name === 'v-btn' ? 'button' : name, {...context.attrs, ...props, 'onUpdate:modelValue': value => context.emit('update:modelValue', value)}, [context.slots.default?.(), context.slots.append?.()]) }}))
    }
    app.mount(root); await flush()
    try {
        assert.equal(button(root, 'Actualizar').props.disabled, false)
        for (const label of ['Alimento', 'Unidad', 'Ubicación (opcional)', 'Cantidad mínima']) assert.equal(field(root, label).props.disabled, true, label)
        assert.equal(button(root, 'Guardar mínimo').props.disabled, true)
        assert.equal(button(root, 'Editar').props.disabled, true)
        button(root, 'Editar').props.onClick(); await flush()
        assert.equal(field(root, 'Cantidad mínima').props.modelValue, '')
        field(root, 'Alimento').props['onUpdate:modelValue']({id: 2})
        field(root, 'Unidad').props['onUpdate:modelValue']({id: 3})
        field(root, 'Cantidad mínima').props['onUpdate:modelValue']('5')
        const form = all(root, node => node.type === 'form')[0]
        await form.props.onSubmit({preventDefault() {}}); await flush()
        assert.equal(calls.some(call => call.options.method === 'PUT'), false)
        await button(root, 'Actualizar').props.onClick(); await flush()
        assert.equal(calls.filter(call => !call.options.method).length, 2)
    } finally { app.unmount(); delete globalThis.__stockMinimumTransport }
})
