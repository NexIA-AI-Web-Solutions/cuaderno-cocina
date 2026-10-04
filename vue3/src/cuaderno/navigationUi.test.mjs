import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./navigationUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {cuadernoNavigationCapabilities} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('navigation exposes Cuaderno modules only from their contracted edition', () => {
    assert.deepEqual(cuadernoNavigationCapabilities({edition: 'esencial'}), {
        edition: 'esencial', prices: true, production: false, warehouse: false,
    })
    assert.deepEqual(cuadernoNavigationCapabilities({edition: 'profesional'}), {
        edition: 'profesional', prices: true, production: true, warehouse: false,
    })
    assert.deepEqual(cuadernoNavigationCapabilities({edition: 'integral'}), {
        edition: 'integral', prices: true, production: true, warehouse: true,
    })
})

test('navigation fails closed for missing and malformed edition responses', () => {
    for (const value of [null, {}, {edition: 'enterprise'}, {edition: true}]) {
        assert.deepEqual(cuadernoNavigationCapabilities(value), {
            edition: null, prices: false, production: false, warehouse: false,
        })
    }
})
