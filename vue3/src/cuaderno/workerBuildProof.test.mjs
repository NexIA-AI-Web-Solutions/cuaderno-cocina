import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import ts from 'typescript'
import {verifyWorkerBuild} from './workerBuildProof.mjs'

function fixture(t, worker, secondLogo = false) {
    const directory = mkdtempSync(join(tmpdir(), 'cuaderno-worker-build-'))
    t.after(() => rmSync(directory, {recursive: true, force: true}))
    mkdirSync(join(directory, 'assets'))
    const logo = readFileSync(new URL('../assets/cuaderno-logo.svg', import.meta.url))
    writeFileSync(join(directory, 'assets/cuaderno-logo-real.svg'), logo)
    if (secondLogo) writeFileSync(join(directory, 'assets/cuaderno-logo-other.svg'), logo)
    writeFileSync(join(directory, 'service-worker.js'), worker)
    return directory
}

test('checks actual injected public logo and its output bytes', t => {
    const directory = fixture(t, 'const entries=[{url:"assets/cuaderno-logo-real.svg",revision:null}].flatMap(x=>[x]);')
    assert.equal(verifyWorkerBuild(directory).precache_entries, 1)
})

test('source-like comment decoys do not prove a real injected manifest', t => {
    const directory = fixture(t, '// [{url:"assets/cuaderno-logo-real.svg",revision:null}]\nconst entries=[];')
    assert.throws(() => verifyWorkerBuild(directory), /Actual injected manifest/)
})

test('rejects eager page bundles and stale logo revisions', t => {
    const eager = fixture(t, 'const entries=[{url:"assets/cuaderno-logo-real.svg",revision:null},{url:"assets/private.js",revision:"old"}];')
    assert.throws(() => verifyWorkerBuild(eager), /eagerly fetch/)
    const stale = fixture(t, 'const entries=[{url:"assets/cuaderno-logo-real.svg",revision:"incorrect"}];')
    assert.throws(() => verifyWorkerBuild(stale), /revision must match/)
})

test('rejects ambiguous output logo selection', t => {
    const directory = fixture(t, 'const entries=[{url:"assets/cuaderno-logo-real.svg",revision:null}];', true)
    assert.throws(() => verifyWorkerBuild(directory), /exactly one/)
})

test('rejects the plugin-generated web manifest even alongside the correct logo', t => {
    const directory = fixture(t, 'const entries=[{url:"assets/cuaderno-logo-real.svg",revision:null},{url:"manifest.webmanifest",revision:"generated"}];')
    assert.throws(() => verifyWorkerBuild(directory), /injected URLs:.*manifest\.webmanifest/)
})

test('VitePWA explicitly leaves the product web manifest to Django', () => {
    const config = readFileSync(new URL('../../vite.config.ts', import.meta.url), 'utf8')
    const ast = ts.createSourceFile('vite.config.ts', config, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
    assert.equal(ast.parseDiagnostics.length, 0)
    const options = []
    const visit = node => {
        if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'VitePWA') options.push(node.arguments[0])
        ts.forEachChild(node, visit)
    }
    visit(ast)
    assert.equal(options.length, 1)
    assert.ok(ts.isObjectLiteralExpression(options[0]))
    const manifest = options[0].properties.filter(ts.isPropertyAssignment).filter(property => property.name.getText(ast) === 'manifest')
    assert.equal(manifest.length, 1, 'The plugin must explicitly disable its default generated web manifest')
    assert.equal(manifest[0].initializer.kind, ts.SyntaxKind.FalseKeyword)
})
