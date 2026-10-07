import type {Locator, Page, Route, TestInfo} from '@playwright/test'
import {appPath, featureMatrix, fixturePrefix} from './contracts.js'
import {assertNoHorizontalOverflow, enterApp, expect, test} from './fixtures.js'

// page.route cannot hold API fetches after a worker claims the page. Real worker
// behavior stays covered by prefix-acceptance; this file exercises DOM states.
test.use({serviceWorkers: 'block'})

// IDs map to the reviewed presentation ledger. These assertions run against the
// candidate's native UI and real synthetic data; none submits data edits or
// settings. Opening a recipe retains its native, owner-scoped view logging.
async function record(testInfo: TestInfo, ids: string[], measurements: object = {}) {
  await testInfo.attach('modernization-outcomes', {
    contentType: 'application/json',
    body: JSON.stringify({ids, project: testInfo.project.name, measurements}),
  })
}

async function box(locator: Locator) {
  await expect(locator).toBeVisible()
  const value = await locator.boundingBox()
  expect(value).not.toBeNull()
  return value!
}

async function style(locator: Locator, property: string) {
  return locator.evaluate((element, property) => getComputedStyle(element).getPropertyValue(property), property)
}

// Hold only the browser's specific GET, after fetching its genuine response.
// It makes loading states observable without fabricating data or an HTTP error.
async function holdRead(page: Page, pathname: string, query: (url: URL) => boolean) {
  const base = new URL(process.env.BASE_URL || 'http://127.0.0.1:18081')
  const match = (url: URL) => url.origin === base.origin && url.pathname === appPath(pathname) && query(url)
  let release!: () => void
  let ready!: () => void
  const released = new Promise<void>(resolve => { release = resolve })
  const received = new Promise<void>(resolve => { ready = resolve })
  const handler = async (route: Route) => {
    expect(route.request().method()).toBe('GET')
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    ready()
    await released
    await route.fulfill({response})
  }
  await page.route(match, handler, {times: 1})
  return {received, release, remove: () => page.unroute(match, handler)}
}

// A route's visible heading can precede native GET bodies. Drain only observed
// same-origin application API requests before the next planned navigation.
async function transition(page: Page, action: () => Promise<unknown>, ready: (remaining: () => number) => Promise<unknown>) {
  const base = new URL(process.env.BASE_URL || 'http://127.0.0.1:18081')
  const reads = new Set<Promise<unknown>>()
  const listen = (request: import('@playwright/test').Request) => {
    const url = new URL(request.url())
    if (request.method() !== 'GET' || url.origin !== base.origin || !url.pathname.startsWith(appPath('/api/'))) return
    const pending = request.response().then(async response => {
      expect(response, 'native GET receives a response before leaving its route').not.toBeNull()
      const error = await response!.finished()
      expect(error, 'native GET body finishes before leaving its route').toBeNull()
    })
    // Attach rejection handling immediately; awaiting the snapshot still fails.
    void pending.catch(() => {})
    reads.add(pending)
  }
  page.on('request', listen)
  const deadline = Date.now() + 8_000
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const navigateAndDrain = async () => {
      await action()
      await ready(() => Math.max(1, deadline - Date.now()))
      while (reads.size) {
        const snapshot = [...reads]
        await Promise.all(snapshot)
        for (const item of snapshot) reads.delete(item)
      }
    }
    await Promise.race([
      navigateAndDrain(),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Native route read barrier exceeded its existing readiness budget')), Math.max(1, deadline - Date.now())) }),
    ])
  } finally {
    if (timer) clearTimeout(timer)
    page.off('request', listen)
  }
}

async function go(page: Page, path: string, marker: Locator) {
  await transition(page, () => page.goto(appPath(path)), remaining => expect(marker).toBeVisible({timeout: remaining()}))
}

