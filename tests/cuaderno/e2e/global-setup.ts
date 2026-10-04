import {chromium, type FullConfig} from '@playwright/test'
import {chmod, mkdir, lstat, readFile} from 'node:fs/promises'
import {authFile, editions, roles} from './contracts.js'

async function isRegularState(file: string): Promise<boolean> {
  try {
    const stat = await lstat(file)
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size === 0) return false
    const value: unknown = JSON.parse(await readFile(file, 'utf8'))
    return value !== null && typeof value === 'object' &&
      Array.isArray((value as {cookies?: unknown}).cookies) &&
      Array.isArray((value as {origins?: unknown}).origins)
  } catch {
    return false
  }
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL
  if (typeof baseURL !== 'string') throw new Error('BASE_URL no está configurada.')
  await mkdir(new URL('./.auth/', import.meta.url), {recursive: true, mode: 0o700})

  const identities = editions.flatMap(edition => roles.map(role => ({edition, role})))
  const missing: typeof identities = []
  for (const identity of identities) {
    if (!(await isRegularState(authFile(identity.edition, identity.role)))) missing.push(identity)
  }
  if (missing.length === 0) return

  const password = process.env.CUADERNO_DEMO_PASSWORD
  if (!password) {
    throw new Error(
      `Faltan ${missing.length} estados de autenticación. Define CUADERNO_DEMO_PASSWORD para crearlos; ` +
      'la contraseña nunca se escribe en los artefactos del proyecto.',
    )
  }

  const browser = await chromium.launch()
  try {
    for (let index = 0; index < missing.length; index += 1) {
      if (index > 0 && index % 4 === 0) await new Promise(resolve => setTimeout(resolve, 61_000))
      const identity = missing[index]!
      const context = await browser.newContext({baseURL})
      const page = await context.newPage()
      await page.goto('/accounts/login/')
      await page.locator('input[name="login"], input[name="username"]').first().fill(`demo-${identity.edition}-${identity.role}`)
      await page.locator('input[name="password"]').fill(password)
      await Promise.all([
        page.waitForURL(url => !url.pathname.includes('/accounts/login/')),
        page.locator('button[type="submit"], input[type="submit"]').first().click(),
      ])
      const stateFile = authFile(identity.edition, identity.role)
      await context.storageState({path: stateFile})
      await chmod(stateFile, 0o600)
      await context.close()
    }
  } finally {
    await browser.close()
  }
}
