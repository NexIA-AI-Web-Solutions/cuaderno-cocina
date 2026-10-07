import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync, readdirSync, mkdtempSync, writeFileSync, rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join, relative} from 'node:path'
import {fileURLToPath} from 'node:url'
import {component} from './functional/functionalHarness.mjs'
import {loadTestModule} from './testModuleLoader.mjs'

const read = path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('every translated product value uses the current brand while historical keys remain compatible', () => {
    for (const file of readdirSync(new URL('../locales/', import.meta.url)).filter(file => file.endsWith('.json'))) {
        const messages = JSON.parse(read(`locales/${file}`))
        for (const [key, value] of Object.entries(messages)) {
            assert.doesNotMatch(value, /tandoor/i, `${file}: ${key}`)
            if (key === 'open_data_help_text') {
                assert.doesNotMatch(value, /Cuaderno Cocina\s*(?:Open Data|開放資料|开放数据)/, file)
            }
        }
    }
    for (const locale of ['en', 'es']) {
        const messages = JSON.parse(read(`locales/${locale}.json`))
        for (const key of ['AboutTandoor', 'WelcometoTandoor', 'ImportIntoTandoor']) {
            assert.match(messages[key], /Cuaderno Cocina/)
        }
        assert.doesNotMatch(messages.ThanksTextHosted, /official|oficial/i)
        assert.doesNotMatch(messages.open_data_help_text, /Cuaderno Cocina Open Data/)
    }
})

