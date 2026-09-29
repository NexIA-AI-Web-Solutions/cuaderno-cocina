import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./financeUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {
    financeDecimalInput, financeBody, pricePolicyLabel, financeMoneyLabel,
    financeRatioLabel, financeWarningLabel,
} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('Spanish finance fields remain exact decimal strings; blank is unknown and zero is valid', () => {
    assert.deepEqual(financeDecimalInput(''), {value: null, error: ''})
    assert.deepEqual(financeDecimalInput('   '), {value: null, error: ''})
    assert.deepEqual(financeDecimalInput('0'), {value: '0', error: ''})
    assert.deepEqual(financeDecimalInput(' 0012,3400 '), {value: '0012.3400', error: ''})
})

test('finance fields reject signs, exponents, malformed separators and precision over four', () => {
    for (const value of ['-1', '+1', '1e3', 'NaN', 'Infinity', '1,2,3', '.5', '1.', '1.23456', '1'.repeat(29)]) {
        const parsed = financeDecimalInput(value)
        assert.equal(parsed.value, null, value)
        assert.match(parsed.error, /decimal|decimales/)
    }
})

test('PUT body distinguishes unknown from zero and reports each invalid field', () => {
    assert.deepEqual(financeBody('0', ''), {
        body: {selling_price_per_serving: '0', budget_per_person: null}, errors: {},
    })
    const invalid = financeBody('1.23456', '-2')
    assert.equal(invalid.body, null)
    assert.match(invalid.errors.selling_price_per_serving, /decimales/)
    assert.match(invalid.errors.budget_per_person, /decimal/)
})

test('net and gross labels apply the same policy vocabulary to both form fields', () => {
    assert.equal(pricePolicyLabel('net'), 'neto')
    assert.equal(pricePolicyLabel('gross'), 'bruto')
    assert.equal(pricePolicyLabel('unexpected'), 'política desconocida')
})

test('money uses exact string HALF_UP rounding, including negative values and carry', () => {
    assert.equal(financeMoneyLabel(null), '—')
    assert.equal(financeMoneyLabel('0'), '0,00 €')
    assert.equal(financeMoneyLabel('12345678901234567890.5'), '12.345.678.901.234.567.890,50 €')
    assert.equal(financeMoneyLabel('1.005'), '1,01 €')
    assert.equal(financeMoneyLabel('-1.005'), '-1,01 €')
    assert.equal(financeMoneyLabel('999999999999999999.995'), '1.000.000.000.000.000.000,00 €')
    assert.equal(financeMoneyLabel('0.3333'), '0,33 €') // 1 / 3 represented to the allowed precision.
    assert.equal(financeMoneyLabel('12.3456'), '12,35 €')
    assert.equal(financeMoneyLabel('12.5', 'CHF'), '12,50 CHF')
})

test('ratio indicators preserve unknown and shift the exact decimal string', () => {
    assert.equal(financeRatioLabel(null), '—')
    assert.equal(financeRatioLabel('0.2534'), '25,34 %')
    assert.equal(financeRatioLabel('1'), '100 %')
})

test('finance warnings remain explicit and never call a difference profit', () => {
    assert.match(financeWarningLabel('selling_price_unknown'), /precio de venta/i)
    assert.match(financeWarningLabel('cost_incomplete'), /ingredientes/i)
    assert.match(financeWarningLabel('price_policy_unknown'), /política/i)
    assert.match(financeWarningLabel('currency_unsupported'), /moneda/i)
    assert.equal(financeWarningLabel('Aviso del servidor'), 'Aviso del servidor')
})
