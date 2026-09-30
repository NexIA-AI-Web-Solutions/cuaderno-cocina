#!/usr/bin/env node
/** Read-only CycloneDX inventory of the installed Vue dependency tree. */

import {createHash} from 'node:crypto'
import {
    existsSync,
    lstatSync,
    readFileSync,
    readdirSync,
    realpathSync,
} from 'node:fs'
import {dirname, isAbsolute, join, relative, resolve} from 'node:path'
import {fileURLToPath, pathToFileURL} from 'node:url'


export class InventoryFailure extends Error {}

const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url))
const DEFAULT_NODE_MODULES = resolve(SCRIPT_DIRECTORY, '..', '..', 'vue3', 'node_modules')

function inside(root, candidate) {
    const path = relative(root, candidate)
    return path === '' || (!path.startsWith('..') && !isAbsolute(path))
}

function secureRealpath(path, root, label) {
    let real
    try {
        real = realpathSync.native(path)
    } catch (error) {
        throw new InventoryFailure(`No se puede resolver ${label}: ${error.message}`)
    }
    if (!inside(root, real)) throw new InventoryFailure(`${label} sale del node_modules autorizado.`)
    return real
}

function directoryEntries(path) {
    try {
        return readdirSync(path, {withFileTypes: true})
            .map(entry => entry.name)
            .sort((left, right) => left < right ? -1 : left > right ? 1 : 0)
    } catch (error) {
        throw new InventoryFailure(`No se puede recorrer ${path}: ${error.message}`)
    }
}

function declaredLicenses(metadata) {
    const value = metadata.license ?? metadata.licenses
    if (value === undefined || value === null) return ['NOASSERTION']
    const values = Array.isArray(value) ? value : [value]
    if (!values.length) throw new InventoryFailure('La licencia declarada está vacía.')
    const result = values.map(license => {
        if (typeof license === 'string' && license.trim()) return license.trim()
        if (license && typeof license === 'object' && !Array.isArray(license)) {
            const text = typeof license.type === 'string' && license.type.trim()
                ? license.type.trim()
                : typeof license.name === 'string' && license.name.trim()
                    ? license.name.trim()
                    : null
            if (text) return text
        }
        throw new InventoryFailure('La licencia declarada tiene un formato desconocido.')
    })
    return [...new Set(result)].sort((left, right) => left < right ? -1 : left > right ? 1 : 0)
}

export function packagePurl(name, version) {
    if (typeof name !== 'string' || !name || name !== name.trim()) {
        throw new InventoryFailure('El paquete no tiene un nombre npm canónico.')
    }
    if (typeof version !== 'string' || !version || version !== version.trim()) {
        throw new InventoryFailure(`El paquete ${name} no tiene versión textual canónica.`)
    }
    const validSegment = value => (
        value
        && value !== '.'
        && value !== '..'
        && !/[\\/\s\u0000-\u001f\u007f]/u.test(value)
    )
    let encodedName
    if (name.startsWith('@')) {
        const parts = name.split('/')
        if (
            parts.length !== 2
            || !parts[0].startsWith('@')
            || !validSegment(parts[0].slice(1))
            || !validSegment(parts[1])
        ) {
            throw new InventoryFailure(`El paquete scoped ${name} no es válido.`)
        }
        encodedName = `${encodeURIComponent(parts[0])}/${encodeURIComponent(parts[1])}`
    } else {
        if (!validSegment(name)) throw new InventoryFailure(`El paquete npm ${name} no es válido.`)
        encodedName = encodeURIComponent(name)
    }
    return `pkg:npm/${encodedName}@${encodeURIComponent(version)}`
}

function packageComponent(packageDirectory, root) {
    const manifestPath = join(packageDirectory, 'package.json')
    if (!existsSync(manifestPath)) {
        throw new InventoryFailure(`El paquete instalado ${packageDirectory} no contiene package.json.`)
    }
    secureRealpath(manifestPath, root, 'package.json')
    let raw
    let metadata
    try {
        raw = readFileSync(manifestPath)
        metadata = JSON.parse(raw.toString('utf8'))
    } catch (error) {
        throw new InventoryFailure(`package.json inválido en ${packageDirectory}: ${error.message}`)
    }
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
        throw new InventoryFailure(`package.json no es un objeto en ${packageDirectory}.`)
    }
    const purl = packagePurl(metadata.name, metadata.version)
    const licenses = declaredLicenses(metadata)
    const sha256 = createHash('sha256').update(raw).digest('hex')
    return {
        type: 'library',
        name: metadata.name,
        version: metadata.version,
        purl,
        licenses: licenses.map(name => ({license: {name}})),
        properties: [
            {name: 'cuaderno:declared_license', value: JSON.stringify(licenses)},
            {name: 'cuaderno:package_json_sha256', value: sha256},
        ],
    }
}