test('modernización: UX02–08/13–14 y UI01–08 · navegación y recetas', async ({cleanPage: page, identity}, testInfo) => {
  const count = await holdRead(page, '/api/recipe/', url => url.searchParams.get('page_size') === '1')
  const entered = enterApp(page)
  void entered.catch(() => {})
  try {
    await Promise.race([count.received, entered])
    await expect(page.locator('.cuaderno-home-loading'), 'UX08 announces an actual pending recipe count').toBeVisible()
    await expect(page.locator('.cuaderno-home-loading')).toHaveAttribute('aria-live', 'polite')
    count.release()
    await entered
  } finally {
    count.release()
    await count.remove()
  }
  const main = page.locator('#cuaderno-main')
  await expect(main.getByRole('heading', {name: /^(Recipes|Recetas)$/, level: 1}), 'UI08 home task heading').toBeVisible()
  await expect(page.locator('.cuaderno-home-header .v-chip'), 'UI08 genuine count context').toHaveText(/^\d+$/)
  const logo = page.locator('.v-app-bar img[alt="Cuaderno Cocina"]').first()
  await expect(logo, 'UI02 original product identity').toBeVisible()
  expect(await logo.getAttribute('src')).not.toMatch(/tandoor|pizza/i)
  const contrast = await page.locator('.v-application').evaluate(element => {
    const colors = getComputedStyle(element)
    const luminance = (value: string) => value.split(',').map(part => Number(part.trim()) / 255)
      .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
      .reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0)
    return ['primary', 'secondary', 'surface', 'background'].map(surface => {
      const values = [surface, 'on-' + surface].map(key => luminance(colors.getPropertyValue('--v-theme-' + key))).sort((a, b) => a - b)
      return {surface, ratio: (values[1] + .05) / (values[0] + .05)}
    })
  })
  for (const pair of contrast) expect(pair.ratio, `UI01 ${pair.surface} readable text`).toBeGreaterThanOrEqual(4.5)
  const skip = page.locator('.cuaderno-skip-link')
  await skip.focus()
  expect((await box(skip)).y, 'UX04 skip control appears when focused').toBeGreaterThanOrEqual(0)
  await page.keyboard.press('Enter')
  await expect(main, 'UX04 keyboard reaches primary content').toBeFocused()

  if (identity.width < 1440) {
    const bottom = page.locator('.cuaderno-bottom-navigation')
    await expect(bottom.locator('.v-btn'), 'UX02 all four native destinations remain present').toHaveCount(4)
    for (const item of await bottom.locator('.v-btn').all()) {
      await expect(item.locator('.v-btn__content > span'), 'UX02 visible destination label').toBeVisible()
    }
    expect((await box(bottom)).height, 'UI04 distinct mobile navigation rhythm').toBeGreaterThanOrEqual(72)
    expect(await style(bottom.locator('a').first(), 'border-top-width')).toBe('3px')
    expect(await style(bottom.locator('a').first(), 'border-top-color'), 'UI04 active destination indicator').not.toBe(await style(bottom.locator('a').nth(1), 'border-top-color'))
  } else {
    const active = page.locator('.v-navigation-drawer a.v-list-item--active').first()
    expect(await style(active, 'border-inline-start-width'), 'UI03 current desktop destination indicator').toBe('3px')
    expect((await box(active)).height, 'UI03 navigation row rhythm').toBeGreaterThanOrEqual(48)
  }

  const profile = page.locator('button.cuaderno-user-menu')
  await expect(profile, 'UX03 native named profile button').toHaveAccessibleName(/\S+/)
  await profile.focus()
  await page.keyboard.press('Enter')
  await expect(profile, 'UX03 keyboard opens the actual menu').toHaveAttribute('aria-expanded', 'true')
  const userMenu = page.locator('.v-menu.v-overlay--active').filter({has: page.locator('a.cuaderno-household-link')})
  await expect(userMenu).toBeVisible()
  const household = userMenu.locator('a.cuaderno-household-link')
  await expect(household, 'UX14 household is a native destination').toHaveAttribute('href', new RegExp(`${appPath('/list/')}household$`, 'i'))
  expect(await style(userMenu.locator('.cuaderno-identity-name'), 'white-space'), 'UX13 full identity can wrap').toBe('normal')
  expect(await style(userMenu.locator('.cuaderno-identity-line').first(), 'overflow-wrap')).toBe('anywhere')
  await household.focus()
  await expect(household, 'UX14 household link receives keyboard focus').toBeFocused()
  await page.keyboard.press('Escape')

  const card = main.locator('article.cuaderno-recipe-card').first()
  const cardBox = await box(card)
  expect(cardBox.width, 'UI05 a recipe occupies its responsive column').toBeLessThan(identity.width * (identity.width === 1440 ? .45 : identity.width === 768 ? .7 : 1))
  expect(await style(card, 'border-radius'), 'UI07 card containment independent from grid').toBe('16px')
  expect(await style(card, 'padding-top')).toBe('12px')
  const title = card.locator('a.cuaderno-recipe-title')
  await expect(title, 'UX05 native recipe link preserves destination').toHaveAttribute('href', new RegExp(`${appPath('/recipe/')}\\d+`))
  await title.focus()
  await expect(title).toBeFocused()
  expect(await style(title, 'overflow-wrap'), 'UI07 long names wrap inside the card').toBe('anywhere')
  const placeholder = main.locator('.cuaderno-recipe-placeholder img.v-img__img').first()
  expect(await style(placeholder, 'object-fit'), 'UI06 original illustration remains contained').toBe('contain')
  expect(await placeholder.getAttribute('src')).not.toMatch(/pizza/i)
  const more = main.locator('button.cuaderno-section-more[data-mode="random"]').first()
  await expect(more, 'UX06 section action has its own accessible task name').toHaveAccessibleName(/.+: .+/)
  expect((await box(more)).height).toBeGreaterThanOrEqual(44)
  await assertNoHorizontalOverflow(page, testInfo)
  await more.focus()
  await transition(page, () => page.keyboard.press('Enter'), async remaining => {
    await expect(page, 'UX06 keyboard follows the section filter').toHaveURL(url => url.pathname === appPath('/advanced-search') && url.searchParams.get('sortOrder') === 'random', {timeout: remaining()})
    await expect(main.getByRole('textbox', {name: /^(Search|Buscar)$/})).toBeVisible({timeout: remaining()})
  })
  await enterApp(page)
  const destination = main.locator('a.cuaderno-recipe-title').first()
  const name = (await destination.innerText()).trim()
  const href = await destination.getAttribute('href')
  expect(href).not.toBeNull()
  const target = new URL(href!, page.url())
  const logged = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === appPath('/api/view-log/'), {timeout: 8_000})
  void logged.catch(() => {})
  await destination.focus()
  await transition(page, () => page.keyboard.press('Enter'), async remaining => {
    await expect(page, 'UX05 native keyboard activation follows the exact recipe destination').toHaveURL(target.href, {timeout: remaining()})
    await expect(main.getByText(name, {exact: true}).filter({visible: true}).first()).toBeVisible({timeout: remaining()})
    const response = await logged
    expect(response.status(), 'native view logging keeps its owner-scoped permission').toBe(201)
    expect(await response.finished()).toBeNull()
  })
  await record(testInfo, [...(identity.width < 1440 ? ['UX02'] : []), 'UX03', 'UX04', 'UX05', 'UX06', 'UX08', 'UX13', 'UX14', 'UI01', 'UI02', ...(identity.width < 1440 ? ['UI04'] : ['UI03']), 'UI05', 'UI06', 'UI07', 'UI08'], {cardWidth: cardBox.width, contrast})
})

