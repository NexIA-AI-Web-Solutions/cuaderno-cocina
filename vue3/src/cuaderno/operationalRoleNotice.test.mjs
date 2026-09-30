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
        remove: () => {}, patchProp: (node, key, _old, value) => { node.props[key] = value },
        setScopeId: () => {}, insertStaticContent: () => assert.fail('No static HTML'),
    })
}
const textOf = root => {
    const text = []
    const visit = node => { if (node.type === '#text') text.push(node.text); for (const child of node.children || []) visit(child) }
    visit(root)
    return text.join(' ')
}
async function mount(role) {
    const filename = 'OperationalRoleNotice.vue'
    const {descriptor, errors} = parse(readFileSync(new URL('./components/OperationalRoleNotice.vue', import.meta.url), 'utf8'), {filename})
    assert.deepEqual(errors, [])
    let code = compileScript(descriptor, {id: 'role-notice', inlineTemplate: true,
        templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    code = ts.transpileModule(code, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
        .replace(/from ["']vue["']/g, `from ${JSON.stringify(import.meta.resolve('vue'))}`)
        .replace(/import .*operationalRoleUi.*;?/g, '')
    const component = (await import(moduleUrl(code))).default
    const root = {type: 'root', props: {}, children: [], parent: null}
    const app = renderer().createApp(component, {role})
    app.component('v-alert', Vue.defineComponent({setup(_props, context) { return () => Vue.h('v-alert', context.slots.default?.()) }}))
    app.mount(root)
    await Vue.nextTick()
    return {text: textOf(root), close: () => app.unmount()}
}

test('describes Consulta without declaring the whole native product read-only', async () => {
    const mounted = await mount({code: 'guest', label: 'Consulta', space: 4,
        can_operate_cuaderno: false, can_manage_edition: false, native_permissions_preserved: true})
    assert.match(mounted.text, /Consulta/)
    assert.match(mounted.text, /espacio 4/)
    assert.match(mounted.text, /Cuaderno operativo.+no permitido/i)
    assert.match(mounted.text, /costes/i)
    assert.match(mounted.text, /propietarios.+libros.+menús.+listas/i)
    assert.doesNotMatch(mounted.text, /solo lectura global|todo.+solo lectura/i)
    mounted.close()
})

test('distinguishes Cocina, Responsable and an unverified response', async () => {
    for (const [role, expected] of [
        [{code: 'user', label: 'Cocina', space: 8, can_operate_cuaderno: true, can_manage_edition: false, native_permissions_preserved: true}, /Cocina.+permitido/si],
        [{code: 'admin', label: 'Responsable', space: 9, can_operate_cuaderno: true, can_manage_edition: true, native_permissions_preserved: true}, /Responsable.+gestionar la edición/si],
        [null, /no se ha podido confirmar el rol operativo/i],
    ]) {
        const mounted = await mount(role)
        assert.match(mounted.text, expected)
        mounted.close()
    }
})
