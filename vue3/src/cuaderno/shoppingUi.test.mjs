import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./shoppingUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {shoppingLists, shoppingEntries, shoppingEntryResponse, ifMatchRevision, shoppingSourceLabel} = await import(
    `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
)

const entry = {
    id: 3, amount: '1.5', checked: false, updated_at: '2026-10-04T10:00:00.123456+02:00',
    food: {id: 8, name: 'Arroz'}, unit: {id: 5, name: 'kg'}, shopping_lists: [{id: 2}],
    list_recipe_data: {recipe: {name: 'Paella'}},
}

test('shopping boundaries accept complete native pages and reject malformed success payloads', () => {
    assert.deepEqual(shoppingLists({results: [{id: 2, name: 'Compra'}]}), [{id: 2, name: 'Compra'}])
    assert.deepEqual(shoppingEntries({results: [entry]}), [entry])
    for (const change of [{id: true}, {updated_at: ''}, {checked: 'false'}, {food: null}, {shopping_lists: [{}]}]) {
        assert.equal(shoppingEntries([{...entry, ...change}]), null)
    }
    assert.equal(shoppingLists({results: [{id: 2, name: 'Compra'}, {id: 2, name: 'Otra'}]}), null)
})

test('toggle response must confirm identity, state and a usable exact revision', () => {
    assert.deepEqual(shoppingEntryResponse({...entry, checked: true}, 3, true), {...entry, checked: true})
    assert.equal(shoppingEntryResponse({...entry, id: 4, checked: true}, 3, true), null)
    assert.equal(shoppingEntryResponse({...entry, checked: false}, 3, true), null)
    assert.equal(ifMatchRevision(entry.updated_at), '"2026-10-04T10:00:00.123456+02:00"')
    assert.equal(ifMatchRevision(''), null)
    assert.equal(ifMatchRevision('2026-10-04T10:00:00Z"\r\nX: bad'), null)
})

test('line provenance stays explicit without inventing a recipe', () => {
    assert.equal(shoppingSourceLabel(entry.list_recipe_data), 'Receta: Paella')
    assert.equal(shoppingSourceLabel(null), 'Añadido manualmente')
    assert.equal(shoppingSourceLabel({recipe: {id: 1}}), 'Origen de receta')
})
