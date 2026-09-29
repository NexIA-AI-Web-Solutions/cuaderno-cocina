import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
const source = readFileSync(new URL('./inventoryRequests.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {inventoryRequests} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('failed request keeps its key across retry and intervening edits; success starts a new operation', () => {
    const requests = inventoryRequests()
    const payload = {quantity: '2'}
    const key = requests.key('consume:1', payload)
    assert.notEqual(requests.key('consume:1', {quantity: '3'}), key)
    assert.notEqual(requests.key('consume:2', payload), key)
    assert.equal(requests.key('consume:1', {quantity: '2'}), key)
    requests.complete('consume:1', payload)
    assert.notEqual(requests.key('consume:1', payload), key)
})
test('OpenAPI override preserves CSRF, content type, credentials and serialized body', async () => {
    const requests = inventoryRequests()
    const init = {headers: {'X-CSRFToken': 'local-test', 'Content-Type': 'application/json'}, credentials: 'same-origin', body: '{"amount":"2"}', method: 'POST'}
    const result = await requests.override('create', {amount: '2'})({init})
    assert.equal(result.headers.get('X-CSRFToken'), 'local-test')
    assert.equal(result.headers.get('Content-Type'), 'application/json')
    assert.equal(result.headers.get('Idempotency-Key'), requests.key('create', {amount: '2'}))
    assert.equal(result.body, init.body)
    assert.equal(result.credentials, init.credentials)
    assert.equal(init.headers['Idempotency-Key'], undefined)
})