test('anonymous and authenticated navigation share a local branded logo and own home route', () => {
    const app = read('apps/tandoor/Tandoor.vue')
    assert.doesNotMatch(app, /href="https:\/\/tandoor\.dev"|assets\/brand_logo\.svg/)
    assert.equal((app.match(/:src="brandLogo"/g) || []).length, 2)
    assert.equal((app.match(/alt="Cuaderno Cocina"/g) || []).length, 2)
    const assertHomeBrand = componentPath => {
        const document = {title: 'Previous page'}
        const router = {
            currentRoute: {value: {fullPath: '/', name: 'StartPage', meta: {}}},
            afterEach: () => () => {},
        }
        component(componentPath, [], {globals: {
            document,
            useRouter: () => router,
            watch: (source, callback, options) => {
                if (options?.immediate) callback(source(), undefined)
                return () => {}
            },
        }})
        assert.equal(document.title, 'Cuaderno Cocina')
    }
    assertHomeBrand('apps/tandoor/Tandoor.vue')

    // Execute a wrong-brand mutation of the same SFC to prove this assertion rejects it.
    const directory = mkdtempSync(join(tmpdir(), 'cuaderno-brand-title-'))
    try {
        const mutated = app.replaceAll("'Cuaderno Cocina'", "'Wrong brand'")
        assert.notEqual(mutated, app)
        const fixture = join(directory, 'Tandoor.vue')
        writeFileSync(fixture, mutated)
        const sourceRoot = fileURLToPath(new URL('../', import.meta.url))
        assert.throws(() => assertHomeBrand(relative(sourceRoot, fixture)), error =>
            error.code === 'ERR_ASSERTION' && error.actual === 'Wrong brand' && error.expected === 'Cuaderno Cocina')
    } finally {
        rmSync(directory, {recursive: true, force: true})
    }
    assert.match(app, /Cuaderno Cocina \{\{ useUserPreferenceStore\(\)\.serverSettings\.version/)
    assert.match(app, /activeSpace\.navLogo\?\.preview/)
})

test('original mark and wordmark are self-contained accessible SVGs with copper and olive geometry', () => {
    for (const file of ['cuaderno-mark.svg', 'cuaderno-logo.svg']) {
        const svg = read(`assets/${file}`)
        assert.match(svg, /<svg[^>]+viewBox=/)
        assert.match(svg, /<title[^>]*>Cuaderno Cocina/)
        assert.match(svg, /#b47b54/i)
        assert.match(svg, /#68744c/i)
        assert.match(svg, /<path|<rect/)
        assert.doesNotMatch(svg, /<image|<script|(?:href|src)=["']https?:|tandoor/i)
    }
})

test('theme labels change without changing persisted native theme identifiers', () => {
    for (const file of ['pages/WelcomePage.vue', 'components/settings/CosmeticSettings.vue']) {
        const source = read(file)
        assert.match(source, /title: 'Cuaderno Cocina', value: 'TANDOOR'/)
        assert.match(source, /title: 'Cuaderno Cocina oscuro \(incompleto\)', value: 'TANDOOR_DARK'/)
        assert.doesNotMatch(source, /title: 'Tandoor/)
    }
})

test('native exchange keeps DEFAULT compatibility and uses an owned bundled icon', () => {
    const source = read('utils/integration_utils.ts')
    assert.match(source, /id: 'DEFAULT', name: "Cuaderno Cocina",[^\n]*import: true, export: true/)
    assert.match(source, /import brandMark from ['"]@\/assets\/cuaderno-mark\.svg['"]/)
    assert.match(source, /imgSrc: brandMark/)
    assert.doesNotMatch(source, /imgSrc: ['"]https?:/)
})

test('shared recipe import points at this prefixed instance rather than another hosted service', () => {
    const source = read('components/dialogs/ImportTandoorDialog.vue')
    assert.doesNotMatch(source, /https:\/\/app\.tandoor\.dev|https:\/\/tandoor\.dev|assets\/logo_color\.svg/)
    assert.match(source, /getFullUrl\('recipe\/import'\)/)
    assert.match(source, /encodeURIComponent\(location\.href\)/)
    assert.match(source, /<v-tab value="hosted">Cuaderno Cocina<\/v-tab>/)
    assert.match(source, /selfhostedImportUrl/)
})

test('shared recipe import computes real root and prefix targets without losing source query parameters', async () => {
    const {useDjangoUrls} = await import(await loadTestModule('../composables/useDjangoUrls.ts'))
    const source = read('components/dialogs/ImportTandoorDialog.vue')
        .split('<script setup lang="ts">')[1].split('</script>')[0]
        .replace(/^import .*;?$/gm, '')
    const instantiate = new Function('computed', 'ref', 'useDjangoUrls', 'location', `${source}; return {hostedImportUrl, selfhostedImportUrl, selfhostedUrl}`)
    const previousDocument = globalThis.document, previousWindow = globalThis.window
    const location = {href: 'https://app.test/cuaderno-cocina/recipe/8/?share=synthetic&language=es#recipe'}
    try {
        for (const prefix of ['/', '/cuaderno-cocina/', '/other-prefix/']) {
            globalThis.document = {baseURI: `https://app.test${prefix}`}
            globalThis.window = {location: {origin: 'https://app.test'}}
            const state = instantiate(get => ({get value() {return get()}}), value => ({value}), useDjangoUrls, location)
            const target = new URL(state.hostedImportUrl.value)
            assert.equal(target.origin, 'https://app.test')
            assert.equal(target.pathname, `${prefix}recipe/import/`)
            assert.equal(target.searchParams.get('url'), location.href)
            assert.deepEqual([...target.searchParams.keys()], ['url'])
            state.selfhostedUrl.value = 'https://chosen-instance.test/own-prefix'
            const chosen = new URL(state.selfhostedImportUrl.value)
            assert.equal(chosen.pathname, '/own-prefix/recipe/import/')
            assert.equal(chosen.searchParams.get('url'), location.href)
        }
    } finally {
        globalThis.document = previousDocument
        globalThis.window = previousWindow
    }
})

test('help and acknowledgements show own identity while retaining original source attribution', () => {
    const help = read('components/display/HelpView.vue')
    const thanks = read('components/display/ThankYouNote.vue')
    assert.match(help, /Bienvenido a Cuaderno Cocina/)
    assert.match(help, /Código fuente/)
    assert.match(help, /https:\/\/github\.com\/NexIA-AI-Web-Solutions\/cuaderno-cocina/)
    assert.doesNotMatch(help, /Welcome to Tandoor|Tandoor is|Tandoor can|your Tandoor|href="https:\/\/tandoor\.dev"/)
    assert.doesNotMatch(thanks, /assets\/logo_color\.svg|GitHub Sponsors/)
    assert.match(thanks, /:image="brandMark"/)
    assert.doesNotMatch(thanks, /github\.com\/sponsors/)
})

test('all Vue template text and default logo references are free of previous product branding', () => {
    const walk = directory => readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
        const path = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory)
        return entry.isDirectory() ? walk(path) : [path]
    })
    for (const file of walk(new URL('../', import.meta.url)).filter(file => file.pathname.endsWith('.vue'))) {
        const source = readFileSync(file, 'utf8')
        const template = source.split('<template>')[1]?.split('<script')[0] || ''
        const visible = template.replace(/<!--[\s\S]*?-->/g, '').replace(/\{\{[\s\S]*?\}\}/g, '')
        for (const [, text] of visible.matchAll(/>([^<]*)</g)) {
            assert.doesNotMatch(text, /tandoor/i, file.pathname)
        }
        assert.doesNotMatch(visible, /(?:brand_logo|logo_color)\.svg|(?:href|src)="https?:\/\/[^"\s]*tandoor/i, file.pathname)
    }
})

test('generated SDK identifies this product and preserves native enum wire values', () => {
    for (const file of ['openapi/runtime.ts', 'openapi/templates/runtime.mustache', 'openapi/models/ThemeEnum.ts', 'openapi/models/SpaceThemeEnum.ts']) {
        const source = read(file)
        assert.match(source, / \* Cuaderno Cocina\n \* Cuaderno Cocina API Docs/)
        if (file.endsWith('Enum.ts')) {
            assert.match(source, /Tandoor: 'TANDOOR'/)
            assert.match(source, /TandoorDark: 'TANDOOR_DARK'/)
        }
    }
})
