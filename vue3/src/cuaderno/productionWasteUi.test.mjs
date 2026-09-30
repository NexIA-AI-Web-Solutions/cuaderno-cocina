import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./productionWasteUi.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const helper = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const exact = '9'.repeat(32) + '.' + '1'.repeat(32)
function document(overrides = {}) {
    return {
        schema_version: 1,
        policy: 'declared_yield_estimate',
        classification_only: true,
        included_in_gross_needs: true,
        additional_stock_movement: false,
        coverage: 'declared_yields_only',
        status: 'declared',
        recorded_by: 7,
        recorded_at: '2026-10-25T12:00:00+02:00',
        lines: [{
            ingredient_id: 11,
            food_id: 12,
            food_name: 'Aceite',
            unit_id: 13,
            unit_name: 'L',
            quantity_basis: 'net_usable',
            yield_ratio: '0.8',
            purchased_quantity: exact,
            useful_quantity: '4',
            waste_quantity: '1',
            cause: 'declared_yield',
        }],
        ...overrides,
    }
}

test('accepts the complete frozen schema without coercing exact decimal strings', () => {
    const value = document()
    const parsed = helper.productionWasteEnvelope(value)
    assert.deepEqual(parsed, value)
    assert.equal(parsed.lines[0].purchased_quantity, exact)
})

test('accepts an explicit unknown classification without inventing zero loss', () => {
    const value = document({status: 'unknown', lines: []})
    assert.deepEqual(helper.productionWasteEnvelope(value), value)
})

test('rejects unsafe identifiers, flags, labels, decimals and ratios', () => {
    const validLine = document().lines[0]
    const invalid = [
        document({recorded_by: true}),
        document({recorded_by: 9007199254740992}),
        document({additional_stock_movement: true}),
        document({coverage: 'all_waste'}),
        document({status: 'safe'}),
        document({lines: [{...validLine, ingredient_id: 0}]}),
        document({lines: [{...validLine, food_name: 'Aceite\u0000oculto'}]}),
        document({lines: [{...validLine, unit_name: 'L\ud800'}]}),
        document({lines: [{...validLine, purchased_quantity: '1e3'}]}),
        document({lines: [{...validLine, purchased_quantity: '1'.repeat(65)}]}),
        document({lines: [{...validLine, yield_ratio: '0'}]}),
        document({lines: [{...validLine, yield_ratio: '1.01'}]}),
        document({lines: [{...validLine, useful_quantity: null}]}),
    ]
    for (const value of invalid) assert.equal(helper.productionWasteEnvelope(value), null)
})

test('accepts repeated ingredient traces and paired astral labels but bounds the envelope', () => {
    const line = {...document().lines[0], food_name: 'Aceite 🫒'}
    assert.ok(helper.productionWasteEnvelope(document({lines: [line]})))
    const repeated = {...line, purchased_quantity: '2', useful_quantity: '1.6', waste_quantity: '0.4'}
    assert.deepEqual(helper.productionWasteEnvelope(document({lines: [line, repeated]}))?.lines, [line, repeated])
    assert.equal(helper.productionWasteEnvelope(document({lines: Array(10001).fill(line)})), null)
})
