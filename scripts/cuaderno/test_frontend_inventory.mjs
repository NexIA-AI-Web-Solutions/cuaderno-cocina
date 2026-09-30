import assert from 'node:assert/strict'
import {afterEach, test} from 'node:test'
import {spawnSync} from 'node:child_process'
import {createHash} from 'node:crypto'
import {copyFileSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync} from 'node:fs'
import {join} from 'node:path'
import {tmpdir} from 'node:os'
import {fileURLToPath} from 'node:url'

import {InventoryFailure, buildInventory, packagePurl} from './frontend_inventory.mjs'


const temporaryRoots = []
const INVENTORY_SCRIPT = fileURLToPath(new URL('./frontend_inventory.mjs', import.meta.url))

function fixtureRoot() {
    const root = mkdtempSync(join(tmpdir(), 'cuaderno-frontend-inventory-'))
    temporaryRoots.push(root)
    const modules = join(root, 'node_modules')
    mkdirSync(modules)
    return {root, modules}
}

function packageFixture(directory, metadata) {
    mkdirSync(directory, {recursive: true})
    const raw = `${JSON.stringify(metadata, null, 2)}\n`
    writeFileSync(join(directory, 'package.json'), raw, 'utf8')
    return {raw, sha256: createHash('sha256').update(raw).digest('hex')}
}

afterEach(() => {
    while (temporaryRoots.length) rmSync(temporaryRoots.pop(), {recursive: true, force: true})
})

test('walks normal, scoped and nested installed packages with deterministic sorting', () => {
    const {modules} = fixtureRoot()
    packageFixture(join(modules, 'zeta'), {name: 'zeta', version: '2.0.0', license: 'MIT'})
    const scoped = packageFixture(
        join(modules, '@scope', 'alpha'),
        {name: '@scope/alpha', version: '1.0.0', license: {type: 'Apache-2.0', url: 'https://example.invalid/license'}},
    )
    packageFixture(
        join(modules, '@scope', 'alpha', 'node_modules', 'nested'),
        {name: 'nested', version: '3.1.4', license: ['BSD-2-Clause', {type: 'ISC'}]},
    )

    const first = buildInventory(modules)
    const second = buildInventory(modules)

    assert.deepEqual(second, first)
    assert.deepEqual(first.components.map(component => component.name), ['@scope/alpha', 'nested', 'zeta'])
    assert.equal(first.components[0].purl, 'pkg:npm/%40scope/alpha@1.0.0')
    assert.deepEqual(first.components[0].licenses, [{license: {name: 'Apache-2.0'}}])
    assert.equal(
        first.components[0].properties.find(property => property.name === 'cuaderno:package_json_sha256').value,
        scoped.sha256,
    )
})

test('deduplicates the same real package reached through an internal symlink', () => {
    const {modules} = fixtureRoot()
    const target = join(modules, 'actual')
    packageFixture(target, {name: 'actual', version: '1.0.0', license: 'MIT'})
    symlinkSync(target, join(modules, 'alias'), 'junction')

    const result = buildInventory(modules)

    assert.equal(result.components.length, 1)
    assert.equal(result.components[0].name, 'actual')
})

test('rejects a package symlink escaping the installed node_modules root', () => {
    const {root, modules} = fixtureRoot()
    const outside = join(root, 'outside-package')
    packageFixture(outside, {name: 'outside', version: '1.0.0', license: 'MIT'})
    symlinkSync(outside, join(modules, 'escape'), 'junction')

    assert.throws(() => buildInventory(modules), InventoryFailure)
})

test('ignores node_modules dot entries and .bin without treating them as packages', () => {
    const {modules} = fixtureRoot()
    packageFixture(join(modules, 'valid'), {name: 'valid', version: '1.0.0', license: 'MIT'})
    mkdirSync(join(modules, '.bin'))
    writeFileSync(join(modules, '.bin', 'tool'), 'not a package', 'utf8')
    mkdirSync(join(modules, '.cache'))
    writeFileSync(join(modules, '.cache', 'broken.json'), '{', 'utf8')

    assert.deepEqual(buildInventory(modules).components.map(component => component.name), ['valid'])
})

