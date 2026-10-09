// Virtual Vue unit boundary; this does not substitute for browser or database checks.
import {readFileSync} from 'node:fs'
import assert from 'node:assert/strict'
import {compileScript, parse} from '@vue/compiler-sfc'
import ts from 'typescript'
import * as Vue from 'vue'
export const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
export function all(root, predicate) {
    const out = []
    const visit = node => {if (predicate(node)) out.push(node); for (const child of node.children || []) visit(child)}
    visit(root); return out
}
export const textOf = root => all(root, node => node.type === '#text').map(node => node.text).join(' ')
export const button = (root, text) => all(root, node => node.type === 'button' && textOf(node).includes(text))[0]
export const field = (root, label) => all(root, node => node.props?.label === label)[0]
export async function flush() {for (let i = 0; i < 24; i++) await Vue.nextTick()}
let sequence = 0
export async function mountFunctional(filename, props, transport, upload = () => assert.fail('Unexpected upload'), options = {}) {
    const id = ++sequence, calls = []
    globalThis.__cuadernoFunctionalUnits ??= new Map()
    globalThis.__cuadernoFunctionalUnits.set(id, {transport, upload, calls})
    const api = moduleUrl(`
        export const dietOptions = [{slug:'celiacos',label:'Celíacos'}];
        export async function planningRequest(path,method='GET',body) {
            const state=globalThis.__cuadernoFunctionalUnits.get(${id});state.calls.push({path,method,body});return state.transport(path,method,body);
        }
        export const validateEntityImage = file => {if(file.size > 5*1024*1024 || !['image/png','image/jpeg','image/webp','image/gif'].includes(file.type)) throw new Error('Elige una imagen JPG, PNG, WebP o GIF sin animación de hasta 5 MiB.')};
        export const uploadEntityImage = (...args) => globalThis.__cuadernoFunctionalUnits.get(${id}).upload(...args);
        export const uploadRecipeGallery = (...args) => globalThis.__cuadernoFunctionalUnits.get(${id}).upload(...args);
    `)
    let imagePanel = moduleUrl(`export default {render: () => null}`)
    if (options.actualImagePanel) {
        const panelFilename = './components/EntityImagePanel.vue'
        const {descriptor: panelDescriptor} = parse(readFileSync(new URL(panelFilename, import.meta.url), 'utf8'), {filename: panelFilename})
        let panelSource = compileScript(panelDescriptor, {id: `image-panel-${id}`, inlineTemplate: true, templateOptions: {compilerOptions: {hoistStatic: false}}}).content
        panelSource = ts.transpileModule(panelSource, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText
        panelSource = panelSource.replace(/from (["'])([^"']+)\1/g, (_, _quote, name) => {
            assert.ok(['vue', '@/cuaderno/planningApi'].includes(name), name)
            return `from ${JSON.stringify(name === 'vue' ? import.meta.resolve('vue') : api)}`
        })
        imagePanel = moduleUrl(panelSource)
    }
    const downloadModule = moduleUrl(`export async function downloadMenu(doc,format,onPages) {onPages(2);globalThis.__cuadernoExportCalls?.push({doc,format});return 2}`)
    const selector = moduleUrl(`import {h} from ${JSON.stringify(import.meta.resolve('vue'))};export default {props:['modelValue','label','disabled'],emits:['update:modelValue'],setup:(p,c)=>()=>h('model-select',{...p,'onUpdate:modelValue':v=>c.emit('update:modelValue',v)})}`)
    const {descriptor, errors} = parse(readFileSync(new URL(filename, import.meta.url), 'utf8'), {filename})
    assert.deepEqual(errors, [])
    let source = compileScript(descriptor, {id: `functional-${id}`, inlineTemplate: true, templateOptions: {compilerOptions: {hoistStatic: false}}}).content
    source = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText
    const replacements = new Map([['vue', import.meta.resolve('vue')], ['luxon', import.meta.resolve('luxon')], ['@/cuaderno/planningApi', api],
        ['@/cuaderno/planningUi.mjs', new URL('./planningUi.mjs', import.meta.url).href], ['@/components/inputs/VModelSelect.vue', selector], ['@/cuaderno/components/EntityImagePanel.vue',imagePanel], ['@/cuaderno/menuExportBrowser',downloadModule]])
    source = source.replace(/from (["'])([^"']+)\1/g, (_, _quote, name) => {assert.ok(replacements.has(name), name); return `from ${JSON.stringify(replacements.get(name))}`})
    const component = (await import(moduleUrl(source))).default
    const renderer = Vue.createRenderer({
        createElement: type => ({type, props: {}, children: [], parent: null}), createText: text => ({type: '#text', text, children: [], parent: null}),
        createComment: text => ({type: '#comment', text, children: [], parent: null}), setText: (node, text) => {node.text = text},
        setElementText: (node, text) => {node.children = [{type: '#text', text, children: [], parent: node}]}, parentNode: node => node.parent,
        nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
        insert(node, parent, anchor = null) {if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = parent; const index = anchor ? parent.children.indexOf(anchor) : -1; if (index < 0) parent.children.push(node); else parent.children.splice(index, 0, node)},
        remove(node) {if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null},
        patchProp: (node, key, _old, value) => {node.props[key] = value}, setScopeId: () => {}, insertStaticContent: () => assert.fail('Static HTML disabled'),
    })
    const app = renderer.createApp(component, props), root = {type: 'root', props: {}, children: [], parent: null}
    const tags = new Set([...readFileSync(new URL(filename, import.meta.url), 'utf8').matchAll(/<(v-[a-z-]+|router-link)\b/g)].map(match => match[1]))
    for (const tag of tags) app.component(tag, Vue.defineComponent({inheritAttrs: false, props: {modelValue: {default: null}, label: String, disabled: Boolean, loading: Boolean}, emits: ['update:modelValue'],
        setup(p, c) {return () => tag === 'v-dialog' && !p.modelValue ? null : Vue.h(tag === 'v-btn' ? 'button' : tag, {...c.attrs, ...p, 'onUpdate:modelValue': value => c.emit('update:modelValue', value)}, [c.slots.default?.(), c.slots.append?.()])}}))
    app.mount(root); await flush()
    return {root, calls, close() {app.unmount(); globalThis.__cuadernoFunctionalUnits.delete(id)}}
}
