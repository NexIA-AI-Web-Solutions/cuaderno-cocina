import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./forms.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {decimalInput, apiError, shoppingCheckBody, productionUsage, serviceCovers, yieldBody, productionWarning, serviceBody, confirmedCostLabel} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('Spanish decimals stay strings; empty, invalid and negative quantities fail', () => {
    assert.equal(decimalInput(' 32,50 '), '32.50')
    for (const value of ['', 'abc', '-1', 'NaN', 'Infinity', '1,2,3']) assert.equal(decimalInput(value), null)
    assert.equal(decimalInput('0'), null)
    assert.equal(decimalInput('0', true), '0')
})
test('nested API validation errors and access errors are visible', () => {
    assert.match(apiError(400, {food: {name: ['El nombre es obligatorio.']}}), /El nombre es obligatorio/)
    assert.match(apiError(403, {}), /permiso/)
})
test('shopping autosync updates never require nested food writes', () => {
    assert.deepEqual(shoppingCheckBody(true), {checked: true})
})
test('production lines reject missing quantities instead of adding zero', () => {
    assert.equal(productionUsage('Aceite', ''), null)
    assert.equal(productionUsage('', '3'), null)
    assert.equal(productionUsage('Aceite', '-1'), null)
    assert.deepEqual(productionUsage(' Aceite · L ', '0,40'), {component: 'Aceite · L', quantity: '0.40'})
})
test('service covers require whole people and cannot cancel more than planned', () => {
    assert.equal(serviceCovers('', '0', '0'), null)
    assert.equal(serviceCovers('1.5', '0', '0'), null)
    assert.equal(serviceCovers('4', '1', '6'), null)
    assert.deepEqual(serviceCovers('4', '1', '2'), {base_covers: '4', extra: '1', cancelled: '2'})
})
test('declared yield needs a native unit and a positive decimal quantity', () => {
    assert.equal(yieldBody('', 1), null)
    assert.equal(yieldBody('0', 1), null)
    assert.equal(yieldBody('1', undefined), null)
    assert.deepEqual(yieldBody('1,250', 7), {quantity: '1.250', unit: 7})
})
test('missing yield is an explicit incomplete production warning', () => {
    assert.match(productionWarning('yield_missing'), /incompleta.*rendimiento/)
    assert.match(productionWarning({code: 'yield_missing', recipe_id: 9}), /9/)
    assert.equal(productionWarning('Otro aviso'), 'Otro aviso')
})

test('service body preserves local date and whole positive covers, including DST days', () => {
    assert.deepEqual(serviceBody(' Cena ', '45', '2026-10-25', 9), {
        title: 'Cena', covers: '45', service_date: '2026-10-25', recipe: 9,
    })
    assert.deepEqual(serviceBody('Turno', '1', '2026-03-29'), {
        title: 'Turno', covers: '1', service_date: '2026-03-29',
    })
    for (const covers of ['', '0', '-1', '1.5', '10000', 'true']) assert.equal(serviceBody('Cena', covers, '2026-10-25'), null)
    for (const day of ['', '2026-02-30', '2026-02-29', '25/10/2026', '2026-13-01']) assert.equal(serviceBody('Cena', '1', day), null)
    assert.equal(serviceBody('', '1', '2026-10-25'), null)
    assert.equal(serviceBody('Cena', '1', '2026-10-25', 0), null)
})

test('frozen costs display the backend rounded amount and never unknown as zero', () => {
    assert.equal(confirmedCostLabel({status: 'complete', total: '1.255', display: '1.26'}), '1.26 €')
    assert.equal(confirmedCostLabel({status: 'incomplete', total: null, display: null}), 'incompleto')
    assert.equal(confirmedCostLabel({status: 'invalid', total: '0', display: '0.00'}), 'incompleto')
})
