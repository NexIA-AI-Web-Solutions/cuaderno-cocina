import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./ingredientYieldUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {
    ingredientYieldBody, yieldSummary, quantityBasisLabel, ingredientAmountLabel,
    ingredientYieldEnvelope, ingredientYieldSaveEnvelope, withYieldRevision, ingredientYieldConflictMessage,
} = await import(
    `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
)

test('ingredient quantities remove redundant zeros and use the Spanish decimal separator', () => {
    assert.equal(ingredientAmountLabel('400.0000000000000000'), '400')
    assert.equal(ingredientAmountLabel('400.5000'), '400,5')
    assert.equal(ingredientAmountLabel('000400.5000'), '400,5')
    assert.equal(ingredientAmountLabel('-2.5000'), '-2,5')
    assert.equal(ingredientAmountLabel('-0.0000000000000000'), '0')
})

test('ingredient quantity labels preserve every significant digit without rounding', () => {
    assert.equal(ingredientAmountLabel('0.0000000000000001'), '0,0000000000000001')
    assert.equal(ingredientAmountLabel('9999999999999999.1234567890123456'), '9999999999999999,1234567890123456')
    assert.equal(ingredientAmountLabel('-0.0000000000000001'), '-0,0000000000000001')
})

test('invalid ingredient quantities have an explicit label and never become zero', () => {
    for (const value of ['', 'abc', 'NaN', 'Infinity', '1e3', '400,5', '12345678901234567', '0.12345678901234567', 400, null]) {
        assert.equal(ingredientAmountLabel(value), 'Cantidad no válida', String(value))
    }
})

test('net usable quantities require an exact positive ratio and accept Spanish comma', () => {
    assert.deepEqual(ingredientYieldBody(7, 'net_usable', ' 0,8 '), {
        body: {ingredient: 7, quantity_basis: 'net_usable', yield_ratio: '0.8'},
        error: '',
    })
    assert.match(ingredientYieldBody(7, 'net_usable', '').error, /rendimiento/i)
})

test('gross quantities keep an optional yield for waste information without changing the basis', () => {
    assert.deepEqual(ingredientYieldBody(7, 'gross', ''), {
        body: {ingredient: 7, quantity_basis: 'gross', yield_ratio: null},
        error: '',
    })
    assert.deepEqual(ingredientYieldBody(7, 'gross', '1'), {
        body: {ingredient: 7, quantity_basis: 'gross', yield_ratio: '1'},
        error: '',
    })
})

test('ratios enforce 0 < value <= 1, strings only and at most sixteen decimals', () => {
    assert.equal(ingredientYieldBody(7, 'net_usable', '0.1234567890123456').error, '')
    for (const value of ['0', '0.0000000000000000', '0.12345678901234567', '1.0000000000000001', '1.1', '-0.8', '+0.8', '8e-1', 'NaN', 0.8]) {
        assert.match(ingredientYieldBody(7, 'net_usable', value).error, /entre 0 y 1|decimal exacto/i, String(value))
    }
})

test('subrecipes cannot receive a second ingredient yield', () => {
    const parsed = ingredientYieldBody(7, 'net_usable', '0.8', true)
    assert.equal(parsed.body, null)
    assert.match(parsed.error, /subelaboración|doble/i)
})

test('labels and yield summary use exact strings without binary floating point', () => {
    assert.equal(quantityBasisLabel('gross'), 'Cantidad bruta')
    assert.equal(quantityBasisLabel('net_usable'), 'Cantidad neta útil')
    assert.equal(yieldSummary(null), 'Rendimiento no declarado')
    assert.equal(yieldSummary('0.8'), 'Rendimiento 80 % · merma 20 %')
    assert.equal(yieldSummary('0.9999999999999999'), 'Rendimiento 99,99999999999999 % · merma 0,00000000000001 %')
})

const responseIngredient = {
    id: 7, food_name: 'Patata', amount: '2.5', unit: 'kg', quantity_basis: 'net_usable',
    yield_ratio: '0.8', is_subrecipe: false,
}

test('yield response requires a lowercase SHA-256 revision and complete typed ingredients', () => {
    const response = {
        recipe_id: 3, edition: 'profesional', can_edit: true,
        revision: 'a'.repeat(64), ingredients: [responseIngredient],
    }
    assert.deepEqual(ingredientYieldEnvelope(response), response)
    for (const revision of ['a'.repeat(63), 'A'.repeat(64), 'g'.repeat(64), 3, null]) {
        assert.equal(ingredientYieldEnvelope({...response, revision}), null, String(revision))
    }
    for (const ingredient of [
        {...responseIngredient, id: true}, {...responseIngredient, food_name: 4},
        {...responseIngredient, amount: 2.5}, {...responseIngredient, unit: false},
        {...responseIngredient, quantity_basis: 'other'}, {...responseIngredient, yield_ratio: 0.8},
        {...responseIngredient, is_subrecipe: 'false'},
    ]) {
        assert.equal(ingredientYieldEnvelope({...response, ingredients: [ingredient]}), null)
    }
    assert.equal(ingredientYieldEnvelope({...response, can_edit: 1}), null)
    assert.equal(ingredientYieldEnvelope({...response, edition: 'desconocida'}), null)
    assert.equal(ingredientYieldEnvelope({...response, edition: 'esencial', can_edit: true}), null)
    assert.equal(ingredientYieldEnvelope({...response, ingredients: [responseIngredient, responseIngredient]}), null)
})

test('yield response validates fixed decimals and ratio semantics without float arithmetic', () => {
    const response = {
        recipe_id: 3, edition: 'integral', can_edit: true,
        revision: 'b'.repeat(64), ingredients: [responseIngredient],
    }
    assert.notEqual(ingredientYieldEnvelope({...response, ingredients: [{
        ...responseIngredient, amount: '-2.5000', yield_ratio: '0.1234567890123456',
    }]}), null)
    assert.notEqual(ingredientYieldEnvelope({...response, ingredients: [{
        ...responseIngredient, yield_ratio: '1.0000000000000000',
    }]}), null)
    for (const amount of ['', 'NaN', 'Infinity', '1e2', '12345678901234567', '1.12345678901234567', 2.5]) {
        assert.equal(ingredientYieldEnvelope({...response, ingredients: [{...responseIngredient, amount}]}), null, String(amount))
    }
    for (const yield_ratio of [null, '0', '0.0000000000000000', '0.12345678901234567', '1.1', '-0.8', '8e-1', 0.8]) {
        assert.equal(ingredientYieldEnvelope({...response, ingredients: [{...responseIngredient, yield_ratio}]}), null, String(yield_ratio))
    }
    assert.notEqual(ingredientYieldEnvelope({...response, ingredients: [{
        ...responseIngredient, quantity_basis: 'gross', yield_ratio: null,
    }]}), null)
    for (const change of [
        {is_subrecipe: true, quantity_basis: 'net_usable', yield_ratio: '0.8'},
        {is_subrecipe: true, quantity_basis: 'gross', yield_ratio: '0.8'},
    ]) {
        assert.equal(ingredientYieldEnvelope({...response, ingredients: [{...responseIngredient, ...change}]}), null)
    }
    assert.notEqual(ingredientYieldEnvelope({...response, ingredients: [{
        ...responseIngredient, is_subrecipe: true, quantity_basis: 'gross', yield_ratio: null,
    }]}), null)
})

test('write wrapper adds the validated server revision without changing the exact decimal body', () => {
    const source = {ingredient: 7, quantity_basis: 'net_usable', yield_ratio: '0.8000'}
    assert.deepEqual(withYieldRevision(source, '0'.repeat(64)), {
        body: {...source, revision: '0'.repeat(64)}, error: '',
    })
    assert.deepEqual(source, {ingredient: 7, quantity_basis: 'net_usable', yield_ratio: '0.8000'})
    for (const revision of ['', 'f'.repeat(63), 'F'.repeat(64), null]) {
        const result = withYieldRevision(source, revision)
        assert.equal(result.body, null)
        assert.match(result.error, /versión|recargar/i)
    }
})

test('stale revision has a specific conflict message and never implies an automatic retry', () => {
    assert.equal(
        ingredientYieldConflictMessage(409),
        'Otra persona cambió las mermas de esta receta. Conservamos tus cambios; recarga los datos cuando quieras compararlos.',
    )
    assert.equal(ingredientYieldConflictMessage(400), '')
})

test('save response must contain the requested recipe and saved ingredient exactly once', () => {
    const response = {
        recipe_id: 3, edition: 'profesional', can_edit: true,
        revision: 'c'.repeat(64), ingredients: [responseIngredient],
    }
    assert.deepEqual(ingredientYieldSaveEnvelope(response, 3, 7), response)
    assert.equal(ingredientYieldSaveEnvelope({...response, ingredients: []}, 3, 7), null)
    assert.equal(ingredientYieldSaveEnvelope(response, 4, 7), null)
    for (const ingredientId of [0, true, '7', null]) {
        assert.equal(ingredientYieldSaveEnvelope(response, 3, ingredientId), null)
    }
})
