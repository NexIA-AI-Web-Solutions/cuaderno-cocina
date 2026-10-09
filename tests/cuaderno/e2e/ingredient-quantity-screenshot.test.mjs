import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {runInNewContext} from 'node:vm'

let transform
try {
  const {default: ts} = await import('typescript')
  transform = source => ts.transpileModule(source, {compilerOptions: {
    module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
  }}).outputText
} catch {
  const {stripTypeScriptTypes} = await import('node:module')
  transform = source => stripTypeScriptTypes(source, {mode: 'transform'})
}
const source = readFileSync(new URL('./ingredient-quantity-precision.spec.ts', import.meta.url), 'utf8')
const start = source.indexOf('function cardPngDimensionsMatch(')
const end = source.indexOf('function validateDetailGeometry(', start)
assert.ok(start >= 0 && end > start)
const {cardPngDimensionsMatch} = runInNewContext(`${transform(source.slice(start, end))};({cardPngDimensionsMatch})`)

// Actual V6 PNG IHDR dimensions and browser-recorded card bounds. Both ends of
// a fractional card occupy pixels; rounding its size alone loses that origin.
const originals = [
  ['esencial consulta mobile', 356, 321, {x: 17, y: 261.859375, width: 356, height: 319.875}],
  ['esencial consulta maximum', 356, 341, {x: 17, y: 252.484375, width: 356, height: 339.8125}],
  ['esencial cocina tablet', 734, 203, {x: 17, y: 410.796875, width: 734, height: 201.875}],
  ['profesional consulta mobile', 356, 341, {x: 17, y: 251.859375, width: 356, height: 339.8125}],
  ['profesional consulta maximum', 356, 361, {x: 17, y: 242.296875, width: 356, height: 359.75}],
  ['profesional cocina mobile', 356, 385, {x: 17, y: 230.484375, width: 356, height: 383.8125}],
  ['profesional responsable tablet', 734, 247, {x: 17, y: 388.796875, width: 734, height: 245.875}],
  ['integral consulta mobile', 356, 321, {x: 17, y: 261.734375, width: 356, height: 319.875}],
  ['integral cocina mobile', 356, 365, {x: 17, y: 240.484375, width: 356, height: 363.875}],
]
for (const [name, width, height, bounds] of originals) {
  test(`accepts original complete PNG: ${name}`, () => assert.equal(cardPngDimensionsMatch(width, height, bounds), true))
}

test('uses both fractional x and y origins, rather than rounding size', () => {
  assert.equal(cardPngDimensionsMatch(11, 21, {x: 17.875, y: 261.875, width: 9.25, height: 19.25}), true)
})
test('integer card edges have exact integer PNG dimensions', () => {
  assert.equal(cardPngDimensionsMatch(356, 320, {x: 17, y: 262, width: 356, height: 320}), true)
})
test('preserves Playwright epsilon at edges within one thousandth of a pixel', () => {
  assert.equal(cardPngDimensionsMatch(356, 320, {x: 16.9995, y: 261.9995, width: 356.001, height: 320.001}), true)
  assert.equal(cardPngDimensionsMatch(358, 322, {x: 16.998, y: 261.998, width: 356.004, height: 320.004}), true)
})
test('rejects even one pixel of padding or clipping', () => {
  const bounds = {x: 17, y: 262, width: 356, height: 320}
  for (const [width, height] of [[355, 320], [357, 320], [356, 319], [356, 321]]) {
    assert.equal(cardPngDimensionsMatch(width, height, bounds), false)
  }
})
test('rejects a cropped original fractional card even within the former tolerance', () => {
  const [, width, height, bounds] = originals[0]
  assert.equal(cardPngDimensionsMatch(width, height - 1, bounds), false)
})
test('rejects invalid geometry and non-integer or empty PNG dimensions', () => {
  const bounds = {x: 17, y: 262, width: 356, height: 320}
  for (const field of ['x', 'y', 'width', 'height']) {
    for (const value of [NaN, Infinity, -Infinity]) assert.equal(cardPngDimensionsMatch(356, 320, {...bounds, [field]: value}), false)
  }
  for (const field of ['width', 'height']) {
    for (const value of [0, -1]) assert.equal(cardPngDimensionsMatch(356, 320, {...bounds, [field]: value}), false)
  }
  for (const [width, height] of [[0, 320], [356, 0], [356.5, 320], [356, 320.5], [NaN, 320], [356, Infinity]]) {
    assert.equal(cardPngDimensionsMatch(width, height, bounds), false)
  }
})
