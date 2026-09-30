/** Rollup/Vite evidence of observed modules and final frontend artifact bytes. */

import {createHash} from 'node:crypto'
import {
    existsSync,
    lstatSync,
    readFileSync,
    readdirSync,
    realpathSync,
    writeFileSync,
} from 'node:fs'
import {dirname, isAbsolute, relative, resolve, sep} from 'node:path'

import {buildInventoryIndex} from './frontend_inventory.mjs'


export class BuildProvenanceFailure extends Error {}

export const BUILD_PROVENANCE_REPORT = 'cuaderno-build-provenance.json'

function compare(left, right) {
    return left < right ? -1 : left > right ? 1 : 0
}

function unixPath(value) {
    return value.split(sep).join('/')
}

function inside(root, candidate) {
    const path = relative(root, candidate)
    return path === '' || (!path.startsWith('..') && !isAbsolute(path))
}

function sha256(value) {
    return createHash('sha256').update(value).digest('hex')
}

function requiredDirectory(value, label) {
    if (typeof value !== 'string' || !value) throw new BuildProvenanceFailure(`${label} no es una ruta.`)
    try {
        const path = realpathSync.native(resolve(value))
        if (!lstatSync(path).isDirectory()) throw new Error('no es un directorio')
        return path
    } catch (error) {
        throw new BuildProvenanceFailure(`No se puede verificar ${label}: ${error.message}`)
    }
}

function outputDirectory(value, projectRoot) {
    if (typeof value !== 'string' || !value) throw new BuildProvenanceFailure('outDir no es una ruta.')
    const requested = resolve(value)
    if (existsSync(requested)) {
        const real = requiredDirectory(requested, 'outDir')
        if (!inside(projectRoot, real)) throw new BuildProvenanceFailure('outDir sale del proyecto autorizado.')
        return real
    }
    let ancestor = requested
    while (!existsSync(ancestor)) {
        const parent = dirname(ancestor)
        if (parent === ancestor) throw new BuildProvenanceFailure('No se puede verificar el ancestro de outDir.')
        ancestor = parent
    }
    const realAncestor = requiredDirectory(ancestor, 'ancestro de outDir')
    const candidate = resolve(realAncestor, relative(ancestor, requested))
    if (!inside(projectRoot, candidate)) throw new BuildProvenanceFailure('outDir sale del proyecto autorizado.')
    return candidate
}

function safeRelativeName(value, label) {
    if (typeof value !== 'string' || !value || /[\u0000-\u001f\u007f]/u.test(value)) {
        throw new BuildProvenanceFailure(`${label} no es textual.`)
    }
    const normalized = value.replaceAll('\\', '/')
    if (normalized.startsWith('/') || /^[A-Za-z]:\//u.test(normalized)
            || normalized.split('/').some(part => part === '..' || part === '')) {
        throw new BuildProvenanceFailure(`${label} sale del output autorizado.`)
    }
    return normalized
}

function sourceBytes(source) {
    if (typeof source === 'string') return Buffer.from(source)
    if (source instanceof Uint8Array) return Buffer.from(source)
    throw new BuildProvenanceFailure('Un asset Rollup no contiene bytes verificables.')
}

function packageIdentity(component) {
    const packageHash = component.properties.find(row => row.name === 'cuaderno:package_json_sha256')?.value
    const licenses = component.properties.find(row => row.name === 'cuaderno:declared_license')?.value
    if (typeof packageHash !== 'string' || typeof licenses !== 'string') {
        throw new BuildProvenanceFailure('El inventario npm no conserva su procedencia esperada.')
    }
    return {
        name: component.name,
        version: component.version,
        purl: component.purl,
        package_json_sha256: packageHash,
        declared_licenses: licenses,
    }
}

