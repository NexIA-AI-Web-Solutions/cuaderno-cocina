import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./stockMinimumUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {stockMinimumBody, replenishmentExcess, minimumScopeLabel, stockMinimumEnvelope, stockMinimumItems, replenishmentEnvelope} = await import(
    `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
)

test('minimum body keeps exact decimal text and accepts Spanish comma', () => {
    assert.deepEqual(stockMinimumBody(3, 4, ' 12,5000 ', null), {
        body: {food: 3, unit: 4, quantity: '12.5000', location: null}, error: '',
    })
    assert.deepEqual(stockMinimumBody(3, 4, '0.1234567890123456', 8), {
        body: {food: 3, unit: 4, quantity: '0.1234567890123456', location: 8}, error: '',
    })
})

test('blank quantity explicitly deletes while invalid numbers never become zero', () => {
    assert.deepEqual(stockMinimumBody(3, 4, ' ', null), {
        body: {food: 3, unit: 4, quantity: null, location: null}, error: '',
    })
    for (const value of ['0', '-1', '+1', '1e3', '1.12345678901234567', '12345678901234567.1', 'NaN', 1.5]) {
        const parsed = stockMinimumBody(3, 4, value, null)
        assert.equal(parsed.body, null, String(value))
        assert.match(parsed.error, /positivo|decimal exacto|16 decimales/i)
    }
})

test('native selectors require positive integer ids and location remains optional', () => {
    for (const [food, unit, location] of [[true, 4, null], [3, '4', null], [3, 4, 0], [3, 4, []]]) {
        assert.equal(stockMinimumBody(food, unit, '1', location).body, null)
    }
})

test('package excess is exact for decimal strings and does not clamp', () => {
    assert.equal(replenishmentExcess('15', '12.5'), '2.5')
    assert.equal(replenishmentExcess('0.3', '0.1'), '0.2')
    assert.equal(replenishmentExcess('1', '1.25'), '-0.25')
    assert.equal(replenishmentExcess(null, '1'), null)
    assert.equal(replenishmentExcess('NaN', '1'), null)
})

test('scope labels distinguish household-wide and location-specific minimums', () => {
    assert.equal(minimumScopeLabel(null), 'Todo el hogar')
    assert.equal(minimumScopeLabel('Despensa'), 'Ubicación: Despensa')
})

test('minimum list reads the contracted edition and items envelope only', () => {
    const row = {
        id: 9, household: 4, food: 3, food_name: 'Arroz', unit: 5, unit_name: 'kg',
        quantity: '2.5', location: 8, location_name: 'Despensa', updated_by: 6,
        updated_at: '2026-09-30T10:00:00+02:00',
    }
    const payload = {
        edition: 'integral', items: [row], household: {id: 4, name: 'Cocina'},
        locations: [{id: 8, name: 'Despensa'}],
    }
    assert.deepEqual(stockMinimumItems(payload), [row])
    assert.deepEqual(stockMinimumEnvelope(payload), payload)
    assert.equal(stockMinimumItems({items: [row]}), null)
    assert.equal(stockMinimumItems({edition: 'integral', items: [row], household: payload.household}), null)
    assert.equal(stockMinimumItems({edition: 'integral', items: [row], locations: payload.locations}), null)
    assert.equal(stockMinimumItems({edition: 'integral', results: [row]}), null)
    assert.equal(stockMinimumItems([row]), null)
})

test('minimum envelope rejects non-integral editions and unsafe or cross-household rows', () => {
    const row = {
        id: 9, household: 4, food: 3, food_name: 'Arroz', unit: 5, unit_name: 'kg',
        quantity: '2.5', location: null, location_name: null, updated_by: 6,
        updated_at: '2026-09-30T10:00:00+02:00',
    }
    const payload = {edition: 'integral', items: [row], household: {id: 4, name: 'Cocina'}, locations: []}
    assert.equal(stockMinimumEnvelope({...payload, edition: 'profesional'}), null)
    assert.equal(stockMinimumEnvelope({...payload, items: [{...row, id: Number.MAX_SAFE_INTEGER + 1}]}), null)
    assert.equal(stockMinimumEnvelope({...payload, items: [{...row, household: 7}]}), null)
    assert.equal(stockMinimumEnvelope({...payload, items: [{...row, food: true}]}), null)
})

test('minimum envelope accepts only canonical positive quantities and complete text fields', () => {
    const row = {
        id: 9, household: 4, food: 3, food_name: 'Arroz', unit: 5, unit_name: 'kg',
        quantity: '2.5', location: null, location_name: null, updated_by: 6,
        updated_at: '2026-09-30T10:00:00+02:00',
    }
    const payload = {edition: 'integral', items: [row], household: {id: 4, name: 'Cocina'}, locations: []}
    for (const quantity of ['0', '-1', '02', '2.0', ' 2', '2,5', '1e2', '0.12345678901234567', 2.5]) {
        assert.equal(stockMinimumEnvelope({...payload, items: [{...row, quantity}]}), null, String(quantity))
    }
    for (const change of [{food_name: null}, {unit_name: 5}, {updated_at: null}, {location_name: 'Despensa'}]) {
        assert.equal(stockMinimumEnvelope({...payload, items: [{...row, ...change}]}), null)
    }
})

test('location minimum must reference and match a location from its own envelope', () => {
    const row = {
        id: 9, household: 4, food: 3, food_name: 'Arroz', unit: 5, unit_name: 'kg',
        quantity: '2.5', location: 8, location_name: 'Despensa', updated_by: 6,
        updated_at: '2026-09-30T10:00:00+02:00',
    }
    const payload = {
        edition: 'integral', items: [row], household: {id: 4, name: 'Cocina'},
        locations: [{id: 8, name: 'Despensa'}],
    }
    assert.deepEqual(stockMinimumEnvelope(payload), payload)
    assert.equal(stockMinimumEnvelope({...payload, locations: []}), null)
    assert.equal(stockMinimumEnvelope({...payload, items: [{...row, location: 10}]}), null)
    assert.equal(stockMinimumEnvelope({...payload, items: [{...row, location_name: 'Otro almacén'}]}), null)
    assert.equal(stockMinimumEnvelope({...payload, items: [{...row, location: null}]}), null)
})

const replenishmentRow = {
    food: 3, unit: 5, required: '2.5', minimum_stock: '1', target_stock: '3.5',
    usable_stock: '0.5', missing: '3', package: 7, packages: '2', purchase_quantity: '4',
    reference_price: '1.25', currency: 'EUR',
    location_shortfalls: [{
        location: 8, location_name: 'Despensa', minimum_stock: '1', usable_stock: '0.25', missing: '0.75',
    }],
}

test('replenishment accepts the real items envelope and typed complete rows', () => {
    assert.deepEqual(replenishmentEnvelope({items: [replenishmentRow]}), {items: [replenishmentRow]})
    assert.deepEqual(replenishmentEnvelope({items: []}), {items: []})
    assert.equal(replenishmentEnvelope({}), null)
    assert.equal(replenishmentEnvelope([]), null)
})

test('replenishment rejects incomplete rows before the panel replaces visible data', () => {
    const {location_shortfalls, ...withoutShortfalls} = replenishmentRow
    assert.equal(replenishmentEnvelope({items: [withoutShortfalls]}), null)
    assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, location_shortfalls: {}}]}), null)
    assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, food: true}]}), null)
    assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, currency: null}]}), null)
})

test('replenishment decimals are canonical exact text and nullable only where contracted', () => {
    for (const [field, value] of [
        ['required', 2.5], ['usable_stock', ' 0.5'], ['missing', '-1'], ['minimum_stock', '1.0'],
        ['packages', '1e2'], ['purchase_quantity', '0,5'], ['reference_price', 'NaN'],
    ]) {
        assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, [field]: value}]}), null, `${field}: ${value}`)
    }
    assert.deepEqual(replenishmentEnvelope({items: [{
        ...replenishmentRow, package: null, packages: null, purchase_quantity: null,
        reference_price: null, minimum_stock: null, target_stock: null,
    }]}), {items: [{
        ...replenishmentRow, package: null, packages: null, purchase_quantity: null,
        reference_price: null, minimum_stock: null, target_stock: null,
    }]})
    const converted = `0.${'3'.repeat(64)}`
    assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, required: converted}]})?.items[0].required, converted)
    const smallConverted = `0.${'0'.repeat(16)}${'3'.repeat(64)}`
    assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, required: smallConverted}]})?.items[0].required, smallConverted)
    const largeConverted = `1${'0'.repeat(100)}`
    assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, required: largeConverted}]})?.items[0].required, largeConverted)
    assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, required: `0.${'3'.repeat(65)}`}]}), null)
    assert.equal(replenishmentEnvelope({items: [{...replenishmentRow, required: `0.${'0'.repeat(1022)}1`}]}), null)
})

test('replenishment validates every location shortfall field', () => {
    for (const change of [
        {location: 0}, {location_name: null}, {minimum_stock: '01'}, {usable_stock: 0.25}, {missing: '-0.1'},
    ]) {
        assert.equal(replenishmentEnvelope({items: [{
            ...replenishmentRow, location_shortfalls: [{...replenishmentRow.location_shortfalls[0], ...change}],
        }]}), null)
    }
})
