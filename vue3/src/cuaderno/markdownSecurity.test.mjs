import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
import {compile} from '@vue/compiler-dom'
import * as Vue from 'vue'

const cases = {
    legitimate: '> Quote\n\n{{ scale(100) }}',
    script: '<img src="x" onerror="globalThis.__markdownXss=1"><script>globalThis.__markdownXss=1</script>',
    crossBoundaryLink: '<a href="java&#x73;cript:globalThis.__markdownXss=1">enlace</a>',
    svgOnload: '<svg onload="globalThis.__markdownXss=1"><circle></circle></svg>',
    iframeSrcdoc: '<iframe srcdoc="<script>globalThis.__markdownXss=1</script>"></iframe>',
    directives: '<div @click="globalThis.__markdownXss=1" v-html="globalThis.__markdownXss=1"></div>',
    jinjaEncoded: String.raw`{{ "\x3cimg src=x onerror=globalThis.__markdownXss=1\x3e" }}`,
    jinjaFormat: String.raw`{{ "%cimg src=x onerror=globalThis.__markdownXss=1%c"|format(60,62) }}`,
    scalableConstructor: '<scalable-number v-bind:number="\'\'.constructor.constructor(\'globalThis.__markdownXss=1\')()" v-bind:factor="ingredient_factor"></scalable-number>',
    pluralConstructor: '<plural-name singular="unidad" plural="unidades" v-bind:amount="constructor.constructor(\'globalThis.__markdownXss=1\')()" v-bind:factor="ingredient_factor" :no-amount="false"></plural-name>',
    nonFinite: '<scalable-number v-bind:number="NaN" v-bind:factor="ingredient_factor"></scalable-number><plural-name singular="u" plural="us" v-bind:amount="Infinity" v-bind:factor="ingredient_factor" :no-amount="false"></plural-name>{{ scale("-Infinity") }}',
}

const markerStart = '__CUADERNO_MARKDOWN_JSON_START__'
const markerEnd = '__CUADERNO_MARKDOWN_JSON_END__'
const python = [
    'import base64, json, os',
    'from cookbook.helper.template_helper import render_instructions',
    'class Ingredients:',
    '    def all(self): return []',
    'class Step:',
    '    ingredients = Ingredients()',
    '    def __init__(self, instruction): self.instruction = instruction',
    'payloads = json.loads(base64.b64decode(os.environ["MARKDOWN_CASES_B64"]).decode("utf-8"))',
    'rendered = {name: render_instructions(Step(source)) for name, source in payloads.items()}',
    `print("${markerStart}" + json.dumps(rendered, ensure_ascii=False) + "${markerEnd}")`,
].join('\n')

function backendRenderedInstructions() {
    const encoded = Buffer.from(JSON.stringify(cases), 'utf8').toString('base64')
    const result = spawnSync('docker', [
        'exec', '-e', `MARKDOWN_CASES_B64=${encoded}`, 'cuaderno-g0-t002-web',
        '/opt/recipes/venv/bin/python', 'manage.py', 'shell', '-c', python,
    ], {encoding: 'utf8', timeout: 20_000, windowsHide: true})
    assert.notEqual(result.error?.code, 'ETIMEDOUT', 'render_instructions superó el límite local de 20 s')
    assert.equal(result.status, 0, `Falló render_instructions real:\n${result.stderr || result.stdout}`)
    const start = result.stdout.indexOf(markerStart)
    const end = result.stdout.indexOf(markerEnd, start + markerStart.length)
    assert.ok(start >= 0 && end > start, `Salida Django sin JSON delimitado:\n${result.stdout}`)
    return JSON.parse(result.stdout.slice(start + markerStart.length, end))
}