function createNormalizer({projectRoot, vueRoot, nodeModulesRoot, packageIndex}) {
    const packageDirectories = [...packageIndex.keys()].sort((left, right) => right.length - left.length)

    function opaque(kind, value) {
        return {kind, id: `${kind}:sha256:${sha256(value)}`}
    }

    function normalizeModuleId(rawId) {
        if (typeof rawId !== 'string' || !rawId || rawId.length > 16384) {
            throw new BuildProvenanceFailure('Rollup produjo un identificador de módulo inválido.')
        }
        if (rawId.startsWith('\u0000')) return opaque('virtual', rawId)
        if (/[\u0000-\u001f\u007f]/u.test(rawId)) {
            throw new BuildProvenanceFailure('Rollup produjo un identificador de módulo con controles.')
        }
        const queryAt = rawId.indexOf('?')
        let pathPart = queryAt === -1 ? rawId : rawId.slice(0, queryAt)
        if (/^\/[A-Za-z]:\//u.test(pathPart)) pathPart = pathPart.slice(1)
        if (!isAbsolute(pathPart)) {
            if (/^(?:file:|[A-Za-z]:[\\/])/u.test(pathPart)) {
                throw new BuildProvenanceFailure('Un módulo no resuelto parece una ruta absoluta no autorizada.')
            }
            return {kind: 'unresolved', id: `unresolved:${rawId}`}
        }
        const requested = resolve(pathPart)
        let real = requested
        if (existsSync(requested)) {
            try {
                real = realpathSync.native(requested)
            } catch (error) {
                throw new BuildProvenanceFailure(`No se puede resolver un módulo Rollup: ${error.message}`)
            }
        }
        if (!inside(projectRoot, real) && !inside(nodeModulesRoot, real)) {
            throw new BuildProvenanceFailure('Un módulo resuelve fuera del proyecto autorizado.')
        }
        const packageDirectory = packageDirectories.find(directory => inside(directory, real))
        const variant = queryAt === -1 ? {} : {variant_sha256: sha256(rawId.slice(queryAt))}
        if (packageDirectory) {
            return {
                kind: 'package',
                id: `package:${packageIndex.get(packageDirectory).purl}/${unixPath(relative(packageDirectory, real))}`,
                package: packageIdentity(packageIndex.get(packageDirectory)),
                ...variant,
            }
        }
        if (inside(vueRoot, real)) {
            return {kind: 'source', id: `vue:${unixPath(relative(vueRoot, real))}`, ...variant}
        }
        return {kind: 'source', id: `project:${unixPath(relative(projectRoot, real))}`, ...variant}
    }

    function normalizeImport(value, outputNames) {
        if (typeof value !== 'string' || !value || value.length > 4096 || /[\u0000-\u001f\u007f]/u.test(value)) {
            throw new BuildProvenanceFailure('Rollup produjo un import externo inválido.')
        }
        if (/^file:/u.test(value)) throw new BuildProvenanceFailure('Un import externo contiene una ruta no autorizada.')
        if (outputNames.has(value)) return `output:${safeRelativeName(value, 'import Rollup')}`
        if (isAbsolute(value) || /^\/[A-Za-z]:\//u.test(value)) return normalizeModuleId(value).id
        return `external:${value}`
    }

    return {normalizeModuleId, normalizeImport}
}

function captureBundle(lane, bundle, normalizer) {
    if (!bundle || typeof bundle !== 'object' || Array.isArray(bundle)) {
        throw new BuildProvenanceFailure('Rollup no entregó un bundle verificable.')
    }
    const outputNames = new Set(Object.keys(bundle))
    for (const output of Object.values(bundle)) {
        if (!output || typeof output !== 'object') throw new BuildProvenanceFailure('Salida Rollup inválida.')
        const fileName = safeRelativeName(output.fileName, 'archivo Rollup')
        if (output.type === 'asset') {
            const bytes = sourceBytes(output.source)
            lane.assets.push({file_name: fileName, bytes: bytes.length, sha256: sha256(bytes)})
            continue
        }
        if (output.type !== 'chunk' || typeof output.code !== 'string'
                || !output.modules || typeof output.modules !== 'object' || Array.isArray(output.modules)) {
            throw new BuildProvenanceFailure('Chunk Rollup inválido.')
        }
        const modules = Object.entries(output.modules).map(([id, rendered]) => ({
            ...normalizer.normalizeModuleId(id),
            rendered_length: Number.isSafeInteger(rendered?.renderedLength) ? rendered.renderedLength : null,
            original_length: Number.isSafeInteger(rendered?.originalLength) ? rendered.originalLength : null,
        })).sort((left, right) => compare(left.id, right.id))
        const imports = [...(output.imports ?? []), ...(output.dynamicImports ?? [])]
            .map(value => normalizer.normalizeImport(value, outputNames))
            .sort(compare)
        lane.externals.push(...imports.filter(value => value.startsWith('external:')))
        lane.unresolved.push(...modules.filter(row => row.kind === 'unresolved').map(row => row.id))
        lane.chunks.push({
            file_name: fileName,
            bytes: Buffer.byteLength(output.code),
            sha256: sha256(output.code),
            is_entry: output.isEntry === true,
            is_dynamic_entry: output.isDynamicEntry === true,
            facade: output.facadeModuleId === null || output.facadeModuleId === undefined
                ? null : normalizer.normalizeModuleId(output.facadeModuleId),
            imports,
            modules,
        })
    }
    lane.assets.sort((left, right) => compare(left.file_name, right.file_name))
    lane.chunks.sort((left, right) => compare(left.file_name, right.file_name))
    lane.externals = [...new Set(lane.externals)].sort(compare)
    lane.unresolved = [...new Set(lane.unresolved)].sort(compare)
}

function validatedFinalOutput(outDir, projectRoot) {
    if (!inside(projectRoot, outDir)) throw new BuildProvenanceFailure('outDir final sale del proyecto autorizado.')
    const parts = relative(projectRoot, outDir).split(sep).filter(Boolean)
    let current = projectRoot
    try {
        for (const part of parts) {
            current = resolve(current, part)
            const metadata = lstatSync(current)
            if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
                throw new BuildProvenanceFailure('La ruta final de outDir contiene un enlace o no es un directorio.')
            }
            const real = realpathSync.native(current)
            if (!inside(projectRoot, real)) {
                throw new BuildProvenanceFailure('La ruta final de outDir sale del proyecto autorizado.')
            }
            current = real
        }
    } catch (error) {
        if (error instanceof BuildProvenanceFailure) throw error
        throw new BuildProvenanceFailure('No se puede revalidar la ruta final de outDir.')
    }
    return current
}

function finalFiles(root) {
    const result = []

    function visit(directory) {
        const entries = readdirSync(directory, {withFileTypes: true})
            .sort((left, right) => compare(left.name, right.name))
        for (const entry of entries) {
            const path = resolve(directory, entry.name)
            const metadata = lstatSync(path)
            if (metadata.isSymbolicLink()) throw new BuildProvenanceFailure('El output final contiene un enlace simbólico.')
            const real = realpathSync.native(path)
            if (!inside(root, real)) throw new BuildProvenanceFailure('Un archivo final sale del output autorizado.')
            if (metadata.isDirectory()) {
                visit(real)
                continue
            }
            if (!metadata.isFile()) throw new BuildProvenanceFailure('El output final contiene una entrada no regular.')
            const fileName = unixPath(relative(root, real))
            if (fileName === BUILD_PROVENANCE_REPORT) continue
            const bytes = readFileSync(real)
            result.push({file_name: fileName, bytes: bytes.length, sha256: sha256(bytes)})
        }
    }

    visit(root)
    return result.sort((left, right) => compare(left.file_name, right.file_name))
}

function emptyLane() {
    return {chunks: [], assets: [], externals: [], unresolved: []}
}

export function createBuildProvenance({projectRoot, vueRoot, nodeModulesRoot, outDir} = {}) {
    const project = requiredDirectory(projectRoot, 'projectRoot')
    const vue = requiredDirectory(vueRoot, 'vueRoot')
    const modules = requiredDirectory(nodeModulesRoot, 'nodeModulesRoot')
    if (!inside(project, vue) || !inside(vue, modules)) {
        throw new BuildProvenanceFailure('Vue/node_modules salen del proyecto autorizado.')
    }
    const output = outputDirectory(outDir, project)
    const packageIndex = buildInventoryIndex(modules)
    const normalizer = createNormalizer({
        projectRoot: project, vueRoot: vue, nodeModulesRoot: modules, packageIndex,
    })
    const rollup = {main: emptyLane(), service_worker: emptyLane()}
    const plugin = (name, lane) => ({
        name,
        generateBundle(_options, bundle) {
            captureBundle(rollup[lane], bundle, normalizer)
        },
    })
    const finalizePlugin = {
        name: 'cuaderno-build-provenance-finalize',
        closeBundle: {
            order: 'post',
            sequential: true,
            handler() {
                const readRoot = validatedFinalOutput(output, project)
                const report = {
                    schema_version: 1,
                    claims: {
                        rollup_graph: 'Observed Rollup module-to-chunk graph for the main and service-worker builds.',
                        final_assets: 'SHA-256 hashes of every regular final output file observed after closeBundle.',
                    },
                    limitations: [
                        'Observed modules are not an exact npm dependency closure because tree-shaking, virtual modules, runtime externals and generated assets have different provenance.',
                        'The installed npm inventory includes build and development packages that may not be shipped.',
                    ],
                    rollup,
                    final_assets: finalFiles(readRoot),
                }
                const writeRoot = validatedFinalOutput(output, project)
                if (writeRoot !== readRoot) {
                    throw new BuildProvenanceFailure('outDir cambió durante la captura de procedencia.')
                }
                writeFileSync(
                    resolve(writeRoot, BUILD_PROVENANCE_REPORT),
                    `${JSON.stringify(report, null, 2)}\n`,
                    'utf8',
                )
            },
        },
    }
    return {
        mainPlugin: plugin('cuaderno-build-provenance-main', 'main'),
        serviceWorkerPlugin: plugin('cuaderno-build-provenance-service-worker', 'service_worker'),
        finalizePlugin,
    }
}