test('modernización: UX01/20 y UI11/12 · ajustes y formatos', async ({cleanPage: page, identity}, testInfo) => {
  await enterApp(page)
  const appearance = page.locator('.cuaderno-appearance-form')
  await go(page, '/settings/cosmetic', appearance)
  const navigation = page.locator('details.cuaderno-settings-navigation')
  const summary = navigation.locator('summary')
  if (identity.width < 1440) {
    await expect(navigation, 'UX01 mobile settings navigation starts collapsed').not.toHaveAttribute('open')
    expect((await box(appearance)).y, 'UX01 current panel no longer follows a660px sidebar').toBeLessThan(page.viewportSize()!.height * .45)
    await summary.focus()
    await page.keyboard.press('Enter')
    await expect(navigation).toHaveAttribute('open', '')
    await page.keyboard.press('Enter')
    await expect(navigation).not.toHaveAttribute('open')
  } else {
    await expect(navigation).toHaveAttribute('open', '')
    await expect(summary).toBeHidden()
    const selected = navigation.locator('a.v-list-item--active')
    expect(await style(selected, 'border-inline-start-width'), 'UI11 selected settings panel has its own sidebar indicator').toBe('3px')
    expect((await box(appearance)).x).toBeGreaterThan((await box(navigation)).x)
  }
  expect(await style(navigation, 'border-radius'), 'UI11 panel navigation containment').toBe('16px')
  const sections = appearance.locator('section[aria-labelledby]')
  await expect(sections, 'UI12 appearance and preferences grouped separately').toHaveCount(2)
  for (const section of await sections.all()) {
    await expect(section.getByRole('heading')).toHaveCount(1)
    expect(await style(section, 'padding-top')).toBe(identity.width === 390 ? '16px' : '24px')
    expect(await style(section, 'border-radius')).toBe('16px')
  }
  await go(page, '/settings/export', page.getByRole('combobox', {name: /^(Type|Tipo)$/}))
  await page.getByRole('combobox', {name: /^(Type|Tipo)$/}).click()
  const descriptions = page.locator('.v-select__content .v-list-item-subtitle')
  await expect(descriptions, 'UX20 every available format describes its real file structure').toHaveCount(6)
  const expectedDescriptions = [
    ['DEFAULT', 'ZIP nativo con recetas, archivos e imágenes.'],
    ['CHOWDOWN', 'Archivo con carpetas de recetas Markdown e imágenes.'],
    ['COOKLANG', 'Archivos .cook con ingredientes y unidades dentro del texto.'],
    ['NEXTCLOUD', 'Una carpeta por receta con recipe.json e imagen asociada.'],
    ['RECIPESAGE', 'Exportación JSON-LD con datos estructurados de recetas.'],
    ['SAFFRON', 'Recetas en texto con secciones de ingredientes y preparación.'],
  ]
  for (const [index, [id, description]] of expectedDescriptions.entries()) {
    await expect(descriptions.nth(index), `UX20 ${id} explains its reviewed native structure`).toHaveText(description)
  }
  await page.keyboard.press('Escape')
  await assertNoHorizontalOverflow(page, testInfo)
  await record(testInfo, [...(identity.width < 1440 ? ['UX01'] : []), 'UX20', 'UI11', 'UI12'])
})