function virtualRenderer(observedProps) {
    const insert = (child, parent, anchor = null) => {
        child.parent = parent
        const position = anchor === null ? -1 : parent.children.indexOf(anchor)
        if (position < 0) parent.children.push(child)
        else parent.children.splice(position, 0, child)
    }
    return Vue.createRenderer({
        createElement: type => ({type, props: {}, children: [], parent: null}),
        createText: text => ({type: '#text', text, props: {}, children: [], parent: null}),
        createComment: text => ({type: '#comment', text, props: {}, children: [], parent: null}),
        setText: (node, text) => { node.text = text },
        setElementText: (node, text) => { node.children = [{type: '#text', text, props: {}, children: [], parent: node}] },
        parentNode: node => node.parent,
        nextSibling: node => {
            if (!node.parent) return null
            const index = node.parent.children.indexOf(node)
            return node.parent.children[index + 1] || null
        },
        insert,
        remove: node => {
            if (!node.parent) return
            const index = node.parent.children.indexOf(node)
            if (index >= 0) node.parent.children.splice(index, 1)
        },
        patchProp: (node, key, _previous, value) => { node.props[key] = value },
        setScopeId: () => {},
        cloneNode: node => ({...node, props: {...node.props}, children: [...node.children], parent: null}),
        insertStaticContent: () => assert.fail('El compilador introdujo HTML estático opaco que el recorrido no puede inspeccionar'),
    })
}

function compileAndMount(template, observedProps) {
    const {code} = compile(template, {mode: 'function', hoistStatic: false, prefixIdentifiers: true})
    // The compiler executes only the backend-sanitized template from fixed synthetic cases.
    const render = Function('Vue', code)(Vue)
    const component = name => ({
        name,
        props: {
            number: Number, amount: Number, factor: Number, noAmount: Boolean,
            singular: String, plural: String,
        },
        setup(props) {
            observedProps.push({...props})
            const value = props.number ?? props.amount
            return () => Vue.h('output', {}, value === undefined ? '' : String(value * (props.factor ?? 1)))
        },
    })
    const root = {type: '#root', props: {}, children: [], parent: null}
    virtualRenderer(observedProps).createApp({
        data: () => ({ingredient_factor: 1}),
        render,
    }).component('scalable-number', component('scalable-number'))
        .component('plural-name', component('plural-name'))
        .mount(root)
    return root
}

function walk(node, visit) {
    visit(node)
    for (const child of node.children || []) walk(child, visit)
}

test('backend Markdown remains inert when Vue compiles and mounts it', {timeout: 30_000}, () => {
    globalThis.__markdownXss = 0
    const rendered = backendRenderedInstructions()
    const mounted = {}
    const observedProps = []
    for (const [name, template] of Object.entries(rendered)) {
        assert.equal(typeof template, 'string', name)
        mounted[name] = compileAndMount(template, observedProps)
    }

    assert.equal(globalThis.__markdownXss, 0)
    for (const [name, root] of Object.entries(mounted)) {
        walk(root, node => {
            assert.ok(!['script', 'svg', 'iframe', 'object', 'embed', 'template'].includes(node.type), name)
            for (const [key, value] of Object.entries(node.props || {})) {
                assert.ok(!/^on/i.test(key), `${name}: prop ejecutable ${key}`)
                assert.ok(!['innerHTML', 'srcdoc'].includes(key), `${name}: prop ejecutable ${key}`)
                if (key === 'href') assert.ok(!String(value).trim().toLowerCase().startsWith('javascript:'), name)
            }
        })
    }
    for (const props of observedProps) {
        for (const value of [props.number, props.amount, props.factor]) {
            if (value !== undefined) assert.ok(Number.isFinite(value), `Prop no finito: ${value}`)
        }
    }

    let legitimateText = ''
    walk(mounted.legitimate, node => { if (node.type === '#text') legitimateText += node.text })
    assert.match(legitimateText, /Quote/)
    assert.match(legitimateText, /100/)
    const scaleProps = observedProps.find(props => props.number === 100)
    assert.ok(scaleProps)
    assert.equal(scaleProps.factor, 1)
    assert.ok(scaleProps.number > 0)
    delete globalThis.__markdownXss
})
