import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
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
