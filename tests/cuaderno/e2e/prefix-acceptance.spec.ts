import type {BrowserContext, Page} from '@playwright/test'
import {appPath, fixturePrefix} from './contracts.js'
import {reserveFreshLogin} from './auth-state.mjs'
import {api, assertNoHorizontalOverflow, collectBrowserFailures, enterApp, expect, rows, test} from './fixtures.js'
import {withNativeReadBarrier} from './native-read-barrier.js'

const target = new URL(process.env.BASE_URL || 'http://127.0.0.1:18081')
const scopePath = target.pathname.replace(/\/+$/, '') + '/'
const scopeUrl = target.origin + scopePath
const namespace = `cuaderno-${encodeURIComponent(scopePath)}-`

async function assertUnauthenticated(context: BrowserContext): Promise<void> {
  expect(await context.cookies()).toEqual([])
  const response = await context.request.get(appPath('/api/cuaderno/edition/'), {maxRedirects: 0})
  expect(response.status()).toBe(403)
  expect((await context.cookies(scopeUrl)).some(cookie => cookie.name === 'cuaderno_sessionid')).toBe(false)
}

async function activateWorker(page: Page, script: string): Promise<void> {
  const activated = await page.evaluate(async ({script, scope}) => {
    const current = await navigator.serviceWorker.getRegistration(scope)
    if (current?.scope !== scope || current.active?.scriptURL === script) throw new Error('Se requiere una actualización del registro exacto de Cuaderno.')
    const registration = await navigator.serviceWorker.register(script, {scope, updateViaCache: 'none'})
    const worker = registration.installing || registration.waiting || registration.active
    if (!worker || worker.scriptURL !== script) throw new Error('No se instaló el worker solicitado.')
    if (worker.state !== 'activated') await new Promise<void>((resolve, reject) => {
      const changed = () => {
        if (worker.state === 'activated' || worker.state === 'redundant') {
          worker.removeEventListener('statechange', changed)
          if (worker.state === 'activated') resolve()
          else reject(new Error('La actualización del worker fue descartada.'))
        }
      }
      worker.addEventListener('statechange', changed)
      changed()
    })
    return {scope: registration.scope, script: worker.scriptURL, state: worker.state}
  }, {script, scope: scopeUrl})
  expect(activated).toEqual({scope: scopeUrl, script, state: 'activated'})
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL || '')).toBe(script)
}

async function csrf(page: Page): Promise<string> {
  return page.evaluate(() => {
    const config = JSON.parse(document.getElementById('django_config')!.textContent!)
    const cookie = document.cookie.split(';').map(item => item.trim()).find(item => item.startsWith(config.csrfCookieName + '='))
    if (!cookie) throw new Error('Falta la cookie CSRF configurada por Django.')
    return decodeURIComponent(cookie.slice(cookie.indexOf('=') + 1))
  })
}

async function assertPublicCaches(page: Page): Promise<void> {
  await expect.poll(() => page.evaluate(async prefix => (await caches.keys()).filter(name => name.startsWith(prefix)).length, namespace)).toBeGreaterThan(0)
  const cachesSnapshot = await page.evaluate(async () => {
    const result: Record<string, string[]> = {}
    for (const name of await caches.keys()) result[name] = (await (await caches.open(name)).keys()).map(request => request.url)
    return result
  })
  const ownNames = Object.keys(cachesSnapshot).filter(name => name.startsWith(namespace))
  expect(ownNames.length).toBeGreaterThan(0)
  for (const name of ownNames) for (const source of cachesSnapshot[name]!) {
    const url = new URL(source)
    expect(url.origin, name).toBe(target.origin)
    expect(url.pathname.startsWith(scopePath + 'static/'), `${name}: ${source}`).toBe(true)
    expect(url.searchParams.has('share'), source).toBe(false)
  }
}

