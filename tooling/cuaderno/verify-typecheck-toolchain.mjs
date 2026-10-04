#!/usr/bin/env node
import {createHash} from 'node:crypto'
import {readdir, readFile, lstat} from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const ROOTS = ['typescript', 'vue-tsc']
const SHA256 = /^[0-9a-f]{64}$/

class VerificationError extends Error {}

function fail(message) {
  throw new VerificationError(message)
}

function argumentsFor(argv) {
  const result = {project: null, manifest: null, generate: false}
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index]
    if (value === '--generate') result.generate = true
    else if (value === '--project' && argv[index + 1]) result.project = argv[++index]
    else if (value === '--manifest' && argv[index + 1]) result.manifest = argv[++index]
    else fail(`Argumento desconocido o incompleto: ${value}`)
  }
  if (!result.project || (!result.generate && !result.manifest)) {
    fail('Usa --project y --manifest, o --project --generate.')
  }
  return result
}

async function regularFile(file, label) {
  let metadata
  try {
    metadata = await lstat(file)
  } catch {
    fail(`No se puede leer ${label}.`)
  }
  if (!metadata.isFile() || metadata.isSymbolicLink()) fail(`${label} no es un archivo regular.`)
  return readFile(file)
}

async function jsonFile(file, label) {
  const bytes = await regularFile(file, label)
  try {
    return JSON.parse(bytes.toString('utf8'))
  } catch {
    fail(`${label} no es JSON UTF-8 válido.`)
  }
}

function safePackageName(name) {
  if (typeof name !== 'string' || !/^(?:@[a-z0-9._~-]+\/)?[a-z0-9._~-]+$/i.test(name)) {
    fail(`Nombre de paquete inválido: ${String(name)}`)
  }
  return name
}

async function packageAt(candidate, requestedName, project) {
  const packageDirectory = path.dirname(candidate)
  let metadata
  try {
    metadata = await lstat(packageDirectory)
  } catch {
    return null
  }
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) {
    fail(`El paquete ${requestedName} no es un directorio regular.`)
  }
  const relative = path.relative(project, packageDirectory)
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
    fail(`El paquete ${requestedName} queda fuera del proyecto.`)
  }
  let current = project
  for (const part of relative.split(path.sep)) {
    current = path.join(current, part)
    const directoryMetadata = await lstat(current)
    if (!directoryMetadata.isDirectory() || directoryMetadata.isSymbolicLink()) {
      fail(`La ruta del paquete ${requestedName} contiene un enlace o entrada no regular.`)
    }
  }
  const document = await jsonFile(candidate, `package.json de ${requestedName}`)
  if (document.name !== requestedName || typeof document.version !== 'string' || !document.version) {
    fail(`Identidad o versión inválida para ${requestedName}.`)
  }
  return {directory: packageDirectory, document}
}

async function resolvePackage(name, fromDirectory, project) {
  safePackageName(name)
  let current = path.resolve(fromDirectory)
  const boundary = path.resolve(project)
  while (true) {
    const candidate = path.join(current, 'node_modules', ...name.split('/'), 'package.json')
    const found = await packageAt(candidate, name, boundary)
    if (found) return found
    if (current === boundary || path.dirname(current) === current) break
    current = path.dirname(current)
  }
  fail(`No se puede resolver la dependencia ${name}.`)
}

