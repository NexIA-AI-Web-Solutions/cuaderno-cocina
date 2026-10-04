import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
const js = ts.transpileModule(readFileSync(new URL('./purchasingUi.ts', import.meta.url), 'utf8'),
    {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {purchaseOffers, purchaseOrders, purchaseReceipts} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

const offer = {id: 1, package: 2, supplier: 3, amount: '4.50', currency: 'EUR', valid_from: '2026-10-04T10:00:00Z'}
const order = {id: 4, quantity: '10', received_quantity: '0', unit: 5, supplier_name: 'Mercado', package: 2, price_snapshot: '4.50', currency_snapshot: 'EUR', state: 'ordered'}
const receipt = {id: 6, quantity: '2', movement: 7, reversed_by: null}

test('purchase response boundaries accept complete rows and reject malformed 2xx payloads', () => {
    assert.deepEqual(purchaseOffers([offer]), [offer])
    assert.deepEqual(purchaseOrders({results: [order]}), [order])
    assert.deepEqual(purchaseReceipts([receipt]), [receipt])
    assert.equal(purchaseOffers([{...offer, currency: '€'}]), null)
    assert.equal(purchaseOrders([{...order, received_quantity: -1}]), null)
    assert.equal(purchaseOrders([{...order, state: 'paid'}]), null)
    assert.equal(purchaseReceipts([{...receipt, movement: true}]), null)
    assert.equal(purchaseReceipts([receipt, receipt]), null)
})