test('modernización: UX10–12 y UI16 · búsqueda con teclado y petición pendiente', async ({cleanPage: page}, testInfo) => {
  await enterApp(page)
  const trigger = page.locator('.v-app-bar').getByRole('button', {name: /^(Search|Buscar)$/})
  await expect(trigger, 'UX10 quick search is named on mobile as well as desktop').toBeVisible()
  await trigger.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog')
  const input = dialog.locator('#id_global_search_input')
  await expect(input, 'UX10 search input is named').toHaveAccessibleName(/^(Search|Buscar)$/)
  await expect(dialog.getByRole('status')).toHaveCount(0)
  await expect(input, 'UX11 native combobox identifies its result list').toHaveAttribute('role', 'combobox')
  await expect(input).toHaveAttribute('aria-controls', 'cuaderno-search-results')
  const options = dialog.getByRole('option')
  await expect(options.nth(1)).toBeVisible()
  await input.focus()
  await page.keyboard.press('ArrowDown')
  await expect(options.nth(1), 'UX11 keyboard selection is announced').toHaveAttribute('aria-selected', 'true')
  const selected = dialog.locator('.cuaderno-search-result-selected')
  expect(await style(selected, 'border-inline-start-width'), 'UI16 selection has an independent visual indicator').toBe('4px')
  await expect(input).toHaveAttribute('aria-activedescendant', await selected.getAttribute('id') as string)
  const query = '__cuaderno-modernization-no-match__'
  const held = await holdRead(page, '/api/recipe/', url => url.searchParams.get('query') === query)
  try {
    await input.fill(query)
    await expect(input, 'UX12 typing/debounce is pending before server response').toHaveAttribute('aria-busy', 'true')
    await held.received
    await expect(dialog.getByRole('status'), 'UX12 request still pending when genuine response is held').toHaveText(/Loading|Cargando/)
    held.release()
    await expect(input).toHaveAttribute('aria-busy', 'false')
    await expect(dialog.getByRole('status'), 'UX12 no matches only after response finishes').toHaveText(/No matching recipes|No hay recetas/)
    await expect(options).toHaveCount(1) // native advanced-search action remains available
  } finally {
    held.release()
    await held.remove()
  }
  await dialog.getByRole('button', {name: /^(Close|Cerrar)$/}).click()
  await expect(dialog).toBeHidden()
  await record(testInfo, ['UX10', 'UX11', 'UX12', 'UI16'])
})

