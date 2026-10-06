import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'

const source = path => readFileSync(new URL(path, import.meta.url), 'utf8')

function preferenceKeys(baseURI) {
    const code = source('../stores/UserPreferenceStore.ts').match(/^const .*_KEY = .+$/gm).join('\n')
    const helper = source('./storage.ts').replace('export function', 'function').replace('key: string', 'key')
    return vm.runInNewContext(helper + '\n' + code + '\n;[DEVICE_SETTINGS_KEY, USER_PREFERENCE_KEY, SERVER_SETTINGS_KEY, ACTIVE_SPACE_KEY, USER_SPACES_KEY, SPACES_KEY]', {URL, document: {baseURI}})
}

test('all persisted preferences and messages belong to the deployment prefix', () => {
    const keys = preferenceKeys('https://cocina.example/cuaderno-cocina/')
    assert.equal(new Set(keys).size, 6)
    for (const key of keys) assert.ok(key.startsWith('cuaderno:%2Fcuaderno-cocina%2F:'))
    assert.ok(preferenceKeys('https://cocina.example/kitchen/').every(key => !keys.includes(key)))
    assert.match(source('../stores/MessageStore.ts'), /useStorage\(cuadernoStorageKey\('messages'\)/)
})

function runBookmarklet(bookmarkletJs = 'https://cocina.example/cuaderno-cocina/static/vue3/bookmarklet.js') {
    const page = source('../pages/RecipeImportPage.vue')
    const block = page.match(/const bookmarkletContent = computed\(\(\) => \{([\s\S]*?)\n\}\)/)[1]
    const contents = vm.runInNewContext('(function(){' + block + '})()', {
        getFullUrl: path => 'https://cocina.example/cuaderno-cocina' + path,
        bookmarkletToken: {value: 'private-token'}, bookmarkletJs, URL, document: {baseURI: 'https://cocina.example/cuaderno-cocina/'},
    })
    const values = new Map([['token', 'foreign-token'], ['importURL', 'https://foreign.example/api/']])
    const requests = [], opened = [], scripts = []
    const storage = {getItem: key => values.get(key), setItem: (key, value) => values.set(key, value)}
    const context = {
        URL, console, localStorage: storage,
        window: {location: {protocol: 'https:', host: 'recipes.example', pathname: '/recipe/1'}, open: url => opened.push(url)},
        XMLHttpRequest: class {
            constructor() { this.headers = {}; requests.push(this) }
            open(method, url) { this.method = method; this.url = url }
            setRequestHeader(key, value) { this.headers[key] = value }
            send(body) { this.body = body; this.readyState = 4; this.status = 201; this.response = '{"id":42}'; this.onload() }
        },
    }
    context.document = {
        documentElement: {outerHTML: '<html>recipe</html>'},
        createElement: () => ({}), getElementsByTagName: () => [{appendChild() {}}],
        body: {appendChild(script) { scripts.push(script.src); vm.runInNewContext(source('../assets/bookmarklet_v3.js'), context); script.onload?.(); return script }},
    }
    vm.runInNewContext(contents.replace(/^javascript:/, ''), context)
    return {values, requests, opened, scripts, context, contents}
}

test('bookmarklet imports without overwriting foreign storage or persisting its token', () => {
    const result = runBookmarklet()
    assert.deepEqual([...result.values], [['token', 'foreign-token'], ['importURL', 'https://foreign.example/api/']])
    assert.equal(result.requests.length, 1)
    assert.equal(result.requests[0].url, 'https://cocina.example/cuaderno-cocina/api/bookmarklet-import/')
    assert.equal(result.requests[0].headers.Authorization, 'Bearer private-token')
    assert.equal(result.opened[0], 'https://cocina.example/cuaderno-cocina/recipe/import/?bookmarklet_import=42')
    vm.runInNewContext(result.contents.replace(/^javascript:/, ''), result.context)
    assert.equal(result.requests.length, 2)
})


test('bookmarklet resolves Vite build-relative script URLs against own static assets', () => {
    assert.deepEqual(runBookmarklet('./assets/bookmarklet.js').scripts, [
        'https://cocina.example/cuaderno-cocina/static/vue3/assets/bookmarklet.js',
    ])
})
