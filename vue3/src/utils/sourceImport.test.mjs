import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./sourceImport.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {
    compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022},
}).outputText
const {sourceImportRequest} = await import(
    `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
)

test('source import builds native nested requests without inventing catalog identities', () => {
    const request = sourceImportRequest({
        name: 'Pan', sourceUrl: 'https://example.test/pan', servings: 2.5,
        keywords: [{id: 7, name: 'Horno'}, {name: 'Masa'}],
        steps: [{
            instruction: 'Mezclar', showIngredientsTable: true,
            ingredients: [
                {amount: 1.25, food: {name: 'Harina'}, unit: {name: 'kg'}, order: 3, originalText: '1,25 kg harina'},
                {amount: 2, food: {name: 'Huevos'}, unit: {name: '   '}, order: null, originalText: '2 huevos'},
            ],
        }],
    })

    assert.deepEqual(request.keywords, [{id: 7, name: 'Horno'}, {name: 'Masa'}])
    assert.equal(request.steps[0].ingredients[0].amount, 1.25)
    assert.equal(request.steps[0].ingredients[0].order, 3)
    assert.deepEqual(request.steps[0].ingredients[0].unit, {name: 'kg'})
    assert.equal(request.steps[0].ingredients[1].unit, null)
    assert.equal(request.steps[0].ingredients[1].order, 0)
    assert.equal(request.sourceUrl, 'https://example.test/pan')
    assert.equal(request.servings, 2.5)
})

test('source import normalizes omitted keyword and ingredient order collections', () => {
    const request = sourceImportRequest({
        name: 'Agua', sourceUrl: '', steps: [{
            instruction: '', ingredients: [
                {amount: 0.333333, food: {name: 'Agua'}, unit: {name: 'l'}, originalText: 'un tercio de litro'},
            ],
        }],
    })

    assert.deepEqual(request.keywords, [])
    assert.equal(request.steps[0].ingredients[0].order, 0)
    assert.equal(request.steps[0].ingredients[0].amount, 0.333333)
})
