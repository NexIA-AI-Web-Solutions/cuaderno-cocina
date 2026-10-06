import {chromium, type FullConfig} from '@playwright/test'
import {chmod, mkdir} from 'node:fs/promises'
import {appPath, authFile, editions, roles} from './contracts.js'
import {authDirectory, saveAuthState, validAuthState} from './auth-state.mjs'

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL
  if (typeof baseURL !== 'string') throw new Error('BASE_URL no está configurada.')
  await mkdir(authDirectory(baseURL), {recursive: true, mode: 0o700})

  const identities = editions.flatMap(edition => roles.map(role => ({edition, role})))
  const missing: typeof identities = []
  for (const identity of identities) {
    if (!(await validAuthState(authFile(identity.edition, identity.role), baseURL, identity))) missing.push(identity)
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
      const context = await browser.newContext({baseURL, ignoreHTTPSErrors: process.env.CUADERNO_E2E_SELF_SIGNED === '1'})
      const page = await context.newPage()
      await page.goto(appPath('/accounts/login/'))
      await page.locator('input[name="login"], input[name="username"]').first().fill(`demo-${identity.edition}-${identity.role}`)
      await page.locator('input[name="password"]').fill(password)
      await Promise.all([
        page.waitForURL(url => !url.pathname.includes('/accounts/login/')),
        page.locator('button[type="submit"], input[type="submit"]').first().click(),
      ])
      const stateFile = authFile(identity.edition, identity.role)
      await saveAuthState(stateFile, await context.storageState(), baseURL, identity)
      await chmod(stateFile, 0o600)
      await context.close()
    }
  } finally {
    await browser.close()
  }
}
