import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./exchangeUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {readExchangeFile, exchangeBody} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

test('file boundary rejects oversized, malformed and unrelated JSON without replacing server validation', () => {
    assert.throws(() => readExchangeFile('x'.repeat(2_000_001)), /2 MB/)
    assert.throws(() => readExchangeFile('{bad'), /JSON/)
    assert.throws(() => readExchangeFile('[]'), /Cuaderno/)
    assert.throws(() => readExchangeFile('{"recipes":[],"format":"unknown"}'), /Cuaderno/)
    assert.deepEqual(readExchangeFile('{"format":"cuaderno-recipes-v2","recipes":[]}'), {format: 'cuaderno-recipes-v2', recipes: []})
})

test('confirmation preserves preview document and adds only server digest; never alters IDs or prices', () => {
    const original = {format: 'cuaderno-recipes-v2', recipes: [], catalog: {foods: []}, preview_sha256: 'old', source_space: 42}
    const preview = exchangeBody(original, {foods: {'food:8': 42}})
    assert.equal(preview.preview_sha256, undefined)
    assert.equal(preview.source_space, undefined)
    assert.deepEqual(preview.mapping, {foods: {'food:8': 42}})
    const confirmed = exchangeBody(preview, preview.mapping, 'server-digest')
    assert.deepEqual(confirmed, {...preview, preview_sha256: 'server-digest'})
    assert.equal(original.preview_sha256, 'old')
    assert.equal(original.source_space, 42)
})
