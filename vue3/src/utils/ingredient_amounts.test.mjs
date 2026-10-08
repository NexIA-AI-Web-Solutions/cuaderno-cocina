import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./ingredient_amounts.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText
const {normalizeIngredientAmount, ingredientAmountLabel, ingredientAmountDisplayLabel, isZeroIngredientAmount,
    autocorrectIngredientAmount, prepareIngredientAmounts, prepareScaledIngredientAmounts, sumIngredientAmounts} = await import(
    `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('ingredient edits keep all significant digits and normalize comma, whitespace and redundant zeros', () => {
    for (const [input, value] of [[' 400,5000000000000000 ', '400.5'], ['+000400.000', '400'],
        ['0.0000000000000001', '0.0000000000000001'],
        ['9999999999999999.1234567890123456', '9999999999999999.1234567890123456'],
        ['-0.000', '0'], ['-2,5000', '-2.5'], ['400.', '400']]) {
        assert.deepEqual(normalizeIngredientAmount(input), {value, error: ''})
    }
})

test('invalid quantities never silently become zero or floating point', () => {
    for (const input of ['', ' ', 'abc', 'NaN', 'Infinity', '1e3', '1,2.3', '1 000',
        '12345678901234567', '0.00000000000000001', '0.12345678901234567', 400, null]) {
        const result = normalizeIngredientAmount(input)
        assert.equal(result.value, null, String(input))
        assert.ok(result.error, String(input))
    }
    assert.match(normalizeIngredientAmount('0.00000000000000001').error, /16 decimales/)
    assert.match(normalizeIngredientAmount('12345678901234567').error, /16 dígitos enteros/)
})

test('leaving an amount field autocorrects valid spelling without losing precision', () => {
    for (const [input, expected] of [[' 400,5000000000000000 ', '400.5'],
        ['9999999999999999.1234567890123456', '9999999999999999.1234567890123456'],
        ['0,0000000000000001', '0.0000000000000001']]) {
        const ingredient = {amount: input}
        autocorrectIngredientAmount(ingredient)
        assert.equal(ingredient.amount, expected)
    }
})

test('leaving an invalid amount field preserves the entry for correction', () => {
    for (const input of ['', 'no es una cantidad', '0.00000000000000001', '10000000000000000']) {
        const ingredient = {amount: input}
        autocorrectIngredientAmount(ingredient)
        assert.equal(ingredient.amount, input)
    }
})

test('lossless labels and zero detection handle tiny, maximum and negative quantities', () => {
    assert.equal(ingredientAmountLabel('9999999999999999.1234567890123456'), '9999999999999999,1234567890123456')
    assert.equal(ingredientAmountLabel('0.0000000000000001'), '0,0000000000000001')
    assert.equal(ingredientAmountLabel('400.0000000000000000'), '400')
    assert.equal(ingredientAmountLabel('invalid'), 'Cantidad no válida')
    assert.equal(isZeroIngredientAmount('0.0000'), true)
    assert.equal(isZeroIngredientAmount('0.0000000000000001'), false)
    assert.equal(isZeroIngredientAmount(''), false)
})

test('normalization prepares every ingredient before any caller mutation', () => {
    const ingredients = [{amount: '400,5'}, {amount: 'bad'}]
    const before = structuredClone(ingredients)
    const failed = prepareIngredientAmounts(ingredients)
    assert.equal(failed.changes, null)
    assert.match(failed.error, /ingrediente 2/)
    assert.deepEqual(ingredients, before)
    ingredients[1].amount = '0.0000000000000001'
    const plan = prepareIngredientAmounts(ingredients)
    assert.equal(plan.error, '')
    assert.equal(ingredients[0].amount, '400,5')
    plan.changes.forEach(change => {change.ingredient.amount = change.amount})
    assert.deepEqual(ingredients.map(item => item.amount), ['400.5', '0.0000000000000001'])
})

test('serving scaling uses exact integer ratios and preserves every supported digit', () => {
    const ingredients = [{amount: '400.5000000000000001'}, {amount: '0.0000000000000001'}, {amount: '-1.5'}]
    const result = prepareScaledIngredientAmounts(ingredients, 3, 6)
    assert.equal(result.error, '')
    assert.deepEqual(result.changes.map(change => change.amount), ['801.0000000000000002', '0.0000000000000002', '-3'])
    assert.deepEqual(ingredients.map(item => item.amount), ['400.5000000000000001', '0.0000000000000001', '-1.5'])
    assert.equal(prepareScaledIngredientAmounts([{amount: '0.3'}], 3, 1).changes[0].amount, '0.1')
    assert.equal(prepareScaledIngredientAmounts([{amount: '9999999999999999.1234567890123456'}], 7, 7).changes[0].amount,
        '9999999999999999.1234567890123456')
})

test('unrepresentable or overflowing scaling rejects the entire recipe without mutation', () => {
    for (const [amounts, oldServings, newServings, message] of [
        [['2', '0.0000000000000001'], 2, 1, /16 decimales/],
        [['2', '1'], 3, 1, /16 decimales/],
        [['2', '9999999999999999.1234567890123456'], 1, 2, /16 dígitos enteros/],
        [['2', 'bad'], 1, 2, /ingrediente 2/],
        [['2'], 0, 2, /raciones/], [['2'], 1, 1.5, /raciones/],
        [['2'], 1, 2147483648, /raciones/],
    ]) {
        const ingredients = amounts.map(amount => ({amount}))
        const before = structuredClone(ingredients)
        const result = prepareScaledIngredientAmounts(ingredients, oldServings, newServings)
        assert.equal(result.changes, null)
        assert.match(result.error, message)
        assert.deepEqual(ingredients, before)
    }
})

test('merged overview adds decimal strings instead of concatenating or rounding', () => {
    assert.equal(sumIngredientAmounts('400.5000000000000001', '0.0000000000000001'), '400.5000000000000002')
    assert.equal(sumIngredientAmounts('0.1', '0.2'), '0.3')
    assert.equal(sumIngredientAmounts('-1', '1'), '0')
    assert.equal(sumIngredientAmounts('9999999999999999', '1'), '10000000000000000')
})

function recipeEditorScale(recipe) {
    const editor = readFileSync(new URL('../components/model_editors/RecipeEditor.vue', import.meta.url), 'utf8')
    const body = editor.match(/function scaleRecipe\(targetServings: number\) \{[\s\S]*?\n\}/)?.[0]
    assert.ok(body, 'the real recipe editor scaling function must exist')
    const emitted = ts.transpileModule(body, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText
    const quantityError = {value: 'previous error'}
    const errors = []
    const scale = Function('editingObj', 'prepareScaledIngredientAmounts', 'quantityError', 'showQuantityError',
        `${emitted}; return scaleRecipe`)(
        {value: recipe}, prepareScaledIngredientAmounts, quantityError, error => errors.push(error))
    return {scale, errors, quantityError}
}

test('actual recipe editor scaling keeps a maximum quantity when the servings stay unchanged', () => {
    const amount = '9999999999999999.1234567890123456'
    const recipe = {servings: 7, steps: [{ingredients: [{amount}]}]}
    const editor = recipeEditorScale(recipe)
    editor.scale(7)
    assert.equal(recipe.steps[0].ingredients[0].amount, amount)
    assert.equal(recipe.servings, 7)
    assert.deepEqual(editor.errors, [])
    assert.equal(editor.quantityError.value, '')
})

test('actual recipe editor rejects an overflowing later ingredient without changing earlier steps or servings', () => {
    const recipe = {servings: 1, steps: [{ingredients: [{amount: '400.5'}]},
        {ingredients: [{amount: '9999999999999999.1234567890123456'}]}]}
    const before = structuredClone(recipe)
    const editor = recipeEditorScale(recipe)
    editor.scale(2)
    assert.deepEqual(recipe, before)
    assert.equal(editor.errors.length, 1)
    assert.match(editor.errors[0], /16 dígitos enteros.*conserva sus cantidades/)
})

function recipeEditorSave(recipe) {
    const editor = readFileSync(new URL('../components/model_editors/RecipeEditor.vue', import.meta.url), 'utf8')
    const body = editor.match(/async function saveObject\(\): Promise<Recipe \| undefined> \{[\s\S]*?\n\}/)?.[0]
    assert.ok(body, 'the real recipe editor save function must exist')
    const emitted = ts.transpileModule(body, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText
    const quantityError = {value: 'previous error'}
    const errors = []
    const saves = []
    const save = Function('editingObj', 'prepareIngredientAmounts', 'quantityError', 'showQuantityError',
        'saveObjectUnchecked', `${emitted}; return saveObject`)(
        {value: recipe}, prepareIngredientAmounts, quantityError, error => errors.push(error),
        async () => {saves.push(structuredClone(recipe)); return recipe})
    return {save, errors, saves, quantityError}
}

test('actual recipe editor submits normalized decimal strings without numeric conversion', async () => {
    const maximum = '9999999999999999.1234567890123456'
    const recipe = {servings: 1, steps: [{ingredients: [{amount: ' 400,5000000000000001 '}, {amount: maximum},
        {amount: '0.0000000000000001'}]}]}
    const editor = recipeEditorSave(recipe)
    assert.equal(await editor.save(), recipe)
    assert.equal(editor.saves.length, 1)
    assert.deepEqual(editor.saves[0].steps[0].ingredients.map(ingredient => ingredient.amount),
        ['400.5000000000000001', maximum, '0.0000000000000001'])
    assert.deepEqual(editor.errors, [])
    assert.equal(editor.quantityError.value, '')
})

test('actual recipe editor leaves all drafts unchanged and never submits when a later amount is invalid', async () => {
    const recipe = {servings: 1, steps: [{ingredients: [{amount: ' 400,500 '}]},
        {ingredients: [{amount: '0.00000000000000001'}]}]}
    const before = structuredClone(recipe)
    const editor = recipeEditorSave(recipe)
    assert.equal(await editor.save(), undefined)
    assert.deepEqual(recipe, before)
    assert.deepEqual(editor.saves, [])
    assert.equal(editor.errors.length, 1)
    assert.match(editor.errors[0], /ingrediente 2.*16 decimales/)
})

function amountDisplay() {
    const source = readFileSync(new URL('./number_utils.ts', import.meta.url), 'utf8')
        .replace(/^import.*$/gm, '').replace(/^export /gm, '')
    const emitted = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText
    return Function('useUserPreferenceStore', 'ingredientAmountDisplayLabel', 'normalizeIngredientAmount',
        `${emitted}; return calculateFoodAmount`)(
        () => ({userSettings: {ingredientDecimals: 2}}), ingredientAmountDisplayLabel, normalizeIngredientAmount)
}

test('native amount display preserves tiny and maximum strings despite a two-decimal preference', () => {
    const display = amountDisplay()
    assert.equal(display('0.0000000000000001', 1), '0,0000000000000001')
    assert.equal(display('9999999999999999.1234567890123456', 1), '9999999999999999,1234567890123456')
    assert.equal(display('400.5000000000000000', 1), '400,5')
})

test('fraction preference cannot hide or approximate significant string digits', () => {
    const display = amountDisplay()
    for (const amount of ['0.0000000000000001', '9999999999999999.1234567890123456',
        '400.5000000000000001', '0.1234567890123456', '-1.5']) {
        assert.equal(display(amount, 1, true), amount.replace('.', ','))
    }
    assert.equal(display('0.5', 1, true), ' <sup>1</sup>&frasl;<sub>2</sub>')
    assert.equal(display('1.25', 1, true), '1 <sup>1</sup>&frasl;<sub>4</sub>')
})

test('invalid unscaled strings remain explicitly invalid while legacy numeric displays stay compatible', () => {
    const display = amountDisplay()
    for (const amount of ['', 'NaN', 'Infinity', 'invalid']) {
        assert.equal(display(amount, 1), 'Cantidad no válida')
        assert.equal(display(amount, 1, true), 'Cantidad no válida')
    }
    assert.equal(display(400.123456, 1), 400.12)
    assert.equal(display(0.5, 1, true), ' <sup>1</sup>&frasl;<sub>2</sub>')
    assert.equal(display('400.5', 2), 801)
})

test('merged maximum quantities display their exact wider sum while ingredient saves still reject it', () => {
    const aggregate = sumIngredientAmounts('9999999999999999.1234567890123456', '1')
    assert.equal(aggregate, '10000000000000000.1234567890123456')
    const display = amountDisplay()
    assert.equal(display(aggregate, 1), '10000000000000000,1234567890123456')
    assert.equal(display(aggregate, 1, true), '10000000000000000,1234567890123456')
    const ingredients = [{amount: aggregate}]
    assert.equal(prepareIngredientAmounts(ingredients).changes, null)
    assert.match(prepareIngredientAmounts(ingredients).error, /16 dígitos enteros/)
    assert.equal(ingredients[0].amount, aggregate)
})

test('legacy inventory labels omit an absent quantity while keeping food, unit and note', () => {
    const source = readFileSync(new URL('./model_utils.ts', import.meta.url), 'utf8')
        .replace(/^import.*$/gm, '').replace(/^export /gm, '')
    const emitted = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText
    const label = Function(`${emitted}; return ingredientToString`)()
    const names = {food: {name: 'Harina'}, unit: {name: 'kg'}, note: 'Reservado'}
    assert.equal(label(names), 'kg Harina (Reservado)')
    assert.equal(label({...names, amount: undefined}), 'kg Harina (Reservado)')
    assert.equal(label({...names, amount: 0}), 'kg Harina (Reservado)')
    assert.equal(label({...names, amount: 400.5}), '400.5 kg Harina (Reservado)')
    assert.equal(label({...names, amount: '0.0000000000000001'}), '0.0000000000000001 kg Harina (Reservado)')
})
