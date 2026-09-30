import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse, compileScript} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const all = (root, predicate) => {
    const found = []
    const visit = node => { if (predicate(node)) found.push(node); for (const child of node.children || []) visit(child) }
    visit(root)
    return found
}
const textOf = root => all(root, node => node.type === '#text').map(node => node.text).join(' ')

function renderer() {
    return Vue.createRenderer({
        createElement: type => ({type, props: {}, children: [], parent: null}),
        createText: text => ({type: '#text', text, children: [], parent: null}),
        createComment: text => ({type: '#comment', text, children: [], parent: null}),
        setText: (node, text) => { node.text = text },
        setElementText: (node, text) => { node.children = [{type: '#text', text, children: [], parent: node}] },
        parentNode: node => node.parent,
        nextSibling: () => null,
        insert(node, parent) { node.parent = parent; parent.children.push(node) },
        remove: () => {}, patchProp: (node, key, _old, value) => { node.props[key] = value },
        setScopeId: () => {}, insertStaticContent: () => assert.fail('No static HTML'),
    })
}

async function mount(classification) {
    const filename = 'ProductionWastePanel.vue'
    const {descriptor, errors} = parse(readFileSync(new URL('./components/ProductionWastePanel.vue', import.meta.url), 'utf8'), {filename})
    assert.deepEqual(errors, [])
    let code = compileScript(descriptor, {id: 'production-waste-panel', inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    code = ts.transpileModule(code, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
        .replace(/from ["']vue["']/g, `from ${JSON.stringify(import.meta.resolve('vue'))}`)
        .replace(/import .*productionWasteUi.*;?/g, '')
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = renderer().createApp(component, {classification})
    for (const name of ['v-alert', 'v-list', 'v-list-item']) app.component(name, Vue.defineComponent({
        setup(_props, context) {
            return () => Vue.h(name, [context.slots.title?.(), context.slots.subtitle?.(), context.slots.default?.()])
        },
    }))
    app.mount(root)
    await Vue.nextTick()
    return {root, close: () => app.unmount()}
}

test('renders declared-only coverage and exact frozen quantities without actions', async () => {
    const mounted = await mount({status: 'declared', lines: [{food_name: 'Aceite', unit_name: 'L',
        purchased_quantity: '5.0000000000000001', useful_quantity: '4', waste_quantity: '1.0000000000000001',
        quantity_basis: 'net_usable', yield_ratio: '0.8'}]})
    const text = textOf(mounted.root)
    assert.match(text, /Merma teórica declarada/)
    assert.match(text, /solo rendimientos declarados/i)
    assert.match(text, /1\.0000000000000001 L/)
    assert.match(text, /no registra un segundo consumo/i)
    assert.equal(all(mounted.root, node => node.type === 'button').length, 0)
    mounted.close()
})

test('unknown and legacy classifications never display an invented zero', async () => {
    for (const classification of [null, {status: 'unknown', lines: []}]) {
        const mounted = await mount(classification)
        const text = textOf(mounted.root)
        assert.match(text, /desconocida/i)
        assert.doesNotMatch(text, /\b0(?:[,.]0+)?\b/)
        mounted.close()
    }
})

test('repeated ingredient traces remain separate and are never summed in the panel', async () => {
    const mounted = await mount({status: 'declared', lines: [
        {ingredient_id: 11, food_name: 'Aceite', unit_name: 'L', purchased_quantity: '0.5',
            useful_quantity: '0.4', waste_quantity: '0.1', quantity_basis: 'net_usable', yield_ratio: '0.8'},
        {ingredient_id: 11, food_name: 'Aceite', unit_name: 'L', purchased_quantity: '1',
            useful_quantity: '0.8', waste_quantity: '0.2', quantity_basis: 'net_usable', yield_ratio: '0.8'},
    ]})
    const text = textOf(mounted.root)
    assert.match(text, /Merma teórica: 0\.1 L/)
    assert.match(text, /Merma teórica: 0\.2 L/)
    assert.doesNotMatch(text, /Merma teórica: 0\.3 L/)
    mounted.close()
})
