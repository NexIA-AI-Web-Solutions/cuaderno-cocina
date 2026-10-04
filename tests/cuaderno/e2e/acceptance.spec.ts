import {readFile} from 'node:fs/promises'
import type {Browser, Page, TestInfo} from '@playwright/test'
import {api, assertNoHorizontalOverflow, enterApp, expect, rows, test} from './fixtures.js'
import {featureMatrix, fixturePrefix} from './contracts.js'

const corePages = [
  {path: '/', marker: '#app'},
  {path: '/cuaderno/lista', heading: 'Vista rápida de la lista'},
  {path: '/pantry', marker: '#app'},
  {path: '/cuaderno/precios', heading: 'Formatos y precios'},
] as const

async function gotoAndIdentify(page: Page, route: typeof corePages[number]): Promise<void> {
  await page.goto(route.path)
  await expect(page).not.toHaveURL(/\/accounts\/login\//)
  if ('heading' in route) await expect(page.getByText(route.heading, {exact: true}).first()).toBeVisible()
  else await expect(page.locator(route.marker)).toBeVisible()
}

async function openEditionNavigation(page: Page, width: number): Promise<void> {
  if (width === 1440) return
  const sheet = page.locator('.v-bottom-sheet .v-list')
  if (await sheet.isVisible()) return
  const menu = page.locator('.v-bottom-navigation button').last()
  await expect(menu).toBeVisible()
  await menu.click()
  await expect(sheet).toBeVisible()
}

async function assertEditionNavigation(
  page: Page,
  identity: {width: number},
  href: string,
  expected: boolean,
): Promise<void> {
  await openEditionNavigation(page, identity.width)
  const scope = identity.width === 1440 ? page.locator('.v-navigation-drawer') : page.locator('.v-bottom-sheet')
  const link = scope.locator(`a[href="${href}"]`)
  if (expected) await expect(link).toBeVisible()
  else await expect(link).toHaveCount(0)
}

test('carga los datos base y las pantallas comunes sin errores de navegador', async ({cleanPage, identity}) => {
  await enterApp(cleanPage)
  const edition = await api<{edition?: string; operational_role?: {code?: string}}>(cleanPage, '/api/cuaderno/edition/')
  expect(edition.status).toBe(200)
  expect(edition.body.edition).toBe(identity.edition)
  expect(edition.body.operational_role?.code).toBe({consulta: 'guest', cocina: 'user', responsable: 'admin'}[identity.role])

  const recipes = await api(cleanPage, '/api/recipe/?page_size=100')
  expect(recipes.status).toBe(200)
  expect(JSON.stringify(recipes.body)).toContain(fixturePrefix)
  // Consulta has scoped read access to Cuaderno catalogs and the native shared
  // shopping and inventory lists. Mutations remain covered by the role checks below.
  for (const endpoint of ['/api/cuaderno/packages/', '/api/shopping-list/']) {
    const fixtureData = await api(cleanPage, endpoint)
    expect(fixtureData.status, endpoint).toBe(200)
    expect(JSON.stringify(fixtureData.body), endpoint).toContain(fixturePrefix)
  }
  const inventory = await api(cleanPage, '/api/inventory-entry/?page_size=100')
  expect(inventory.status).toBe(200)
  expect(JSON.stringify(inventory.body)).toContain(fixturePrefix)
  for (const route of corePages) await gotoAndIdentify(cleanPage, route)
})

test('expone solo la navegación y APIs incluidas en la edición', async ({cleanPage, identity}) => {
  await enterApp(cleanPage)
  const canOperate = identity.role !== 'consulta'
  const expectedProduction = featureMatrix.production.has(identity.edition)
  const expectedWarehouse = featureMatrix.warehouse.has(identity.edition)

  await assertEditionNavigation(cleanPage, identity, '/cuaderno/precios', true)
  await assertEditionNavigation(cleanPage, identity, '/cuaderno/produccion', expectedProduction)
  await assertEditionNavigation(cleanPage, identity, '/cuaderno/almacen', expectedWarehouse)

  const services = await api(cleanPage, '/api/cuaderno/services/')
  expect(services.status).toBe(expectedProduction ? 200 : 403)
  if (services.status === 200) expect(JSON.stringify(services.body)).toContain(fixturePrefix)
  const movements = await api(cleanPage, '/api/cuaderno/movements/')
  expect(movements.status).toBe(expectedWarehouse ? 200 : 403)

  await cleanPage.goto('/cuaderno/produccion')
  await expect(cleanPage.getByRole('heading', {name: 'Producción', exact: true})).toBeVisible()
  if (!expectedProduction) {
    await expect(cleanPage.getByText(
      'La producción está disponible en las ediciones Profesional e Integral.',
      {exact: true},
    )).toBeVisible()
    await expect(cleanPage.getByRole('button', {name: 'Anotar servicio', exact: true})).toHaveCount(0)
    await expect(cleanPage.getByLabel('Recetas', {exact: true})).toHaveCount(0)
  } else if (!canOperate) {
    await expect(cleanPage.getByText(
      'Modo Consulta: las fichas están disponibles solo para lectura.',
      {exact: true},
    )).toBeVisible()
  }

  await cleanPage.goto('/cuaderno/almacen')
  await expect(cleanPage.getByRole('heading', {name: 'Compras y movimientos', exact: true})).toBeVisible()
  if (!expectedWarehouse) {
    await expect(cleanPage.getByText(
      'El almacén está disponible en la edición Integral.',
      {exact: true},
    )).toBeVisible()
    await expect(cleanPage.getByRole('button', {name: 'Aplicar movimiento', exact: true})).toHaveCount(0)
    await expect(cleanPage.getByText(
      'Modo Consulta: puedes revisar compras y movimientos, pero no modificarlos.',
      {exact: true},
    )).toHaveCount(0)
  } else if (!canOperate) {
    await expect(cleanPage.getByText(
      'Modo Consulta: puedes revisar compras y movimientos, pero no modificarlos.',
      {exact: true},
    )).toBeVisible()
  }
})

test('aplica ACL de rol y bloquea las escrituras de Consulta', async ({cleanPage, identity}) => {
  await enterApp(cleanPage)
  await cleanPage.goto('/cuaderno/precios')
  const savePackage = cleanPage.getByRole('button', {name: 'Guardar formato'})
  await expect(savePackage).toBeVisible()
  if (identity.role === 'consulta') {
    await expect(cleanPage.getByText(
      'Cuaderno operativo: no permitido para este rol. La consulta de costes disponible para tu cuenta permanece accesible.',
      {exact: true},
    )).toBeVisible()
    await expect(savePackage).toBeDisabled()
    await expect(cleanPage.getByLabel('Formato', {exact: true})).toBeDisabled()
    const consultHistory = cleanPage.getByRole('button', {name: /^Consultar el historial de /}).first()
    await expect(consultHistory).toBeEnabled()
    await consultHistory.click()
    await expect(cleanPage.getByRole('heading', {name: 'Historial del formato', exact: true})).toBeVisible()
    await expect(cleanPage.getByRole('button', {name: 'Actualizar precio', exact: true})).toHaveCount(0)
    await expect(cleanPage.getByLabel(/^Nuevo precio /)).toHaveCount(0)

    await cleanPage.goto('/cuaderno/lista')
    await expect(cleanPage.getByText('Modo Consulta: puedes revisar la lista, pero no modificarla.')).toBeVisible()
    await expect(cleanPage.getByRole('button', {name: 'Crear', exact: true})).toBeDisabled()
    await expect(cleanPage.getByRole('button', {name: 'Añadir', exact: true})).toBeDisabled()
    const shoppingToggle = cleanPage.getByRole('checkbox', {name: /^(Marcar|Desmarcar) /}).first()
    if (await shoppingToggle.count()) await expect(shoppingToggle).toBeDisabled()

    await cleanPage.goto('/cuaderno/produccion')
    if (featureMatrix.production.has(identity.edition)) {
      await expect(cleanPage.getByText(
        'Modo Consulta: las fichas están disponibles solo para lectura.',
        {exact: true},
      )).toBeVisible()
      for (const name of ['Calcular necesidades', 'Guardar rendimiento', 'Anotar servicio', 'Añadir línea', 'Consolidar', 'Declarar']) {
        await expect(cleanPage.getByRole('button', {name, exact: true})).toBeDisabled()
      }
    } else {
      await expect(cleanPage.getByText(
        'La producción está disponible en las ediciones Profesional e Integral.',
        {exact: true},
      )).toBeVisible()
      for (const name of ['Calcular necesidades', 'Guardar rendimiento', 'Anotar servicio', 'Añadir línea', 'Consolidar', 'Declarar']) {
        await expect(cleanPage.getByRole('button', {name, exact: true})).toHaveCount(0)
      }
    }

    await cleanPage.goto('/cuaderno/almacen')
    if (featureMatrix.warehouse.has(identity.edition)) {
      await expect(cleanPage.getByText(
        'Modo Consulta: puedes revisar compras y movimientos, pero no modificarlos.',
        {exact: true},
      )).toBeVisible()
      await expect(cleanPage.getByRole('button', {name: 'Aplicar movimiento', exact: true})).toBeDisabled()
      await expect(cleanPage.locator('[inert][aria-disabled="true"]')).toHaveCount(0)
      await expect(cleanPage.getByRole('button', {name: 'Guardar oferta', exact: true})).toBeDisabled()
      await expect(cleanPage.getByRole('button', {name: 'Crear borrador', exact: true})).toBeDisabled()
      await expect(cleanPage.getByRole('button', {name: 'Guardar mínimo', exact: true})).toBeDisabled()
      for (const action of ['Cancelar', 'Recibir']) {
        const controls = cleanPage.getByRole('button', {name: action, exact: true})
        for (const control of await controls.all()) await expect(control).toBeDisabled()
      }
      const refresh = cleanPage.getByRole('button', {name: 'Actualizar', exact: true})
      expect(await refresh.count()).toBeGreaterThanOrEqual(2)
      for (const control of await refresh.all()) await expect(control).toBeEnabled()
      const receipts = cleanPage.getByRole('button', {name: 'Recepciones', exact: true}).first()
      await expect(receipts).toBeEnabled()
      const receiptResponse = cleanPage.waitForResponse(response =>
        response.request().method() === 'GET' && /\/api\/cuaderno\/purchase-orders\/\d+\/receipts\/$/.test(response.url()),
      )
      await receipts.click()
      expect((await receiptResponse).status()).toBe(200)
    } else {
      await expect(cleanPage.getByText(
        'El almacén está disponible en la edición Integral.',
        {exact: true},
      )).toBeVisible()
      await expect(cleanPage.getByRole('button', {name: 'Aplicar movimiento', exact: true})).toHaveCount(0)
      await expect(cleanPage.locator('[inert][aria-disabled="true"]')).toHaveCount(0)
    }
  } else {
    const managePrice = cleanPage.getByRole('button', {name: /^Gestionar el precio de /}).first()
    await expect(managePrice).toBeEnabled()
    await managePrice.click()
    await expect(cleanPage.getByRole('button', {name: 'Actualizar precio', exact: true})).toBeEnabled()
  }

  const update = await api(cleanPage, '/api/cuaderno/edition/', {
    method: 'PUT',
    body: {edition: identity.edition},
  })
  expect(update.status).toBe(identity.role === 'responsable' ? 200 : 403)
})

test('no desborda en recetas, lista, inventario, precios, servicio y producción', async ({cleanPage}, testInfo) => {
  const routes = ['/', '/cuaderno/lista', '/pantry', '/cuaderno/precios', '/cuaderno/produccion']
  for (const route of routes) {
    await cleanPage.goto(route)
    await expect(cleanPage.locator('#app')).toBeVisible()
    await cleanPage.evaluate(() => document.fonts.ready)
    await assertNoHorizontalOverflow(cleanPage, testInfo)
  }
})

test('genera una vista de impresión PDF privada en el directorio del resultado', async ({cleanPage, identity}, testInfo) => {
  const route = featureMatrix.production.has(identity.edition) ? '/cuaderno/produccion' : '/cuaderno/precios'
  await cleanPage.goto(route)
  await cleanPage.emulateMedia({media: 'print'})
  const output = testInfo.outputPath(`cuaderno-${identity.edition}-${identity.role}-${identity.width}.pdf`)
  await cleanPage.pdf({path: output, format: 'A4', printBackground: true})
  const bytes = await readFile(output)
  expect(bytes.subarray(0, 4).toString('ascii')).toBe('%PDF')
  expect(bytes.length).toBeGreaterThan(1_000)
})

test('repite una recepción con la misma clave una sola vez', async ({cleanPage, identity}) => {
  await enterApp(cleanPage)
  const applicable = identity.edition === 'integral' && identity.role !== 'consulta'
  if (!applicable) {
    const denied = await api(cleanPage, '/api/cuaderno/purchase-orders/1/receipts/', {
      method: 'POST', body: {entry: 1, quantity: '0.0001', idempotency_key: 'e2e-denied'},
    })
    expect(denied.status).toBe(403)
    return
  }

  const orderResponse = await api(cleanPage, '/api/cuaderno/purchase-orders/')
  expect(orderResponse.status).toBe(200)
  const orderMarker = `${fixturePrefix}-${identity.role}-${identity.width}`
  const order = rows(orderResponse.body).find(item =>
    item.supplier_name === orderMarker && ['ordered', 'part_received'].includes(String(item.state)),
  )
  if (!order) throw new Error(`El fixture Integral necesita el pedido ${orderMarker} disponible para recibir.`)

  const entriesResponse = await api(cleanPage, '/api/inventory-entry/?page_size=100')
  expect(entriesResponse.status).toBe(200)
  const entry = rows(entriesResponse.body).find(item => {
    const food = typeof item.food === 'object' && item.food ? (item.food as {id?: unknown}).id : item.food
    const unit = typeof item.unit === 'object' && item.unit ? (item.unit as {id?: unknown}).id : item.unit
    return food === order.food && unit === order.unit
  })
  if (!entry) throw new Error('El fixture Integral necesita una existencia para el alimento y unidad del pedido.')

  const key = `e2e-receipt-${crypto.randomUUID()}`
  const endpoint = `/api/cuaderno/purchase-orders/${String(order.id)}/receipts/`
  const payload = {entry: entry.id, quantity: '0.0001', idempotency_key: key}
  const first = await api<{id?: number}>(cleanPage, endpoint, {method: 'POST', body: payload})
  const replay = await api<{id?: number}>(cleanPage, endpoint, {method: 'POST', body: payload})
  expect(first.status).toBe(201)
  expect(replay.status).toBe(200)
  expect(replay.body.id).toBe(first.body.id)
})

async function newAuthenticatedPage(browser: Browser, testInfo: TestInfo): Promise<{page: Page; close: () => Promise<void>}> {
  const storageState = testInfo.project.use.storageState
  const baseURL = testInfo.project.use.baseURL
  if (typeof storageState !== 'string' || typeof baseURL !== 'string') throw new Error('El proyecto no declaró auth/baseURL.')
  const context = await browser.newContext({storageState, baseURL})
  const page = await context.newPage()
  await page.goto('/')
  return {page, close: () => context.close()}
}

test('rechaza el segundo escritor de una línea de compra obsoleta', async ({browser, cleanPage, identity}, testInfo) => {
  await enterApp(cleanPage)
  if (identity.role === 'consulta') {
    const denied = await api(cleanPage, '/api/shopping-list-entry/1/', {
      method: 'PATCH', body: {checked: true}, headers: {'If-Match': '"e2e"'},
    })
    expect(denied.status).toBe(403)
    return
  }

  const list = await api(cleanPage, '/api/shopping-list-entry/?page_size=100')
  expect(list.status).toBe(200)
  const entry = rows(list.body).find(item => JSON.stringify(item).includes(fixturePrefix)) || rows(list.body)[0]
  if (!entry || typeof entry.id !== 'number' || typeof entry.updated_at !== 'string') {
    throw new Error('El fixture necesita una línea de compra con id y updated_at.')
  }
  const body = {checked: !Boolean(entry.checked)}
  const headers = {'If-Match': `"${entry.updated_at}"`}
  const left = await newAuthenticatedPage(browser, testInfo)
  const right = await newAuthenticatedPage(browser, testInfo)
  try {
    const results = await Promise.all([
      api(left.page, `/api/shopping-list-entry/${entry.id}/`, {method: 'PATCH', body, headers}),
      api(right.page, `/api/shopping-list-entry/${entry.id}/`, {method: 'PATCH', body, headers}),
    ])
    expect(results.map(result => result.status).sort()).toEqual([200, 409])
  } finally {
    await Promise.all([left.close(), right.close()])
  }
})
