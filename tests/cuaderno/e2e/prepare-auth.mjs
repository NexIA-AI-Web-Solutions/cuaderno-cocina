#!/usr/bin/env node
import {chmod, lstat, mkdir, readFile} from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import {pathToFileURL} from 'node:url'
import {chromium} from '@playwright/test'

const editions = ['esencial', 'profesional', 'integral']
const roles = ['consulta', 'cocina', 'responsable']
const identities = editions.flatMap(edition => roles.map(role => ({edition, role})))
const authDirectory = path.join(import.meta.dirname, '.auth')

function authFile({edition, role}) {
  return path.join(authDirectory, `${edition}-${role}.json`)
}

async function validState(file) {
  try {
    const stat = await lstat(file)
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size === 0) return false
    const value = JSON.parse(await readFile(file, 'utf8'))
    return value && typeof value === 'object' && Array.isArray(value.cookies) && Array.isArray(value.origins)
  } catch {
    return false
  }
}

export function argumentsFrom(argv) {
  let baseURL = process.env.BASE_URL || 'http://127.0.0.1:18081'
  let reuse = false
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--reuse') reuse = true
    else if (argv[index] === '--base-url' && argv[index + 1]) baseURL = argv[++index]
    else throw new Error(`Argumento desconocido: ${argv[index]}`)
  }
  const url = new URL(baseURL)
  if (!['127.0.0.1', 'localhost'].includes(url.hostname) || !['http:', 'https:'].includes(url.protocol)) {
    throw new Error('BASE_URL debe ser loopback local.')
  }
  return {baseURL: url.origin, reuse}
}

export async function prepare({baseURL, reuse, password = process.env.CUADERNO_DEMO_PASSWORD}) {
  await mkdir(authDirectory, {recursive: true, mode: 0o700})
  const missing = []
  for (const identity of identities) {
    if (!(await validState(authFile(identity)))) missing.push(identity)
  }
  if (missing.length === 0) return {created: 0, reused: identities.length}
  if (reuse) throw new Error(`Faltan ${missing.length} estados preautenticados; --reuse nunca inicia sesión.`)
  if (!password) throw new Error('Falta CUADERNO_DEMO_PASSWORD para preparar autenticación.')

  const browser = await chromium.launch()
  try {
    for (let index = 0; index < missing.length; index += 1) {
      if (index > 0 && index % 4 === 0) await new Promise(resolve => setTimeout(resolve, 61_000))
      const identity = missing[index]
      const context = await browser.newContext({baseURL})
      try {
        const page = await context.newPage()
        await page.goto('/accounts/login/')
        await page.locator('input[name="login"], input[name="username"]').first()
          .fill(`demo-${identity.edition}-${identity.role}`)
        await page.locator('input[name="password"]').fill(password)
        await Promise.all([
          page.waitForURL(url => !url.pathname.includes('/accounts/login/')),
          page.locator('button[type="submit"], input[type="submit"]').first().click(),
        ])
        const destination = authFile(identity)
        await context.storageState({path: destination})
        await chmod(destination, 0o600)
      } finally {
        await context.close()
      }
    }
  } finally {
    await browser.close()
  }
  return {created: missing.length, reused: identities.length - missing.length}
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const result = await prepare(argumentsFrom(process.argv.slice(2)))
    process.stdout.write(`Authentication states ready: created=${result.created} reused=${result.reused}\n`)
  } catch (error) {
    process.stderr.write(`Authentication setup failed: ${error.message}\n`)
    process.exitCode = 1
  }
}