function installedPackageRecords(nodeModulesPath) {
    const requestedRoot = resolve(nodeModulesPath)
    if (!existsSync(requestedRoot) || !lstatSync(requestedRoot).isDirectory()) {
        throw new InventoryFailure('El node_modules de Vue no existe o no es un directorio.')
    }
    const root = realpathSync.native(requestedRoot)
    const visitedNodeModules = new Set()
    const visitedPackages = new Set()
    const records = []

    function scanPackage(candidate) {
        const packageDirectory = secureRealpath(candidate, root, 'paquete instalado')
        if (!lstatSync(packageDirectory).isDirectory()) {
            throw new InventoryFailure(`La entrada ${candidate} no es un directorio de paquete.`)
        }
        if (visitedPackages.has(packageDirectory)) return
        visitedPackages.add(packageDirectory)
        records.push({directory: packageDirectory, component: packageComponent(packageDirectory, root)})
        const nested = join(packageDirectory, 'node_modules')
        if (existsSync(nested)) scanNodeModules(nested)
    }

    function scanScope(candidate) {
        const scopeDirectory = secureRealpath(candidate, root, 'scope npm')
        if (!lstatSync(scopeDirectory).isDirectory()) {
            throw new InventoryFailure(`El scope ${candidate} no es un directorio.`)
        }
        for (const child of directoryEntries(scopeDirectory)) {
            if (!child.startsWith('.')) scanPackage(join(scopeDirectory, child))
        }
    }

    function scanNodeModules(candidate) {
        const modulesDirectory = secureRealpath(candidate, root, 'node_modules anidado')
        if (!lstatSync(modulesDirectory).isDirectory()) {
            throw new InventoryFailure(`${candidate} no es un directorio node_modules.`)
        }
        if (visitedNodeModules.has(modulesDirectory)) return
        visitedNodeModules.add(modulesDirectory)
        for (const name of directoryEntries(modulesDirectory)) {
            if (name.startsWith('.')) continue
            const entry = join(modulesDirectory, name)
            if (name.startsWith('@')) scanScope(entry)
            else scanPackage(entry)
        }
    }

    scanNodeModules(root)
    records.sort((left, right) => {
        const first = `${left.component.purl}\u0000${left.component.properties[1].value}`
        const second = `${right.component.purl}\u0000${right.component.properties[1].value}`
        return first < second ? -1 : first > second ? 1 : 0
    })
    return records
}

export function buildInventoryIndex(nodeModulesPath) {
    return new Map(installedPackageRecords(nodeModulesPath).map(record => [record.directory, record.component]))
}

export function buildInventory(nodeModulesPath) {
    const components = installedPackageRecords(nodeModulesPath).map(record => record.component)
    return {
        bomFormat: 'CycloneDX',
        specVersion: '1.6',
        version: 1,
        metadata: {
            properties: [
                {
                    name: 'cuaderno:inventory_scope',
                    value: 'Installed vue3/node_modules tree, including build and development dependencies.',
                },
                {
                    name: 'cuaderno:image_contents',
                    value: 'This installed-tree inventory is not proof of packages copied into a production image.',
                },
                {
                    name: 'cuaderno:schema_validation',
                    value: 'Official CycloneDX schema validation was not performed by this dependency-free tool.',
                },
            ],
        },
        components,
    }
}

function main() {
    if (process.argv.length !== 2) throw new InventoryFailure('Este comando no acepta rutas ni argumentos externos.')
    const inventory = buildInventory(DEFAULT_NODE_MODULES)
    process.stdout.write(`${JSON.stringify(inventory, null, 2)}\n`)
    process.stderr.write(
        `CUADERNO_FRONTEND_INVENTORY_SCOPE installed_tree_with_build_dev=true image_contents_proven=false schema_validated=false components=${inventory.components.length}\n`,
    )
}

const invokedPath = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : ''
if (import.meta.url === invokedPath) {
    try {
        main()
    } catch (error) {
        const message = error instanceof InventoryFailure ? error.message : 'Fallo inesperado al inventariar node_modules.'
        process.stderr.write(`CUADERNO_FRONTEND_INVENTORY ERROR: ${message}\n`)
        process.exitCode = 1
    }
}
