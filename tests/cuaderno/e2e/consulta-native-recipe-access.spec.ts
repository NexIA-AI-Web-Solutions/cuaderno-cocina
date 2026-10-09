import type {Page, Request} from '@playwright/test'
import {appPath, fixturePrefix} from './contracts.js'
import {api, assertNoHorizontalOverflow, enterApp, expect, rows, test} from './fixtures.js'
import {withAuthenticatedReadBarrier} from './native-read-barrier.js'

const consultationMessage = 'Modo Consulta: puedes revisar recetas, pero crear, editar o importar requiere el rol Cocina o Responsable. Pide a un Responsable que revise tu acceso.'
const createLinks = 'a[href$="/edit/recipe" i], a[href$="/recipe/import"]'

async function consultationNotice(page: Page) {
  const notice = page.locator('.cuaderno-native-recipe-access')
  await expect(notice).toHaveAttribute('aria-busy', 'false')
  await expect(notice.getByRole('status')).toContainText(consultationMessage)
  await expect(notice.getByRole('link', {name: 'Volver a recetas', exact: true})).toHaveAttribute('href', appPath('/'))
  await expect(page.locator('main form, main input, main textarea, main .v-stepper')).toHaveCount(0)
  await expect(page.locator('main').getByRole('button', {name: /^(Guardar|Save|Importar|Import|Vista previa|Previsualizar|Confirmar importación)$/i})).toHaveCount(0)
}

// All 27 Chromium edition/role/width projects exercise real DOM. The 18
// operators are positive controls; the nine Consulta cases perform no writes.
// CI's public seed is nonempty. Empty demonstration spaces are checked by the
// public release campaign; this suite does not mock a zero recipe count.
test('recetas nativas: Consulta recibe lectura y exportación, operadores conservan entradas y formularios', async ({cleanPage: page, identity}, info) => {
  const consultation = identity.role === 'consulta'
  const writes: string[] = []
  const base = new URL(process.env.BASE_URL || 'http://127.0.0.1:18081')
  const capture = (request: Request) => {
    const url = new URL(request.url())
    if (consultation && url.origin === base.origin && url.pathname.startsWith(appPath('/api/')) &&
      !['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && url.pathname !== appPath('/api/view-log/')) {
      writes.push(`${request.method()} ${url.pathname}`)
    }
  }
  page.on('request', capture)
  try {
    await enterApp(page)
    const edition = await api<{edition: string; operational_role: {code: string}}>(page, '/api/cuaderno/edition/')
    expect(edition.status).toBe(200)
    expect(edition.body.edition).toBe(identity.edition)
    expect(edition.body.operational_role.code).toBe({consulta: 'guest', cocina: 'user', responsable: 'admin'}[identity.role])
    if (consultation) {
      await expect(page.locator('main').locator(createLinks)).toHaveCount(0)
      await expect(page.locator('.v-app-bar').getByRole('button', {name: /crear receta|create recipe/i})).toHaveCount(0)
    } else {
      const createMenu = page.locator('.v-app-bar').getByRole('button', {name: /crear receta|create recipe/i})
      await expect(createMenu).toBeVisible()
      await createMenu.click()
      await expect(page.locator('.v-menu a[href$="/edit/recipe" i]')).toBeVisible()
      await expect(page.locator(`.v-menu a[href="${appPath('/recipe/import')}"]`)).toBeVisible()
      await page.keyboard.press('Escape')
    }
    if (identity.width !== 1440) {
      await page.locator('.v-bottom-navigation button').last().click()
      await expect(page.locator('.v-bottom-sheet')).toBeVisible()
    }
    const navigation = page.locator(identity.width === 1440 ? '.v-navigation-drawer' : '.v-bottom-sheet')
    const importLink = navigation.locator(`a[href="${appPath('/recipe/import')}"]`)
    if (consultation) await expect(navigation.locator(createLinks)).toHaveCount(0)
    else await expect(importLink).toBeVisible()

    await withAuthenticatedReadBarrier(page, async () => {
      await page.goto(appPath('/edit/Recipe'))
      if (consultation) await consultationNotice(page)
      else {
        await expect(page.locator('main form')).toBeVisible()
        await expect(page.locator('main').getByRole('textbox', {name: /^(Nombre|Name)$/})).toBeEnabled()
        await expect(page.locator('.cuaderno-native-recipe-access')).toHaveCount(0)
      }
    })
    await withAuthenticatedReadBarrier(page, async () => {
      await page.goto(appPath('/recipe/import'))
      if (consultation) await consultationNotice(page)
      else {
        await expect(page.locator('main .v-stepper')).toBeVisible()
        await expect(page.locator('main').getByRole('button', {name: /^(Siguiente|Next)$/})).toBeEnabled()
        await expect(page.locator('.cuaderno-native-recipe-access')).toHaveCount(0)
      }
    })
    if (consultation) {
      await page.getByRole('button', {name: 'Intercambio JSON de Cuaderno', exact: true}).click()
      await expect(page.getByRole('button', {name: 'Exportar JSON visible', exact: true})).toBeEnabled()
      await expect(page.locator('main input, main textarea')).toHaveCount(0)
      const exportResponse = page.waitForResponse(response => new URL(response.url()).pathname === appPath('/api/cuaderno/exchange/') && response.request().method() === 'GET')
      const download = page.waitForEvent('download')
      void exportResponse.catch(() => {})
      void download.catch(() => {})
      await page.getByRole('button', {name: 'Exportar JSON visible', exact: true}).click()
      const response = await exportResponse
      expect(response.status()).toBe(200)
      expect(await response.finished()).toBeNull()
      expect((await response.json()).format).toBe('cuaderno-recipes-v2')
      expect(await (await download).failure()).toBeNull()
      await withAuthenticatedReadBarrier(page, async () => {
        await page.getByRole('link', {name: 'Volver a recetas', exact: true}).click()
        await expect(page).toHaveURL(new RegExp(`${appPath('/').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`))
        await expect(page.locator('main .plan-features')).toBeVisible()
      })
      const seeded = await api(page, `/api/recipe/?query=${encodeURIComponent(fixturePrefix + ' receta pública')}&page_size=100`)
      expect(seeded.status).toBe(200)
      const matches = rows(seeded.body).filter(row => row.name === `${fixturePrefix} receta pública`)
      expect(matches).toHaveLength(1)
      const recipe = matches[0]!
      expect(Number.isSafeInteger(recipe.id)).toBe(true)
      await withAuthenticatedReadBarrier(page, async () => {
        await page.goto(appPath(`/edit/recipe/${recipe.id}`))
        await consultationNotice(page)
      })
      await withAuthenticatedReadBarrier(page, async () => {
        await page.goto(appPath(`/recipe/${recipe.id}`))
        await expect(page.getByRole('heading', {name: String(recipe.name), exact: true})).toBeVisible()
      }, [`/api/recipe/${recipe.id}/`, `/api/cuaderno/recipes/${recipe.id}/extras/`, `/api/cuaderno/recipes/${recipe.id}/ingredient-yields/`], ['/api/view-log/'])
      expect(writes, 'Consulta must not submit recipe/import/preview/commit or other mutating API requests').toEqual([])
    }
    await assertNoHorizontalOverflow(page, info)
  } finally {
    page.off('request', capture)
  }
})
