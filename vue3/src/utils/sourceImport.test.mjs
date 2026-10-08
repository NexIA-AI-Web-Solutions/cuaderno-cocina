import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
import {component, settle} from '../cuaderno/functional/functionalHarness.mjs'

const source = readFileSync(new URL('./sourceImport.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {
    compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022},
}).outputText
const {sourceImportRequest, sourcePreviewIngredientAmount, SourceImportPrecisionError} = await import(
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
    assert.equal(request.steps[0].ingredients[0].amount, '1.25')
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
    assert.equal(request.steps[0].ingredients[0].amount, '0.333333')
})

test('native decimal previews accept only quantities preserved by the numeric JSON wire roundtrip', () => {
    for (const [amount, expected] of [['400.5000000000000000', 400.5], ['0.0000000000000001', 1e-16],
        ['-2.5000000000000000', -2.5], ['-0.0000000000000000', 0], ['9007199254740992', 9007199254740992]]) {
        assert.equal(sourcePreviewIngredientAmount(amount), expected)
    }
})

test('numeric source previews reject significant rounding and invalid quantities with a Spanish recovery message', () => {
    for (const amount of ['9999999999999999.1234567890123456', '400.1234567890123456', '9007199254740993',
        '', 'NaN', 'Infinity', 'invalid', '400,5', '1e-16', '0.00000000000000001', null, 400, true]) {
        assert.throws(() => sourcePreviewIngredientAmount(amount), error => {
            assert.ok(error instanceof SourceImportPrecisionError)
            assert.match(error.message, /sin perder precisión/)
            assert.match(error.message, /editor de recetas/)
            return true
        })
    }
})

function recipeSorter(nativeRecipe) {
    return component('pages/RecipeImportPage.vue', ['aiStepSort', 'importResponse', 'aiStepSortLoading'], {
        api: {apiAiStepSortCreate: async () => nativeRecipe},
        globals: {
            sourceImportRequest, sourcePreviewIngredientAmount, SourceImportPrecisionError,
            useFileApi: () => ({updateRecipeImage: async () => ({}), doAiImport: async () => ({}),
                doAppImport: async () => 1, fileApiLoading: {value: false}}),
            useDjangoUrls: () => ({getFullUrl: path => path}),
        },
    })
}

test('actual AI-sort precision rejection retains the draft and displays its Spanish recovery message', async () => {
    const h = recipeSorter({name: 'Native result', steps: [{ingredients: [{amount: '9999999999999999.1234567890123456'}]}]})
    const draft = {name: 'Original draft', steps: [{ingredients: [
        {amount: 400.5, food: {name: 'Food'}, unit: {name: 'Unit'}, originalText: ''},
    ]}]}
    const before = structuredClone(draft)
    h.exposed.importResponse.value = {recipe: draft}
    h.exposed.aiStepSort(7)
    await settle()
    assert.equal(h.exposed.importResponse.value.recipe, draft)
    assert.deepEqual(draft, before)
    assert.equal(h.exposed.aiStepSortLoading.value, false)
    assert.equal(h.messages.length, 1)
    assert.equal(h.messages[0][0], 'error', 'the actual catch must display the message, not hide it in generic fetch-error data')
    assert.equal(h.messages[0][1].title, 'Revisa las cantidades')
    assert.match(h.messages[0][1].text, /sin perder precisión.*editor de recetas/)
})

test('actual AI-sort preview preserves supported normal and tiny quantities without an error', async () => {
    const h = recipeSorter({name: 'Native result', steps: [{ingredients: [
        {amount: '400.5000000000000000'}, {amount: '0.0000000000000001'},
    ]}]})
    h.exposed.importResponse.value = {recipe: {name: 'Original draft', steps: []}}
    h.exposed.aiStepSort(7)
    await settle()
    assert.deepEqual(Array.from(h.exposed.importResponse.value.recipe.steps[0].ingredients, ingredient => ingredient.amount),
        [400.5, 1e-16])
    assert.equal(h.exposed.aiStepSortLoading.value, false)
    assert.deepEqual(h.messages, [])
})
