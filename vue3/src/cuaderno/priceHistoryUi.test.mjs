import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./priceHistoryUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {
    editionCurrency, optionalPackagePrice, packageSummaries, priceAmountLabel, priceHistoryEnvelope,
    priceHistoryRequest, priceTimingLabel, priceVersionBody, priceWriteResponse,
} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)


test('price update accepts exact Spanish decimals up to DecimalField 32/16 without floats', () => {
    assert.deepEqual(priceVersionBody(' 1234567890123456,1234567890123456 ', false), {
        body: {amount: '1234567890123456.1234567890123456', explicit_free: false}, error: '',
    })
    for (const value of [
        '', '1'.repeat(17), `1.${'1'.repeat(17)}`, '1,2.3', '.5', '1.', '-1', '+1', '1e2', 'NaN', 'Infinity',
    ]) {
        const result = priceVersionBody(value, false)
        assert.equal(result.body, null, value)
        assert.ok(result.error, value)
    }
})

test('unknown is never zero and the explicit-free checkbox is equivalent only to exact zero', () => {
    assert.match(priceVersionBody('', false).error, /precio|importe/i)
    assert.match(priceVersionBody('0', false).error, /gratis/i)
    assert.match(priceVersionBody('1', true).error, /cero/i)
    assert.deepEqual(priceVersionBody('0,000', true), {
        body: {amount: '0.000', explicit_free: true}, error: '',
    })
    assert.deepEqual(optionalPackagePrice('', false), {
        value: null, explicit_free: false, error: '',
    })
    assert.match(optionalPackagePrice('', true).error, /cero|importe/i)
})

test('a successful price write is trusted only after validating its exact monetary response', () => {
    const requested = {amount: '1.2500', explicit_free: false}
    const response = {id: 9, amount: '1.25', explicit_free: false, valid_from: '2026-09-30T12:00:00+00:00'}
    assert.deepEqual(priceWriteResponse(response, requested), response)
    assert.deepEqual(
        priceWriteResponse({...response, amount: '0.000', explicit_free: true}, {amount: '0', explicit_free: true}),
        {...response, amount: '0.000', explicit_free: true},
    )
    for (const malformed of [
        null,
        {...response, id: '9'},
        {...response, id: 0},
        {...response, amount: 1.25},
        {...response, amount: '1,25'},
        {...response, amount: ' 1.25 '},
        {...response, amount: '1e0'},
        {...response, explicit_free: 0},
        {...response, valid_from: 'today'},
        {...response, amount: '1.26'},
        {...response, explicit_free: true},
    ]) assert.equal(priceWriteResponse(malformed, requested), null)
})

test('space currency is strict and never silently replaced by EUR', () => {
    assert.equal(editionCurrency({edition: 'professional', currency: 'USD'}), 'USD')
    for (const value of [null, {}, {currency: 'eur'}, {currency: 'EURO'}, {currency: 978}, {currency: true}]) {
        assert.equal(editionCurrency(value), null)
    }
})

const item = {
    id: 11,
    amount: '32.0000000000000000',
    explicit_free: false,
    valid_from: '2026-09-30T10:00:00+00:00',
    created_at: '2026-09-30T10:01:00+00:00',
    created_by: 7,
    note: 'Proveedor local',
    is_current: true,
}

const envelope = {
    package: 3,
    currency: 'EUR',
    as_of: '2026-09-30T11:00:00+00:00',
    current_price_id: 11,
    count: 21,
    next_offset: 20,
    items: [item, ...Array.from({length: 19}, (_, index) => ({
        ...item, id: 12 + index, is_current: false,
    }))],
}

test('history envelope validates strict paging while current price remains global', () => {
    assert.deepEqual(priceHistoryEnvelope(envelope, 3, 0), envelope)
    const secondPage = {
        ...envelope,
        next_offset: null,
        items: [{...item, id: 99, is_current: false}],
    }
    assert.notEqual(priceHistoryEnvelope(secondPage, 3, 20), null)
    assert.equal(priceHistoryEnvelope({...secondPage, current_price_id: 99}, 3, 20), null)
    assert.equal(priceHistoryEnvelope({...envelope, next_offset: 19}, 3, 0), null)
    assert.equal(priceHistoryEnvelope({...envelope, count: 19}, 3, 0), null)
    assert.equal(priceHistoryEnvelope({...envelope, items: [item, item]}, 3, 0), null)
})

test('history rejects floats, malformed decimals, booleans and inconsistent current markers', () => {
    for (const amount of [32, '', 'NaN', '1e2', '-1', '12345678901234567', `1.${'1'.repeat(17)}`]) {
        const items = [{...item, amount}, ...envelope.items.slice(1)]
        assert.equal(priceHistoryEnvelope({...envelope, items}, 3, 0), null, String(amount))
    }
    for (const change of [
        {package: true}, {count: '21'}, {next_offset: '20'}, {current_price_id: true}, {currency: ''}, {as_of: 'today'},
    ]) {
        assert.equal(priceHistoryEnvelope({...envelope, ...change}, 3, 0), null)
    }
    const items = [{...item, is_current: false}, ...envelope.items.slice(1)]
    assert.equal(priceHistoryEnvelope({...envelope, items}, 3, 0), null)
    const futureCurrent = [{...item, valid_from: '2026-10-01T00:00:00Z'}, ...envelope.items.slice(1)]
    assert.equal(priceHistoryEnvelope({...envelope, items: futureCurrent}, 3, 0), null)
})

test('requests are bounded and presentation marks future prices without money arithmetic', () => {
    assert.equal(priceHistoryRequest(3, 0), '/api/cuaderno/packages/3/prices/?limit=20&offset=0')
    assert.equal(priceHistoryRequest(3, 40), '/api/cuaderno/packages/3/prices/?limit=20&offset=40')
    assert.equal(priceAmountLabel('1234.5000', 'EUR'), '1234,5000 EUR')
    assert.equal(priceTimingLabel(item, envelope.as_of), 'Actual')
    assert.equal(priceTimingLabel({...item, id: 12, is_current: false, valid_from: '2026-10-01T00:00:00Z'}, envelope.as_of), 'Programado; todavía no actual')
    assert.equal(priceTimingLabel({...item, id: 12, is_current: false}, envelope.as_of), 'Histórico')
})

test('the unpaged package list remains typed without triggering any history request', () => {
    const packages = [{
        id: 3, food: 4, food_name: 'Aceite', unit: 5, unit_name: 'L', label: 'Garrafa',
        quantity: '5.0000000000000000', is_reference: true,
        current_price: {id: 11, amount: '32.0000000000000000', explicit_free: false, valid_from: item.valid_from},
    }]
    assert.deepEqual(packageSummaries(packages), packages)
    assert.equal(packageSummaries({...packages}), null)
    assert.equal(packageSummaries([{...packages[0], quantity: 5}]), null)
    assert.equal(packageSummaries([{
        ...packages[0], current_price: {...packages[0].current_price, amount: '0', explicit_free: false},
    }]), null)
})