// The existing root acceptance baseline remains unchanged. Enabling this suite is
// explicit and requires the isolated prefix proxy and its synthetic fixture DB.
test.describe('despliegue aislado bajo prefijo', () => {
  test.beforeAll(() => {
    expect(process.env.CUADERNO_E2E_PREFIX).toBe('1')
    expect(target.protocol).toBe('https:')
    expect(scopePath).toBe('/cuaderno-cocina/')
    expect(['127.0.0.1', 'localhost']).toContain(target.hostname)
  })

  test('conserva base, assets, API, cookies y recarga profunda en el prefijo', async ({cleanPage, context, identity}, testInfo) => {
    await enterApp(cleanPage)
    const config = await cleanPage.evaluate(() => ({base: document.baseURI,
      config: JSON.parse(document.getElementById('django_config')!.textContent!),
      assets: [...document.querySelectorAll<HTMLScriptElement | HTMLLinkElement>('script[src], link[rel="stylesheet"]')]
        .map(element => element instanceof HTMLScriptElement ? element.src : element.href),
    }))
    expect(config.base).toBe(scopeUrl)
    expect(config.config).toMatchObject({csrfCookieName: 'cuaderno_csrftoken', languageCookieName: 'cuaderno_language',
      languageCookiePath: scopePath, languageCookieSecure: true, mediaUrl: scopePath + 'media/'})
    expect(config.assets.length).toBeGreaterThan(0)
    for (const asset of config.assets) {
      const url = new URL(asset)
      expect(url.origin).toBe(target.origin)
      expect(url.pathname.startsWith(scopePath + 'static/'), asset).toBe(true)
      const response = await context.request.get(asset)
      expect(response.status(), asset).toBe(200)
    }
    const cookies = await context.cookies(scopeUrl)
    for (const name of ['cuaderno_sessionid', 'cuaderno_csrftoken']) {
      const cookie = cookies.find(cookie => cookie.name === name)
      expect(cookie, name).toBeDefined()
      expect(cookie).toMatchObject({path: scopePath, secure: true, httpOnly: name === 'cuaderno_sessionid'})
    }
    expect((await context.cookies(target.origin + '/')).some(cookie => cookie.name.startsWith('cuaderno_'))).toBe(false)
    const health = await context.request.get(appPath('/health/ready/'), {maxRedirects: 0})
    expect(health.status()).toBe(200)
    expect(await health.json()).toEqual({ready: true})
    const edition = await api<{edition: string}>(cleanPage, '/api/cuaderno/edition/')
    expect(edition.status).toBe(200)
    expect(edition.body.edition).toBe(identity.edition)
    const requiredPriceReads = identity.role === 'consulta' ? [] : ['/api/food/', '/api/unit/']
    const pricePageReady = async () => {
      await expect(cleanPage.getByText('Formatos y precios', {exact: true}).first()).toBeVisible()
      await expect(cleanPage.getByRole('button', {name: 'Actualizar lista', exact: true})).toBeEnabled()
      if (identity.role === 'consulta') {
        await expect(cleanPage.getByText('Modo Consulta: puedes revisar formatos, precios e historial, pero no modificarlos.', {exact: true})).toBeVisible()
        await expect(cleanPage.getByRole('button', {name: 'Guardar formato', exact: true})).toHaveCount(0)
      } else {
        await expect(cleanPage.getByRole('button', {name: 'Guardar formato', exact: true})).toBeEnabled()
      }
      // Lazy route content can request fonts after document load. Finish the
      // actual font set before an intentional reload; no canceled read is ignored.
      await cleanPage.evaluate(async () => {await document.fonts.ready})
    }
    await withNativeReadBarrier(cleanPage, async () => {
      await cleanPage.goto(appPath('/cuaderno/precios'))
      await pricePageReady()
    }, requiredPriceReads)
    await withNativeReadBarrier(cleanPage, async () => {
      await cleanPage.reload()
      await pricePageReady()
    }, requiredPriceReads)
    expect(new URL(cleanPage.url()).pathname).toBe(appPath('/cuaderno/precios'))
    await assertNoHorizontalOverflow(cleanPage, testInfo)
  })

  test('instala el manifiesto y limita el worker y sus caches a Cuaderno', async ({cleanPage, context}) => {
    await enterApp(cleanPage)
    const manifestUrl = await cleanPage.locator('link[rel="manifest"]').getAttribute('href')
    expect(manifestUrl).toBe(appPath('/manifest.json'))
    const response = await context.request.get(manifestUrl!)
    expect(response.status()).toBe(200)
    const manifest = await response.json() as {start_url: string; scope: string; share_target: {action: string};
      icons: {src: string}[]; shortcuts: {url: string; icons: {src: string}[]}[]}
    const resolve = (source: string) => new URL(source, target.origin + manifestUrl)
    expect(resolve(manifest.start_url).href).toBe(scopeUrl)
    expect(resolve(manifest.scope).href).toBe(scopeUrl)
    expect(resolve(manifest.share_target.action).pathname).toBe(appPath('/recipe/import'))
    expect(manifest.shortcuts.length).toBeGreaterThan(0)
    expect(manifest.icons.length).toBeGreaterThan(0)
    for (const shortcut of manifest.shortcuts) expect(resolve(shortcut.url).pathname.startsWith(scopePath)).toBe(true)
    for (const icon of [...manifest.icons, ...manifest.shortcuts.flatMap(shortcut => shortcut.icons)]) {
      const url = resolve(icon.src)
      expect(url.origin).toBe(target.origin)
      expect(url.pathname.startsWith(scopePath + 'static/'), icon.src).toBe(true)
      expect((await context.request.get(url.href)).status(), icon.src).toBe(200)
    }
    await expect.poll(() => cleanPage.evaluate(() => navigator.serviceWorker.controller?.scriptURL || '')).toBe(target.origin + appPath('/service-worker.js'))
    const registered = await cleanPage.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).map(registration => registration.scope))
    expect(registered).toEqual([scopeUrl])
    // Exercise installation/activation through real updates, keeping the
    // registration alive. Unregister/reload tests browser uninstall behavior.
    const foreignKey = target.origin + '/foreign-cache-probe'
    await cleanPage.evaluate(async key => {
      await (await caches.open('images')).put(key, new Response('foreign sentinel'))
    }, foreignKey)
    const foreignSentinel = () => cleanPage.evaluate(async key => (await (await caches.open('images')).match(key))?.text(), foreignKey)
    expect(await foreignSentinel()).toBe('foreign sentinel')
    const canonicalScript = target.origin + appPath('/service-worker.js')
    const updateScript = new URL(canonicalScript)
    updateScript.searchParams.set('e2e-activation', crypto.randomUUID())
    await activateWorker(cleanPage, updateScript.href)
    expect(await foreignSentinel()).toBe('foreign sentinel')
    await activateWorker(cleanPage, canonicalScript)
    expect(await foreignSentinel()).toBe('foreign sentinel')
    await cleanPage.reload()
    await expect.poll(() => cleanPage.evaluate(() => navigator.serviceWorker.controller?.scriptURL || '')).toBe(canonicalScript)
    expect(await cleanPage.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).map(registration => ({scope: registration.scope, script: registration.active?.scriptURL})))).toEqual([{scope: scopeUrl, script: canonicalScript}])
    expect(await foreignSentinel()).toBe('foreign sentinel')
    await api(cleanPage, '/api/recipe/?page_size=100')
    await assertPublicCaches(cleanPage)
  })

  test('rechaza CSRF inválido y conserva cookies ajenas al cambiar idioma y cerrar sesión', async ({cleanPage, context, browser, identity}) => {
    await context.addCookies([
      {name: 'sessionid', value: 'foreign-session', domain: target.hostname, path: '/', secure: true, httpOnly: true},
      {name: 'csrftoken', value: 'foreign-csrf', domain: target.hostname, path: '/', secure: true},
      {name: 'django_language', value: 'foreign-language', domain: target.hostname, path: '/', secure: true},
    ])
    await enterApp(cleanPage)
    const list = await api(cleanPage, '/api/shopping-list-entry/?page_size=100')
    const entry = rows(list.body).find(item => JSON.stringify(item).includes(fixturePrefix))
    expect(entry?.id).toBeDefined()
    expect(typeof entry?.updated_at).toBe('string')
    const endpoint = `/api/shopping-list-entry/${entry!.id}/`
    const version = {'If-Match': `"${entry!.updated_at}"`}
    const invalid = await api(cleanPage, endpoint, {method: 'PATCH', body: {checked: entry!.checked}, headers: {...version, 'X-CSRFToken': 'invalid'}})
    expect(invalid.status).toBe(403)
    expect(JSON.stringify(invalid.body)).toMatch(/CSRF/i)
    const valid = await api(cleanPage, endpoint, {method: 'PATCH', body: {checked: entry!.checked}, headers: version})
    expect(valid.status).toBe(200)
    await cleanPage.goto(appPath('/settings/cosmetic'))
    await cleanPage.locator('.language-select .v-field').click()
    await Promise.all([
      cleanPage.waitForNavigation({waitUntil: 'load'}),
      cleanPage.getByRole('option').filter({hasText: /\(en\)/}).first().click(),
    ])
    await expect(cleanPage.locator('html')).toHaveAttribute('lang', 'en')
    await expect(cleanPage.locator('.language-select .v-field')).toBeVisible()
    const language = (await context.cookies(scopeUrl)).find(cookie => cookie.name === 'cuaderno_language')
    expect(language).toMatchObject({value: 'en', path: scopePath, secure: true})
    const foreign = (await context.cookies(target.origin + '/')).filter(cookie => ['sessionid', 'csrftoken', 'django_language'].includes(cookie.name))
    expect(foreign.map(cookie => [cookie.name, cookie.value]).sort()).toEqual([
      ['csrftoken', 'foreign-csrf'], ['django_language', 'foreign-language'], ['sessionid', 'foreign-session'],
    ])
    await assertPublicCaches(cleanPage)
    // The shared authFile session remains available for all later projects.
    // One fresh session per edition/role at width1440 bounds additional logins;
    // all widths still execute CSRF, language, foreign-cookie and cache checks.
    if (identity.width !== 1440) return
    const password = process.env.CUADERNO_DEMO_PASSWORD
    if (!password) throw new Error('Falta CUADERNO_DEMO_PASSWORD para la sesión aislada de login/logout.')
    // Playwright Test injects project defaults into newContext unless overridden.
    const isolated = await browser.newContext({baseURL: scopeUrl, storageState: {cookies: [], origins: []}, ignoreHTTPSErrors: process.env.CUADERNO_E2E_SELF_SIGNED === '1'})
    const freshPage = await isolated.newPage()
    const assertClean = collectBrowserFailures(freshPage)
    try {
      await assertUnauthenticated(isolated)
      await isolated.addCookies([
        {name: 'sessionid', value: 'foreign-session', domain: target.hostname, path: '/', secure: true, httpOnly: true},
        {name: 'csrftoken', value: 'foreign-csrf', domain: target.hostname, path: '/', secure: true},
        {name: 'django_language', value: 'foreign-language', domain: target.hostname, path: '/', secure: true},
      ])
      await freshPage.goto(appPath('/accounts/login/'))
      await freshPage.locator('input[name="login"], input[name="username"]').first().fill(identity.username)
      await freshPage.locator('input[name="password"]').fill(password)
      await reserveFreshLogin(scopeUrl)
      await Promise.all([
        freshPage.waitForURL(url => !url.pathname.includes('/accounts/login/')),
        freshPage.locator('button[type="submit"], input[type="submit"]').first().click(),
      ])
      await enterApp(freshPage)
      const authenticated = await api<{edition: string}>(freshPage, '/api/cuaderno/edition/')
      expect(authenticated.status).toBe(200)
      expect(authenticated.body.edition).toBe(identity.edition)
      const logout = await isolated.request.post(appPath('/accounts/logout/'), {headers: {'X-CSRFToken': await csrf(freshPage), Origin: target.origin}})
      expect(logout.status()).toBe(200)
      expect((await isolated.cookies(scopeUrl)).some(cookie => cookie.name === 'cuaderno_sessionid')).toBe(false)
      const remaining = (await isolated.cookies(target.origin + '/')).filter(cookie => ['sessionid', 'csrftoken', 'django_language'].includes(cookie.name))
      expect(remaining.map(cookie => [cookie.name, cookie.value]).sort()).toEqual([
        ['csrftoken', 'foreign-csrf'], ['django_language', 'foreign-language'], ['sessionid', 'foreign-session'],
      ])
      await freshPage.goto(appPath('/cuaderno/precios'))
      await expect(freshPage).toHaveURL(/\/cuaderno-cocina\/accounts\/login\//)
      await assertPublicCaches(freshPage)
      expect((await api(cleanPage, '/api/cuaderno/edition/')).status).toBe(200)
    } finally {
      try { await assertClean() } finally { await isolated.close() }
    }
  })

  test('sube imagen privada y limita su descarga compartida a la receta autorizada', async ({cleanPage, context, browser, identity}) => {
    await enterApp(cleanPage)
    const created = await api<{id: number}>(cleanPage, '/api/recipe/', {method: 'POST', body: {
      name: `${fixturePrefix} privada prefijo ${identity.username} ${crypto.randomUUID()}`, private: true, steps: [], servings: 1,
    }})
    if (identity.role === 'consulta') {
      expect(created.status).toBe(403)
      return
    }
    expect(created.status).toBe(201)
    const recipeId = created.body.id
    const anonymous = await browser.newContext({baseURL: scopeUrl, storageState: {cookies: [], origins: []}, ignoreHTTPSErrors: process.env.CUADERNO_E2E_SELF_SIGNED === '1'})
    try {
      await assertUnauthenticated(anonymous)
      const png = await cleanPage.evaluate(() => {
        const canvas = document.createElement('canvas')
        canvas.width = canvas.height = 4
        const drawing = canvas.getContext('2d')!
        drawing.fillStyle = '#b98766'
        drawing.fillRect(0, 0, 4, 4)
        return canvas.toDataURL('image/png').split(',')[1]!
      })
      const upload = await context.request.put(appPath(`/api/recipe/${recipeId}/image/`), {
        headers: {'X-CSRFToken': await csrf(cleanPage), Origin: target.origin},
        multipart: {image: {name: 'synthetic.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64')}},
      })
      expect(upload.status()).toBe(200)
      const recipe = await api<{image: string}>(cleanPage, `/api/recipe/${recipeId}/`)
      expect(recipe.status).toBe(200)
      const image = new URL(recipe.body.image, scopeUrl)
      expect(image.origin).toBe(target.origin)
      expect(image.pathname.startsWith(scopePath + 'media/')).toBe(true)
      const privateResponse = await context.request.get(image.href)
      expect(privateResponse.status()).toBe(200)
      expect(privateResponse.headers()['cache-control']).toContain('no-store')
      expect((await anonymous.request.get(image.href)).status()).toBe(404)
      const share = await api<{share: string; link: string}>(cleanPage, `/api/share-link/${recipeId}`)
      expect(share.status).toBe(200)
      expect(new URL(share.body.link).pathname).toBe(appPath(`/recipe/${recipeId}/`))
      const sharedRecipe = await anonymous.request.get(appPath(`/api/recipe/${recipeId}/?share=${encodeURIComponent(share.body.share)}`))
      expect(sharedRecipe.status()).toBe(200)
      expect((await sharedRecipe.json()).id).toBe(recipeId)
      const invalid = new URL(image)
      invalid.searchParams.set('share', '00000000-0000-0000-0000-000000000000')
      expect((await anonymous.request.get(invalid.href)).status()).toBe(404)
      image.searchParams.set('share', share.body.share)
      const shared = await anonymous.request.get(image.href)
      expect(shared.status()).toBe(200)
      expect(shared.headers()['cache-control']).toContain('no-store')
      // Exercise browser rendering and print routing using the real shared link.
      await cleanPage.goto(share.body.link)
      const photo = cleanPage.locator(`img[src*="share=${share.body.share}"]`).first()
      await expect(photo).toBeVisible()
      await expect.poll(() => photo.evaluate(element => {
        const image = element as HTMLImageElement
        return image.complete && image.naturalWidth > 0
      })).toBe(true)
      await cleanPage.goto(appPath(`/recipe/${recipeId}/?print=true`))
      await cleanPage.emulateMedia({media: 'print'})
      await expect(cleanPage.locator('.v-navigation-drawer')).toBeHidden()
      await assertPublicCaches(cleanPage)
    } finally {
      await anonymous.close()
      const deleted = await api(cleanPage, `/api/recipe/${recipeId}/`, {method: 'DELETE'})
      expect(deleted.status).toBe(204)
    }
  })
})
