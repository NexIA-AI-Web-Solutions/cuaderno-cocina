import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./ingredientYieldUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {ingredientYieldBody, yieldSummary, quantityBasisLabel} = await import(
    `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
)

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
