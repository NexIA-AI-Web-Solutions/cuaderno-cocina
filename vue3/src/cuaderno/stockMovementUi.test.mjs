import assert from 'node:assert/strict'
import test from 'node:test'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./stockMovementUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {
    canReverseGeneric,
    hasReplacementValuation,
    isPurchaseMovement,
    isServiceProductionMovement,
    replacementValuationLabel,
} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

function movement(overrides = {}) {
    return {id: 7, kind: 'waste', reverses: null, metadata_snapshot: {}, ...overrides}
}

function valuedRow(overrides = {}) {
    return movement({
        metadata_snapshot: {
            valuation: {
                policy: 'replacement_estimate',
                status: 'complete',
                amount: '1.25',
                currency: 'EUR',
                price_policy: 'net',
                input: {quantity: '0.625', unit_id: 1, unit_name: 'kg'},
                ...overrides,
            },
        },
    })
}

test('production consumption and purchase receipts cannot use generic reversal', () => {
    const production = movement({metadata_snapshot: {origin: {type: 'service_plan', id: 31}}})
    const purchase = movement({metadata_snapshot: {origin: {type: 'purchase_order', id: 41}}})

    assert.equal(isServiceProductionMovement(production), true)
    assert.equal(isPurchaseMovement(purchase), true)
    assert.equal(canReverseGeneric(production, [production]), false)
    assert.equal(canReverseGeneric(purchase, [purchase]), false)
    assert.equal(canReverseGeneric(movement(), [movement()]), true)
})

test('reversals, already reversed movements and malformed rows remain unavailable', () => {
    const original = movement()
    assert.equal(canReverseGeneric(movement({kind: 'reversal', reverses: 3}), []), false)
    assert.equal(canReverseGeneric(movement({reverses: '3'}), []), false)
    assert.equal(canReverseGeneric(original, [movement({id: 8, kind: 'reversal', reverses: 7})]), false)
    assert.equal(canReverseGeneric({id: true, metadata_snapshot: {}}, []), false)
    assert.equal(canReverseGeneric(original, null), false)
})

test('replacement estimate preserves the raw decimal string and price policy', () => {
    const precise = valuedRow({amount: '0.0000000000000002'})
    const gross = valuedRow({amount: '12.3400', price_policy: 'gross'})

    assert.equal(hasReplacementValuation(precise), true)
    assert.equal(
        replacementValuationLabel(precise),
        'Coste de reposición estimado: 0.0000000000000002 EUR (precio neto).',
    )
    assert.equal(
        replacementValuationLabel(gross),
        'Coste de reposición estimado: 12.3400 EUR (precio bruto).',
    )
})

test('explicit zero remains visible while unknown and malformed amounts never become zero', () => {
    assert.equal(
        replacementValuationLabel(valuedRow({amount: '0'})),
        'Coste de reposición estimado: 0 EUR (precio neto).',
    )
    assert.equal(
        replacementValuationLabel(valuedRow({status: 'unknown', amount: null})),
        'Coste de reposición estimado: desconocido.',
    )
    for (const amount of [null, 0, 'NaN', 'Infinity', '1e3', '-1']) {
        assert.equal(
            replacementValuationLabel(valuedRow({amount})),
            'Coste de reposición estimado: desconocido.',
        )
    }
    assert.equal(replacementValuationLabel(movement()), null)
    assert.doesNotMatch(source, /\b(?:Number|parseFloat)\s*\(/)
})
