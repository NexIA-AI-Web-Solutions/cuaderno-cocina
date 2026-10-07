// Check actual post-Workbox bytes, not only source configuration or mock caches.
import assert from 'node:assert/strict'
import {createHash} from 'node:crypto'
import {readFileSync, readdirSync} from 'node:fs'
import {join, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import ts from 'typescript'

export function verifyWorkerBuild(directory) {
    const assets = join(directory, 'assets')
    const logos = readdirSync(assets).filter(name => /^cuaderno-logo-[A-Za-z0-9_-]+\.svg$/.test(name))
    assert.equal(logos.length, 1, 'Build must emit exactly one original Cuaderno logo')
    const logo = readFileSync(join(assets, logos[0]))
    const original = readFileSync(new URL('../assets/cuaderno-logo.svg', import.meta.url))
    assert.equal(logo.toString('utf8'), original.toString('utf8'), 'Emitted logo must preserve our original SVG')
    const worker = readFileSync(join(directory, 'service-worker.js'), 'utf8')
    const ast = ts.createSourceFile('service-worker.js', worker, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS)
    assert.equal(ast.parseDiagnostics.length, 0, 'Built worker must parse as JavaScript')
    const manifests = []
    const string = node => node && ts.isStringLiteralLike(node) ? node.text : undefined
    const visit = node => {
        if (ts.isArrayLiteralExpression(node)) {
            const entries = node.elements.map(element => {
                if (!ts.isObjectLiteralExpression(element)) return null
                const fields = Object.fromEntries(element.properties.filter(ts.isPropertyAssignment)
                    .map(property => [string(property.name) ?? (ts.isIdentifier(property.name) ? property.name.text : ''), property.initializer]))
                if (string(fields.url) === undefined || fields.revision === undefined) return null
                return {url: string(fields.url), revision: string(fields.revision), noRevision: fields.revision.kind === ts.SyntaxKind.NullKeyword}
            })
            if (entries.some(entry => entry?.url === 'assets/' + logos[0])) manifests.push(entries)
        }
        ts.forEachChild(node, visit)
    }
    visit(ast)
    assert.equal(manifests.length, 1, 'Actual injected manifest must contain the emitted logo once')
    assert.equal(manifests[0].length, 1, 'Installation must not eagerly fetch lazy pages or translations')
    const entry = manifests[0][0]
    assert.ok(entry.noRevision || entry.revision === createHash('md5').update(logo).digest('hex'), 'Workbox revision must match emitted bytes')
    return {passed: true, precache_entries: 1, logo: entry.url,
        logo_sha256: createHash('sha256').update(logo).digest('hex'),
        worker_sha256: createHash('sha256').update(worker).digest('hex')}
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const directory = process.argv[2] ?? fileURLToPath(new URL('../../../cookbook/static/vue3/', import.meta.url))
    console.log(JSON.stringify(verifyWorkerBuild(directory)))
}
