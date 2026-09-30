import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./priceImpactUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {priceImpactRequest, priceImpactEnvelope} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

function payload() {
    return {
        recipe_id: 1, package: 2, as_of: '2026-09-30T02:30:00+00:00',
        current_price_id: 12, previous_price_id: 11, affected: true,
        before: {status: 'complete', unrounded: '2.56', per_serving: '0.64', servings: '4', warnings: []},
        after: {status: 'complete', unrounded: '2.80', per_serving: '0.70', servings: '4', warnings: []},
        difference: '0.24', difference_per_serving: '0.06', currency: 'EUR', price_policy: 'net',
    }
}

test('requests preserve exact Spanish servings and validate identifiers', () => {
    assert.equal(priceImpactRequest(1, 2, '4'), '/api/cuaderno/recipes/1/price-impact/?package=2&servings=4')
    assert.equal(priceImpactRequest(1, 2, '0,1000000000000001'), '/api/cuaderno/recipes/1/price-impact/?package=2&servings=0.1000000000000001')
    for (const servings of ['', '0', '-1', '+1', '1e3', 'NaN', '١', '1.00000000000000001', '1'.repeat(17)]) {
        assert.equal(priceImpactRequest(1, 2, servings), null, servings)
    }
    for (const id of [0, -1, 1.5, NaN, Number.MAX_SAFE_INTEGER + 1]) {
        assert.equal(priceImpactRequest(id, 2, '4'), null)
        assert.equal(priceImpactRequest(1, id, '4'), null)
    }
})

test('complete envelopes remain exact strings and match recipe/package/servings', () => {
    const result = priceImpactEnvelope(payload(), 1, 2, '4')
    assert.equal(result?.difference, '0.24')
    assert.equal(result?.after.unrounded, '2.80')
    assert.equal(priceImpactEnvelope(payload(), 3, 2, '4'), null)
    assert.equal(priceImpactEnvelope(payload(), 1, 3, '4'), null)
    assert.equal(priceImpactEnvelope(payload(), 1, 2, '5'), null)
})

test('unknown costs stay null; incomplete comparison is never zero', () => {
    const unknown = payload()
    unknown.previous_price_id = null
    unknown.before = {status: 'incomplete', unrounded: null, per_serving: null, servings: '4', warnings: ['precio_desconocido']}
    unknown.difference = null
    unknown.difference_per_serving = null
    assert.equal(priceImpactEnvelope(unknown, 1, 2, '4')?.difference, null)
    assert.equal(priceImpactEnvelope({...unknown, difference: '0'}, 1, 2, '4'), null)
    assert.equal(priceImpactEnvelope({...payload(), difference: null}, 1, 2, '4'), null)
})

test('reductions allow signed decimal differences, never non-finite or coerced money', () => {
    assert.equal(priceImpactEnvelope({...payload(), difference: '-0.24', difference_per_serving: '-0.06'}, 1, 2, '4')?.difference, '-0.24')
    for (const value of [0.24, false, 'NaN', 'Infinity', '1e2', '١', '+1']) {
        assert.equal(priceImpactEnvelope({...payload(), difference: value}, 1, 2, '4'), null)
    }
    assert.equal(priceImpactEnvelope({...payload(), after: {...payload().after, unrounded: 2.8}}, 1, 2, '4'), null)
})

test('malformed identities, temporal metadata, policy and sheet status fail closed', () => {
    for (const changes of [
        {affected: 'true'}, {current_price_id: false}, {previous_price_id: -1},
        {as_of: 'not-a-date'}, {currency: ''}, {price_policy: 'profit'}, {price_policy: ['net']},
        {after: {...payload().after, status: 'ok'}}, {after: {...payload().after, status: ['complete']}}, {before: null},
        {after: {...payload().after, warnings: [false]}},
    ]) assert.equal(priceImpactEnvelope({...payload(), ...changes}, 1, 2, '4'), null)
})

test('an unused package cannot claim a change: equivalent costs and zero or unknown difference only', () => {
    const unused = {...payload(), affected: false, after: {...payload().before}, difference: '0.00', difference_per_serving: '0'}
    assert.equal(priceImpactEnvelope(unused, 1, 2, '4')?.affected, false)
    assert.equal(priceImpactEnvelope({...payload(), affected: false}, 1, 2, '4'), null)
    assert.equal(priceImpactEnvelope({...unused, difference: '0.24'}, 1, 2, '4'), null)
    assert.equal(priceImpactEnvelope({...unused, after: {...unused.after, per_serving: '0.70'}}, 1, 2, '4'), null)
    const unknown = {status: 'incomplete', unrounded: null, per_serving: null, servings: '4', warnings: ['precio_desconocido']}
    assert.equal(priceImpactEnvelope({...unused, before: unknown, after: {...unknown}, difference: null, difference_per_serving: null}, 1, 2, '4')?.difference, null)
})
