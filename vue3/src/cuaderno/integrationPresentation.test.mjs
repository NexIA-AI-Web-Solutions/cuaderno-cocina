import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {stripTypeScriptTypes} from 'node:module'

const source = readFileSync(new URL('../utils/integration_utils.ts', import.meta.url), 'utf8')
const executable = stripTypeScriptTypes(source, {mode: 'transform'})
    .replace(/^import .*;?$/gm, '').replace('export const INTEGRATIONS', 'const INTEGRATIONS')
const formats = new Function('brandMark', `${executable};return INTEGRATIONS`)('owned-mark.svg')

test('all native format handlers retain their interoperable IDs and capabilities', () => {
    const ids = ['DEFAULT', 'CHEFTAP', 'CHOWDOWN', 'COOKBOOKAPP', 'COOKLANG', 'COOKMATE', 'COPYMETHAT', 'DOMESTICA', 'MEALIE', 'MEALIE1', 'MEALMASTER', 'MELARECIPES', 'NEXTCLOUD', 'OPENEATS', 'PAPRIKA', 'PEPPERPLATE', 'PLANTOEAT', 'RECETTETEK', 'RECIPEKEEPER', 'RECIPESAGE', 'REZKONV', 'SAFFRON', 'REZEPTSUITEDE', 'GOURMET', 'PESTLE']
    assert.deepEqual(formats.map(format => format.id), ids)
    assert.ok(formats.every(format => format.import === true))
    assert.deepEqual(formats.filter(format => format.export).map(format => format.id), ['DEFAULT', 'CHOWDOWN', 'COOKLANG', 'NEXTCLOUD', 'RECIPESAGE', 'SAFFRON'])
})

test('format selection uses distinct functional labels rather than other product branding', () => {
    assert.equal(new Set(formats.map(format => format.name)).size, formats.length)
    for (const format of formats) {
        assert.doesNotMatch(format.name, /Cheftap|Chowdown|CookBookApp|Cooklang|Cookmate|Mealmaster|Melarecipes|CopyMeThat|Domestica|Mealie|Nextcloud|OpenEats|Paprika|Pepperplate|Plantoeat|RecetteTek|Recipekeeper|Recipesage|RezKonv|Saffron|Safron|Rezeptsuite|Gourmet|Pestle/i)
        assert.match(format.name, /Cuaderno Cocina|JSON|XML|YAML|Markdown|HTML|Texto|\.cook/)
        assert.equal(typeof format.description, 'string')
        assert.ok(format.description.length > 15)
    }
    assert.match(formats.find(format => format.id === 'MEALIE').name, /legado/)
    assert.match(formats.find(format => format.id === 'MEALIE1').name, /v1/)
    assert.match(formats.find(format => format.id === 'RECIPESAGE').name, /JSON-LD/)
})

test('format documentation and owned marks remain attached to the original protocol handler', () => {
    assert.equal(formats[0].imgSrc, 'owned-mark.svg')
    for (const format of formats) {
        assert.match(format.helpUrl, /^https:\/\/github\.com\/NexIA-AI-Web-Solutions\/cuaderno-cocina\/blob\/cuaderno\/main\/docs\/features\/import_export\.md#/)
    }
})

test('export chooser explains each supported format without altering native values or capability filtering', () => {
    const component = readFileSync(new URL('../components/settings/ExportDataSettings.vue', import.meta.url), 'utf8')
    const script = component.split('<script setup lang="ts">')[1].split('</script>')[0]
    const executable = stripTypeScriptTypes(script, {mode: 'transform'}).replace(/^import .*;?$/gm, '')
    const state = new Function('INTEGRATIONS', 'computed', 'ref', `${executable};return {exportFormats,exportType}`)(
        formats, get => ({get value() {return get()}}), value => ({value}),
    )
    assert.equal(state.exportType.value, 'DEFAULT')
    assert.deepEqual(state.exportFormats.value.map(item => item.value), formats.filter(format => format.export).map(format => format.id))
    for (const item of state.exportFormats.value) {
        const format = formats.find(format => format.id === item.value)
        assert.equal(item.title, format.name)
        assert.equal(item.props.subtitle, format.description)
    }
})

test('storage chooser explains authentication without exposing donor branding or changing protocol values', () => {
    const component = readFileSync(new URL('../components/model_editors/StorageEditor.vue', import.meta.url), 'utf8')
    const script = component.split('<script setup lang="ts">')[1].split('</script>')[0]
    const executable = stripTypeScriptTypes(script, {mode: 'transform'}).replace(/^import .*;?$/gm, '')
    const methods = new Function('defineProps', 'defineEmits', 'useModelEditorFunctions', 'watch', 'onMounted', `${executable};return storageMethods`)(
        () => ({}), () => () => {}, () => ({}), () => {}, () => {},
    )
    assert.deepEqual(methods.map(item => item.value), ['DB', 'NEXTCLOUD', 'LOCAL'])
    assert.equal(new Set(methods.map(item => item.title)).size, 3)
    assert.match(methods[0].title, /token/i)
    assert.match(methods[1].title, /usuario.*contraseña/i)
    assert.match(methods[2].title, /local/i)
    for (const item of methods) assert.doesNotMatch(item.title, /Dropbox|Nextcloud|Tandoor/i)
    assert.match(component, /v-model="editingObj.method" :items="storageMethods"/)
    assert.match(component, /editingObj.method == 'NEXTCLOUD'/)
    assert.match(component, /editingObj.method == 'DB'/)
})

test('every format help fragment names an actual section in the shipped documentation', () => {
    const docs = readFileSync(new URL('../../../docs/features/import_export.md', import.meta.url), 'utf8')
    const fragments = new Set([...docs.matchAll(/^## (.+)$/gm)].map(match => match[1].trim().toLowerCase().replace(/[^a-z0-9 -]/g, '').replaceAll(' ', '-')))
    for (const format of formats) assert.ok(fragments.has(new URL(format.helpUrl).hash.slice(1)), format.id)
    assert.equal(new URL(formats.find(format => format.id === 'REZEPTSUITEDE').helpUrl).hash, '#rezeptsuitede')
})
