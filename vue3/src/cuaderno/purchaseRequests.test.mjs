import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const compiled = ts.transpileModule(readFileSync(new URL('./inventoryRequests.ts', import.meta.url), 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.ESNext},
}).outputText
const {inventoryRequests} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const panel = readFileSync(new URL('./components/PurchasingPanel.vue', import.meta.url), 'utf8')
const helper = panel.match(/function receiptKey\([^]*?\n}/)[0]
const context = {JSON, crypto, pendingReceipt: {fingerprint: '', key: ''}, receiptRequests: inventoryRequests()}
vm.runInNewContext(ts.transpileModule(helper, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText, context)

test('receipt retry keys distinguish order and quantity, and survive A → B → A', () => {
    const payload = {entry: 1, quantity: '2'}
    const first = context.receiptKey(10, payload)
    assert.notEqual(context.receiptKey(10, {entry: 1, quantity: '3'}), first)
    assert.notEqual(context.receiptKey(11, payload), first)
    assert.equal(context.receiptKey(10, payload), first)
})
