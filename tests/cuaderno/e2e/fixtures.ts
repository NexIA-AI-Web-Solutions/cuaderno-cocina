import {expect, test as base, type Page, type TestInfo} from '@playwright/test'
import {appPath, parseProject, type Identity} from './contracts.js'
import {enterStartPage} from './start-page-ready.js'

type Fixtures = {identity: Identity; cleanPage: Page}

export function collectBrowserFailures(page: Page): () => Promise<void> {
  const failures: string[] = []
  const pendingConsole = new Set<Promise<void>>()
  page.on('pageerror', error => failures.push(`pageerror: ${error.message}`))
  page.on('console', message => {
    if (message.type() !== 'error') return
    const capture = Promise.all(message.args().map(async argument => {
      try {
        const value: unknown = await argument.evaluate(value => {
          if (value instanceof Error) {
            return {name: value.name, message: value.message, stack: value.stack}
          }
          return value
        })
        return typeof value === 'string' ? value : JSON.stringify(value)
      } catch {
        return argument.toString()
      }
    })).then(values => {
      const detail = values.filter(Boolean).join(' ')
      failures.push(`console: ${detail || message.text()}`)
    })
    pendingConsole.add(capture)
    void capture.finally(() => pendingConsole.delete(capture))
  })
  page.on('request', request => {
    const url = new URL(request.url())
    const base = new URL(process.env.BASE_URL || 'http://127.0.0.1:18081')
    const prefix = base.pathname.replace(/\/+$/, '') + '/'
    if (prefix !== '/' && url.origin === base.origin && !url.pathname.startsWith(prefix)) {
      failures.push(`outside application prefix: ${request.method()} ${url.pathname}`)
    }
  })
  page.on('requestfailed', request => {
    const reason = request.failure()?.errorText || 'fallo desconocido'
    if (!reason.includes('ERR_ABORTED')) failures.push(`network: ${request.method()} ${request.url()} (${reason})`)
  })
  page.on('response', response => {
    if (response.status() >= 500) failures.push(`http ${response.status()}: ${response.request().method()} ${response.url()}`)
  })
  return async () => {
    await Promise.allSettled(pendingConsole)
    expect(failures, failures.join('\n')).toEqual([])
  }
}

export const test = base.extend<Fixtures>({
  identity: async ({}, use, testInfo) => use(parseProject(testInfo.project.name)),
  cleanPage: async ({page}, use) => {
    const assertClean = collectBrowserFailures(page)
    await use(page)
    await assertClean()
  },
})

export {expect}

export type ApiResult<T = unknown> = {status: number; body: T; headers: Record<string, string>}

export async function api<T = unknown>(
  page: Page,
  path: string,
  init: {method?: string; body?: unknown; headers?: Record<string, string>} = {},
): Promise<ApiResult<T>> {
  const csrf = await page.evaluate(() => {
    const config = JSON.parse(document.getElementById('django_config')?.textContent || '{}')
    const name = config.csrfCookieName || (location.pathname.startsWith('/cuaderno-cocina/') ? 'cuaderno_csrftoken' : 'csrftoken')
    const cookie = document.cookie.split('; ').find(row => row.startsWith(name + '='))
    return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : ''
  })
  const method = init.method || 'GET'
  // Share the real browser session/cookies while keeping deliberate HTTP error
  // assertions out of its console. UI requests still use the strict collector.
  const response = await page.context().request.fetch(appPath(path), {
    method,
    headers: {
      Accept: 'application/json',
      ...(init.body === undefined ? {} : {'Content-Type': 'application/json'}),
      ...(csrf ? {'X-CSRFToken': csrf} : {}),
      ...(!['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase()) ? {Origin: new URL(page.url()).origin} : {}),
      ...init.headers,
    },
    ...(init.body === undefined ? {} : {data: JSON.stringify(init.body)}),
    failOnStatusCode: false,
  })
  expect(response.status(), `${method} ${path}`).toBeLessThan(500)
  const text = await response.text()
  let body: unknown = text
  try { body = text ? JSON.parse(text) : null } catch { /* preserve diagnostic text */ }
  return {status: response.status(), body: body as T, headers: response.headers()}
}

export function rows(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) return value.filter(item => item !== null && typeof item === 'object') as Record<string, unknown>[]
  if (value !== null && typeof value === 'object' && Array.isArray((value as {results?: unknown}).results)) {
    return (value as {results: unknown[]}).results.filter(item => item !== null && typeof item === 'object') as Record<string, unknown>[]
  }
  throw new Error(`Se esperaba una lista API; recibido: ${JSON.stringify(value).slice(0, 500)}`)
}

export async function enterApp(page: Page): Promise<void> {
  const home = new URL(appPath('/'), process.env.BASE_URL || 'http://127.0.0.1:18081')
  await enterStartPage(page, home.href, async remaining => {
    await expect(page).not.toHaveURL(/\/accounts\/login\//, {timeout: remaining()})
    await expect(page.locator('#app')).toBeVisible({timeout: remaining()})
    const main = page.locator('main')
    // Both markers require the native recipe count to have reached the UI.
    await expect(main.locator(`a.v-btn[href="${appPath('/advanced-search')}"], .v-card:has(.fa-eye-slash)`).first()).toBeVisible({timeout: remaining()})
    // Recipe-count completion can mount scrollers; the optional meal-plan load
    // has its own progress indicator. Neither may be left pending by navigation.
    await expect(main.locator('.v-skeleton-loader, .v-progress-linear')).toHaveCount(0, {timeout: remaining()})
  })
}

export async function assertNoHorizontalOverflow(page: Page, testInfo: TestInfo): Promise<void> {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(overflow.scrollWidth, `desbordamiento horizontal en ${testInfo.project.name}`).toBeLessThanOrEqual(overflow.clientWidth + 1)
}