test('modernización: UX15–17/19 y UI13–15 · ayuda coherente y legible', async ({cleanPage: page, identity}, testInfo) => {
  await enterApp(page)
  const article = page.locator('.cuaderno-help-article')
  await go(page, '/help?section=recipes', article)
  const paragraphs = article.locator('.v-window-item--active p')
  await expect(paragraphs.first(), 'UX15 product guidance is Spanish prose').toContainText('Una receta contiene pasos')
  await expect(paragraphs.nth(1), 'UX16 guidance does not claim all recipes public').toContainText('no todas las recetas son públicas')
  await expect(paragraphs.nth(2)).toContainText('si el espacio permite compartir')
  expect((await box(article)).width, 'UI13 constrained reading measure').toBeLessThanOrEqual(860)
  expect(Number.parseFloat(await style(paragraphs.first(), 'line-height')) / Number.parseFloat(await style(paragraphs.first(), 'font-size')), 'UI13 readable body line spacing').toBeCloseTo(1.75, 1)
  const choose = async (name: RegExp) => {
    if (identity.width < 1440) {
      const selector = article.getByRole('combobox', {name: /^(Help|Ayuda)$/})
      await expect(selector, 'UX19 named native topic selector').toBeVisible()
      await selector.click()
      await page.getByRole('option', {name}).click()
    } else {
      await page.locator('.cuaderno-help-navigation .v-list-item').filter({hasText: name}).click()
      await expect(page.locator('.cuaderno-help-navigation .v-list-item--active'), 'UI14 current desktop topic selected').toHaveText(name)
    }
  }
  await choose(/^(AI|IA)$/)
  await expect(article.getByRole('heading', {name: /^(AI|IA)$/, level: 1}), 'UX19 topic selection updates its real heading').toBeVisible()
  await expect(article.getByRole('status'), 'UX17 accurately reports disabled IA').toContainText('La IA no está habilitada')
  await expect(article.locator('.v-window-item--active a[href*="AiProvider"]')).toHaveCount(0)
  await choose(/^(Translations|Traducciones)$/)
  const progress = article.locator('tbody .v-progress-linear').first()
  await expect(progress).toBeVisible()
  expect((await box(progress)).height, 'UI15 readable percentage coverage').toBeGreaterThanOrEqual(24)
  expect(Number.parseFloat(await style(progress.locator('span'), 'font-size'))).toBeGreaterThanOrEqual(12)
  await expect(progress).toHaveText(/\d+%/)
  await expect(article.locator('tbody a[aria-label^="Editar traducción:"]').first()).toHaveAccessibleName(/Editar traducción: .+/)
  await assertNoHorizontalOverflow(page, testInfo)
  await record(testInfo, ['UX15', 'UX16', 'UX17', 'UX19', 'UI13', ...(identity.width === 1440 ? ['UI14'] : []), 'UI15'])
})

