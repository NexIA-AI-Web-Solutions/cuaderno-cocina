import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

let transform
try {
  const {default: ts} = await import('typescript')
  transform = source => ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
} catch {
  const {stripTypeScriptTypes} = await import('node:module')
  transform = source => stripTypeScriptTypes(source, {mode: 'transform'})
}
const source = transform(readFileSync(new URL('./contracts.ts', import.meta.url), 'utf8'))
  .replace('./auth-state.mjs', new URL('./auth-state.mjs', import.meta.url).href)
const {appPath, editions, roles, widths} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
const base = 'https://127.0.0.1:18443/cuaderno-cocina/'

test('E2E paths preserve query/hash, recognize existing prefix and reject escape', () => {
  assert.equal(appPath('/api/x?q=1#f', base), '/cuaderno-cocina/api/x?q=1#f')
  assert.equal(appPath('/cuaderno-cocina/api/x?q=1#f', base), '/cuaderno-cocina/api/x?q=1#f')
  assert.equal(appPath('/cuaderno-cocina?q=1#f', base), '/cuaderno-cocina?q=1#f')
  assert.equal(appPath('/api/x?q=1#f', 'http://127.0.0.1:18081/'), '/api/x?q=1#f')
  for (const path of ['/../api/x', '/%2e%2e/api/x', '//third.test/api/x', 'https://third.test/api/x']) {
    assert.throws(() => appPath(path, base), /inválida|prefijo/)
  }
})

test('full edition role and responsive matrix remains intact', () => {
  assert.deepEqual(editions, ['esencial', 'profesional', 'integral'])
  assert.deepEqual(roles, ['consulta', 'cocina', 'responsable'])
  assert.deepEqual(widths, [390, 768, 1440])
})