test('fails closed for malformed or incomplete package metadata', () => {
    for (const metadata of (
        [
            '{not-json',
            JSON.stringify({version: '1.0.0', license: 'MIT'}),
            JSON.stringify({name: 'missing-version', license: 'MIT'}),
            JSON.stringify({name: 'bad-license', version: '1.0.0', license: {url: 'only-url'}}),
        ]
    )) {
        const {modules} = fixtureRoot()
        const directory = join(modules, 'broken')
        mkdirSync(directory)
        writeFileSync(join(directory, 'package.json'), metadata, 'utf8')
        assert.throws(() => buildInventory(modules), InventoryFailure)
    }
})

test('encodes npm purls without confusing scope separators', () => {
    assert.equal(packagePurl('lodash', '4.17.21'), 'pkg:npm/lodash@4.17.21')
    assert.equal(packagePurl('@scope/a-name', '1.0.0+build'), 'pkg:npm/%40scope/a-name@1.0.0%2Bbuild')
    for (const [name, version] of [
        ['@broken', '1'],
        ['scope/name', '1'],
        ['', '1'],
        ['ok', ''],
        ['space name', '1'],
        ['control\u0007name', '1'],
        ['@scope/a name', '1'],
        ['@scope/control\nname', '1'],
        ['@/name', '1'],
        ['@scope/', '1'],
        ['@scope/../', '1'],
    ]) {
        assert.throws(() => packagePurl(name, version), InventoryFailure)
    }
})

test('emits CycloneDX 1.6 provenance with string properties and an honest installed-tree scope', () => {
    const {modules} = fixtureRoot()
    packageFixture(join(modules, 'pkg'), {name: 'pkg', version: '1.2.3', license: 'MIT'})

    const result = buildInventory(modules)

    assert.equal(result.bomFormat, 'CycloneDX')
    assert.equal(result.specVersion, '1.6')
    assert.equal(result.version, 1)
    assert.match(result.metadata.properties.find(row => row.name === 'cuaderno:inventory_scope').value, /installed/i)
    assert.match(result.metadata.properties.find(row => row.name === 'cuaderno:image_contents').value, /not proof/i)
    assert.match(result.metadata.properties.find(row => row.name === 'cuaderno:schema_validation').value, /not performed/i)
    for (const property of [...result.metadata.properties, ...result.components.flatMap(row => row.properties)]) {
        assert.equal(typeof property.name, 'string')
        assert.equal(typeof property.value, 'string')
    }
})

test('CLI inventories the Docker build layout and rejects caller-controlled paths', () => {
    const fixture = mkdtempSync(join(tmpdir(), 'cuaderno-frontend-cli-'))
    temporaryRoots.push(fixture)
    const buildRoot = join(fixture, 'build')
    const scriptDirectory = join(buildRoot, 'scripts', 'cuaderno')
    const scriptPath = join(scriptDirectory, 'frontend_inventory.mjs')
    const modules = join(buildRoot, 'vue3', 'node_modules')
    mkdirSync(scriptDirectory, {recursive: true})
    mkdirSync(modules, {recursive: true})
    copyFileSync(INVENTORY_SCRIPT, scriptPath)
    packageFixture(join(modules, 'plain'), {name: 'plain', version: '1.0.0', license: 'MIT'})
    packageFixture(
        join(modules, '@scope', 'built'),
        {name: '@scope/built', version: '2.0.0', license: 'Apache-2.0'},
    )

    const completed = spawnSync(process.execPath, [scriptPath], {encoding: 'utf8'})

    assert.equal(completed.status, 0, completed.stderr)
    assert.equal(completed.signal, null)
    const inventory = JSON.parse(completed.stdout)
    assert.equal(inventory.components.length, 2)
    assert.deepEqual(inventory.components.map(component => component.name), ['@scope/built', 'plain'])
    assert.match(completed.stderr, /CUADERNO_FRONTEND_INVENTORY_SCOPE/)
    assert.match(completed.stderr, /installed_tree_with_build_dev=true/)
    assert.match(completed.stderr, /components=2/)

    const rejected = spawnSync(process.execPath, [scriptPath, modules], {encoding: 'utf8'})
    assert.equal(rejected.status, 1)
    assert.equal(rejected.stdout, '')
    assert.match(rejected.stderr, /no acepta rutas ni argumentos externos/i)
})