test('modernización: UX09/18 y UI17/18 · lista de compra y vista rápida', async ({cleanPage: page}, testInfo) => {
  await enterApp(page)
  const toolbar = page.locator('.cuaderno-shopping-toolbar')
  await go(page, '/shopping', toolbar)
  const tabs = page.locator('.cuaderno-shopping-tabs')
  await expect(tabs.getByRole('tab', {name: /Shopping List|Lista de la Compra/}), 'UX18 visible shopping task label').toBeVisible()
  await expect(tabs.getByRole('tab', {name: /Recipes|Recetas/})).toBeVisible()
  expect(await style(toolbar, 'border-radius'), 'UI17 independent toolbar grouping').toBe('12px')
  expect(await style(toolbar, 'padding-top')).toBe('10px')
  const currentTab = tabs.locator('.v-tab--selected')
  expect(await style(currentTab, 'border-top-left-radius'), 'UI17 visible current task presentation').toBe('10px')
  // The seed creates this guarded empty list after the populated default list.
  // Selecting it changes only this browser's native device filter.
  await toolbar.locator('.v-chip').filter({has: page.locator('.fa-file-lines')}).click()
  const emptyList = page.locator('.v-overlay--active .v-list-item').filter({hasText: `${fixturePrefix} compra vacía`})
  await expect(emptyList).toBeVisible()
  await emptyList.click()
  await page.keyboard.press('Escape')
  const empty = page.locator('.cuaderno-shopping-empty')
  await expect(empty, 'UX09 explains an actual empty synthetic list').toBeVisible()
  await expect(empty.locator('.v-card-text')).toHaveText(/Choose or create|Elige o crea/)
  const quickLink = empty.locator(`a[href="${appPath('/cuaderno/lista')}"]`)
  await expect(quickLink, 'UX09 retains a permitted next step for every role').toBeVisible()
  await quickLink.click()
  const list = page.locator('.cuaderno-quick-list')
  await expect(list.getByRole('heading', {name: 'Pendiente', exact: true, level: 2}), 'UI18 pending items are a separate section').toBeVisible()
  await expect(list.getByRole('heading', {name: 'Hecho', exact: true, level: 2})).toBeVisible()
  for (const count of await list.locator('.v-list-subheader .v-chip').all()) await expect(count).toHaveText(/^\d+$/)
  expect(await style(list, 'border-radius')).toBe('16px')
  await expect(page.locator('#cuaderno-main .v-select__selection-text'), 'UI18 populated default list is actually selected').toContainText(fixturePrefix)
  await expect(page.getByRole('progressbar', {name: 'Cargando lista'})).toHaveCount(0)
  await assertNoHorizontalOverflow(page, testInfo)
  await record(testInfo, ['UX09', 'UX18', 'UI17', 'UI18'])
})