function dependencyNames(document) {
  const required = new Set()
  for (const field of ['dependencies', 'peerDependencies']) {
    const value = document[field]
    if (value === undefined) continue
    if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${field} inválido en ${document.name}.`)
    for (const name of Object.keys(value)) required.add(safePackageName(name))
  }
  const optional = document.optionalDependencies
  if (optional !== undefined && (!optional || typeof optional !== 'object' || Array.isArray(optional))) {
    fail(`optionalDependencies inválido en ${document.name}.`)
  }
  return {required: [...required].sort(), optional: Object.keys(optional || {}).sort()}
}

function lengthBytes(value) {
  const bytes = Buffer.alloc(8)
  bytes.writeBigUInt64BE(BigInt(value))
  return bytes
}

async function treeHash(packageDirectory) {
  const files = []
  async function visit(directory, relativeDirectory = '') {
    let entries
    try {
      entries = await readdir(directory, {withFileTypes: true})
    } catch {
      fail(`No se puede recorrer ${packageDirectory}.`)
    }
    entries.sort((left, right) => left.name < right.name ? -1 : left.name > right.name ? 1 : 0)
    for (const entry of entries) {
      const absolute = path.join(directory, entry.name)
      const relative = relativeDirectory ? `${relativeDirectory}/${entry.name}` : entry.name
      const metadata = await lstat(absolute)
      if (metadata.isSymbolicLink()) fail(`Enlace no permitido en ${relative}.`)
      if (entry.name === 'node_modules' && !entry.isDirectory()) {
        fail(`node_modules anidado no es un directorio regular en ${relative}.`)
      }
      if (entry.isDirectory()) {
        if (entry.name !== 'node_modules') await visit(absolute, relative)
      } else if (entry.isFile()) {
        files.push({absolute, relative})
      } else {
        fail(`Entrada no regular en ${relative}.`)
      }
    }
  }
  await visit(packageDirectory)
  files.sort((left, right) => left.relative < right.relative ? -1 : left.relative > right.relative ? 1 : 0)
  const digest = createHash('sha256')
  for (const file of files) {
    const name = Buffer.from(file.relative, 'utf8')
    const bytes = await regularFile(file.absolute, file.relative)
    digest.update(lengthBytes(name.length)).update(name).update(lengthBytes(bytes.length)).update(bytes)
  }
  return {files: files.length, sha256: digest.digest('hex')}
}

async function closure(project) {
  const queue = []
  for (const root of ROOTS) queue.push(await resolvePackage(root, project, project))
  const packages = new Map()
  while (queue.length) {
    const current = queue.shift()
    const relative = path.relative(project, current.directory).split(path.sep).join('/')
    if (!relative.startsWith('node_modules/') || relative.includes('/../') || relative === 'node_modules') {
      fail(`Paquete resuelto fuera de node_modules: ${current.document.name}.`)
    }
    if (packages.has(relative)) continue
    packages.set(relative, current)
    const dependencies = dependencyNames(current.document)
    for (const name of dependencies.required) {
      queue.push(await resolvePackage(name, current.directory, project))
    }
    for (const name of dependencies.optional) {
      try {
        queue.push(await resolvePackage(name, current.directory, project))
      } catch (error) {
        if (!(error instanceof VerificationError) || !error.message.startsWith('No se puede resolver')) throw error
      }
    }
  }
  const rows = []
  for (const [relative, current] of [...packages.entries()].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) {
    rows.push({
      name: current.document.name,
      version: current.document.version,
      path: relative,
      ...await treeHash(current.directory),
    })
  }
  return rows
}

async function lockRecord(project) {
  const relative = 'yarn.lock'
  const bytes = await regularFile(path.join(project, relative), relative)
  return {path: relative, sha256: createHash('sha256').update(bytes).digest('hex')}
}

async function generatedManifest(project) {
  return {
    schema_version: 1,
    lockfile: await lockRecord(project),
    roots: ROOTS,
    packages: await closure(project),
  }
}

function validateManifest(document) {
  if (!document || typeof document !== 'object' || Array.isArray(document)
      || document.schema_version !== 1
      || JSON.stringify(document.roots) !== JSON.stringify(ROOTS)
      || !document.lockfile || document.lockfile.path !== 'yarn.lock'
      || !SHA256.test(document.lockfile.sha256)
      || !Array.isArray(document.packages) || document.packages.length === 0) {
    fail('Manifiesto de toolchain inválido.')
  }
  let previous = ''
  for (const row of document.packages) {
    if (!row || typeof row !== 'object' || Array.isArray(row)
        || Object.keys(row).sort().join(',') !== 'files,name,path,sha256,version'
        || safePackageName(row.name) !== row.name || typeof row.version !== 'string' || !row.version
        || typeof row.path !== 'string' || !row.path.startsWith('node_modules/')
        || !isPositiveInteger(row.files) || !SHA256.test(row.sha256)
        || row.path <= previous) {
      fail('Fila de paquete inválida o desordenada en el manifiesto.')
    }
    previous = row.path
  }
}

function isPositiveInteger(value) {
  return Number.isSafeInteger(value) && value >= 1
}

async function verify(project, manifestPath) {
  const expected = await jsonFile(manifestPath, 'el manifiesto de toolchain')
  validateManifest(expected)
  const actual = await generatedManifest(project)
  if (JSON.stringify(actual.lockfile) !== JSON.stringify(expected.lockfile)) fail('El hash de yarn.lock no coincide.')
  const identity = rows => rows.map(({name, version, path}) => ({name, version, path}))
  if (JSON.stringify(identity(actual.packages)) !== JSON.stringify(identity(expected.packages))) {
    fail('La clausura resuelta de paquetes o sus versiones no coincide.')
  }
  for (let index = 0; index < actual.packages.length; index += 1) {
    const found = actual.packages[index]
    const wanted = expected.packages[index]
    if (found.files !== wanted.files || found.sha256 !== wanted.sha256) {
      fail(`Los bytes del paquete ${found.name} no coinciden.`)
    }
  }
  return {status: 'verified', packages: actual.packages.length, lock_sha256: actual.lockfile.sha256}
}

async function main() {
  const args = argumentsFor(process.argv.slice(2))
  const project = path.resolve(args.project)
  if (args.generate) {
    process.stdout.write(`${JSON.stringify(await generatedManifest(project), null, 2)}\n`)
  } else {
    process.stdout.write(`${JSON.stringify(await verify(project, path.resolve(args.manifest)))}\n`)
  }
}

main().catch(error => {
  const message = error instanceof VerificationError ? error.message : 'Fallo inesperado al verificar el toolchain.'
  process.stderr.write(`TYPECHECK TOOLCHAIN ERROR: ${message}\n`)
  process.exitCode = 1
})