test('modernización: UX07 y UI09/10/19/20 · calendario y operaciones por edición', async ({cleanPage: page, identity}, testInfo) => {
  await enterApp(page)
  const calendar = page.locator('.cuaderno-calendar')
  await go(page, '/mealplan', calendar.locator('.cuaderno-calendar-period h1'))
  await expect(calendar.locator('.cuaderno-calendar-period h1'), 'UI09 current date range stays visible on mobile').toHaveText(/\S.+–.+\S/)
  await expect(calendar.getByRole('textbox', {name: /^(Date|Fecha)$/}), 'UX07 date input has its own name').toBeVisible()
  for (const name of [/^(Previous Period|Per[ií]odo [Aa]nterior)$/, /^(Today|Hoy)$/, /^(Next|Siguiente)$/]) {
    const button = calendar.getByRole('button', {name})
    const dimensions = await box(button)
    expect(dimensions.width, 'UX07 calendar target width').toBeGreaterThanOrEqual(44)
    expect(dimensions.height, 'UX07 calendar target height').toBeGreaterThanOrEqual(44)
  }
  const today = calendar.locator('.cv-day.today .cv-day-number')
  expect(await style(today, 'border-bottom-width'), 'UI10 actual current day has a readable independent indicator').toBe('3px')
  expect(await style(calendar.locator('.cv-header-day').first(), 'font-weight')).toBe('600')
  const period = calendar.locator('.cuaderno-calendar-period h1')
  const originalPeriod = (await period.innerText()).trim()
  await transition(page, () => calendar.getByRole('button', {name: /^(Next|Siguiente)$/}).click(), remaining => expect(period, 'UX07 next control changes the native period').not.toHaveText(originalPeriod, {timeout: remaining()}))
  await transition(page, () => calendar.getByRole('button', {name: /^(Today|Hoy)$/}).click(), remaining => expect(period, 'UX07 today restores the current period').toHaveText(originalPeriod, {timeout: remaining()}))
  const ids = ['UX07', 'UI09', 'UI10']
  await go(page, '/cuaderno/produccion', page.getByRole('heading', {name: 'Producción', exact: true, level: 1}))
  if (featureMatrix.production.has(identity.edition)) {
    const formHeading = page.getByRole('heading', {name: 'Ficha desde recetas', exact: true, level: 2})
    await expect(formHeading, 'UI19 production form hierarchy').toBeVisible()
    const state = page.locator('.cuaderno-service-state').first()
    await expect(state, 'UI19 actual service state is independently labeled').toHaveText(/^(Borrador|Confirmado|Producido|Cancelado)$/)
    expect(await style(formHeading.locator('..'), 'padding-top')).toBe('18px')
    await expect(page.getByRole('button', {name: 'Anotar servicio', exact: true})).toBeEnabled({enabled: identity.role !== 'consulta'})
    ids.push('UI19')
  } else {
    await expect(page.getByText('La producción está disponible en las ediciones Profesional e Integral.', {exact: true})).toBeVisible()
    await expect(page.getByRole('button', {name: 'Anotar servicio', exact: true})).toHaveCount(0)
  }
  await go(page, '/cuaderno/almacen', page.getByRole('heading', {name: 'Compras y movimientos', exact: true, level: 1}))
  if (featureMatrix.warehouse.has(identity.edition)) {
    await expect(page.getByRole('heading', {name: 'Movimiento manual', exact: true, level: 2}), 'UI20 movement and audit have separate headings').toBeVisible()
    await expect(page.getByRole('heading', {name: 'Historial de existencias', exact: true, level: 2})).toBeVisible()
    const audit = page.locator('.movement-detail').filter({hasText: /Autor #\d+/}).first()
    await expect(audit, 'UI20 actual movement audit remains readable').toBeVisible()
    expect(await style(audit, 'padding-top')).toBe('6px')
    expect(await style(audit, 'padding-inline-start')).toBe('10px')
    await expect(page.getByRole('button', {name: 'Aplicar movimiento', exact: true})).toBeEnabled({enabled: identity.role !== 'consulta'})
    ids.push('UI20')
  } else {
    await expect(page.getByText('El almacén está disponible en la edición Integral.', {exact: true})).toBeVisible()
    await expect(page.getByRole('button', {name: 'Aplicar movimiento', exact: true})).toHaveCount(0)
  }
  await assertNoHorizontalOverflow(page, testInfo)
  await record(testInfo, ids)
})
