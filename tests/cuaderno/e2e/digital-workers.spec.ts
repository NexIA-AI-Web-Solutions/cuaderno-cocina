import {test as base, expect, type Page, type BrowserContext, type Cookie} from '@playwright/test'
import {readFileSync} from 'node:fs'

const test = base.extend<{browserErrors: string[]}>({
    browserErrors: [async ({page}, use) => {
        const errors: string[] = []
        page.on('pageerror', error => errors.push(error.message))
        page.on('console', message => {if (message.type() === 'error' && !message.text().includes('409 (Conflict)')) errors.push(message.text())})
        await use(errors)
        expect(errors, 'No unexpected browser errors').toEqual([])
    }, {auto: true}],
})
let cookies: Cookie[] = []
const kinds = ['cost_completion', 'price_watch', 'service_briefing', 'requirements_review', 'purchase_review', 'receipt_review', 'menu_candidates', 'service_learning']
function isolatedTarget(baseURL: string | undefined) {
    const target = new URL(baseURL || '')
    expect(target.hostname).toBe('127.0.0.1'); expect(target.port).toBe('18083')
}
function password() {
    if (process.env.CUADERNO_DEMO_PASSWORD) return process.env.CUADERNO_DEMO_PASSWORD
    const text = readFileSync('/tmp/cuaderno-workers-test.env', 'utf8')
    const value = text.match(/^CUADERNO_DEMO_PASSWORD=(.*)$/m)?.[1]?.trim().replace(/^(['"])(.*)\1$/, '$2')
    if (!value) throw new Error('Falta la credencial DEMO local de trabajadores.')
    return value
}
test.beforeAll(async ({browser, baseURL}) => {
    isolatedTarget(baseURL)
    const context = await browser.newContext({baseURL})
    const page = await context.newPage()
    await page.goto('/accounts/login/')
    await page.locator('input[name="login"],input[name="username"]').first().fill('demo-integral-responsable')
    await page.locator('input[name="password"]').fill(password()!)
    await Promise.all([page.waitForURL(url => !url.pathname.includes('/accounts/login/')), page.locator('button[type="submit"],input[type="submit"]').first().click()])
    cookies = await context.cookies()
    await context.close()
})
test.beforeEach(async ({context, baseURL}) => {isolatedTarget(baseURL); await context.addCookies(cookies)})
async function openWorker(page: Page, kind: string) {
    await page.goto(`/cuaderno/trabajadores?kind=${kind}`)
    await expect(page.getByRole('heading', {name: 'Trabajadores digitales'})).toBeVisible()
    await expect(page.getByRole('button', {name: 'Generar informe', exact: true})).toBeEnabled()
}
async function preview(page: Page, proposal = false) {
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/cuaderno/workers/preview/') && response.request().method() === 'POST')
    await page.getByRole('button', {name: proposal ? 'Generar informe y propuesta' : 'Generar informe', exact: true}).click()
    const response = await responsePromise
    expect(response.status(), 'Actual report preview succeeds').toBe(201)
    const run = await response.json()
    await expect(page.locator('#worker-report-title')).toHaveText(run.title)
    await expect(page.getByRole('button', {name: 'Descargar JSON', exact: true})).toBeVisible()
    return run
}
async function getJson(page: Page, path: string) {
    const response = await page.request.get(path)
    expect(response.ok(), `Native read ${path}`).toBeTruthy()
    return response.json()
}
async function inventory(page: Page) {const data = await getJson(page, '/api/inventory-entry/'); return Array.isArray(data) ? data : data.results}
async function csrf(context: BrowserContext) {return (await context.cookies()).find(cookie => cookie.name === 'csrftoken')?.value || ''}
async function choosePackage(page: Page, item: {id: number; food_name: string; label: string}) {
    // Vuetify's input is covered by the field's visual activator; its native
    // keyboard path opens the same menu without bypassing pointer checks.
    await page.getByRole('combobox', {name: 'Formato', exact: true}).focus()
    await page.getByRole('combobox', {name: 'Formato', exact: true}).press('ArrowDown')
    await page.getByRole('option', {name: `${item.food_name} — ${item.label}`, exact: true}).click()
}
async function preparePrice(page: Page, amount: string) {
    await openWorker(page, 'price_watch')
    const packages = await getJson(page, '/api/cuaderno/packages/')
    expect(packages.length).toBeGreaterThan(0)
    const item = packages[0]
    await page.getByRole('button', {name: 'Preparar cambio de precio', exact: true}).click()
    await choosePackage(page, item)
    await page.getByLabel(/Nuevo precio del envase/).fill(amount)
    await page.getByLabel('Fuente o motivo del cambio').fill('Tarifa sintética del test aislado de trabajadores')
    const run = await preview(page, true)
    expect(run.status).toBe('pending')
    await expect(page.getByRole('button', {name: 'Aprobar y aplicar', exact: true})).toBeDisabled()
    return {run, item}
}
async function approve(page: Page) {
    await page.getByRole('checkbox', {name: 'He revisado la evidencia y los efectos de esta propuesta'}).check()
    const responsePromise = page.waitForResponse(response => /\/api\/cuaderno\/workers\/\d+\/apply\/$/.test(response.url()))
    await page.getByRole('button', {name: 'Aprobar y aplicar', exact: true}).click()
    return responsePromise
}

test('all eight reports generate from real native records without business writes', async ({page}) => {
    const inventoryBefore = await inventory(page)
    const pricesBefore = await getJson(page, '/api/cuaderno/packages/')
    const ordersBefore = await getJson(page, '/api/cuaderno/purchase-orders/')
    for (const kind of kinds) {
        await openWorker(page, kind)
        const run = await preview(page)
        expect(run.kind).toBe(kind); expect(run.status).toBe('read_only'); expect(run.proposal).toBeNull()
        expect(run.report.analysis_mode).toBe('deterministic'); expect(run.input_digest).toMatch(/^[a-f0-9]{64}$/)
        await expect(page.getByText('Informe de solo lectura. No ha cambiado datos operativos.')).toBeVisible()
        await page.getByText('Fuentes y versión de los datos', {exact: true}).click()
        await expect(page.getByText(run.input_digest, {exact: true})).toBeVisible()
    }
    expect(await inventory(page)).toEqual(inventoryBefore)
    expect(await getJson(page, '/api/cuaderno/packages/')).toEqual(pricesBefore)
    expect(await getJson(page, '/api/cuaderno/purchase-orders/')).toEqual(ordersBefore)
})

test('price proposal applies only after review and native price readback confirms the change', async ({page}) => {
    const inventoryBefore = await inventory(page)
    const {run, item} = await preparePrice(page, '21,50')
    const before = (await getJson(page, '/api/cuaderno/packages/')).find((row: {id: number}) => row.id === item.id)
    expect(before.current_price?.id).not.toBe(run.result?.prices?.[0]?.id)
    const response = await approve(page)
    expect(response.status()).toBe(200)
    const applied = await response.json()
    expect(applied.status).toBe('applied'); expect(applied.result.stock_changed).toBe(false)
    await expect(page.getByText('Propuesta aplicada. La operación quedó registrada.')).toBeVisible()
    const after = (await getJson(page, '/api/cuaderno/packages/')).find((row: {id: number}) => row.id === item.id)
    expect(Number(after.current_price.amount)).toBe(21.5)
    expect(after.current_price.id).toBe(applied.result.price_ids[0])
    expect(after.current_price.id).not.toBe(before.current_price?.id)
    expect(await inventory(page)).toEqual(inventoryBefore)
})

test('purchase proposal creates a native draft with zero reception and preserves inventory', async ({page}) => {
    const inventoryBefore = await inventory(page)
    await openWorker(page, 'purchase_review')
    const item = (await getJson(page, '/api/cuaderno/packages/'))[0]
    await page.getByRole('button', {name: 'Preparar borrador de compra', exact: true}).click()
    await choosePackage(page, item)
    await page.getByLabel('Número de envases completos').fill('2')
    await page.getByLabel('Fuente o motivo del cambio').fill('Reposición sintética en test local')
    const run = await preview(page, true)
    expect(run.proposal.action).toBe('purchase_draft')
    const response = await approve(page); expect(response.status()).toBe(200)
    const applied = await response.json()
    const created = (await getJson(page, '/api/cuaderno/purchase-orders/')).find((row: {id: number}) => row.id === applied.result.order.id)
    expect(created.state).toBe('draft'); expect(Number(created.received_quantity)).toBe(0)
    expect(created.package).toBe(item.id)
    expect(Number(created.quantity)).toBe(Number(item.quantity) * 2)
    expect(applied.result.sent_to_supplier).toBe(false)
    expect(await inventory(page)).toEqual(inventoryBefore)
})

test('a concurrent price update produces stale UI and a new reviewed version', async ({page, context}) => {
    const {run, item} = await preparePrice(page, '22,30')
    const changed = await page.request.post(`/api/cuaderno/packages/${item.id}/prices/`, {data: {amount: '22.10', explicit_free: false}, headers: {'X-CSRFToken': await csrf(context)}})
    expect(changed.status()).toBe(201)
    const stale = await approve(page); expect(stale.status()).toBe(409)
    await expect(page.getByText('Los datos cambiaron. La propuesta no se ha aplicado. Genera una nueva versión.')).toBeVisible()
    await expect(page.getByRole('button', {name: 'Aprobar y aplicar', exact: true})).toHaveCount(0)
    const nextPromise = page.waitForResponse(response => response.url().endsWith('/api/cuaderno/workers/preview/'))
    await page.getByRole('button', {name: 'Generar nueva versión', exact: true}).click()
    const response = await nextPromise; expect(response.status()).toBe(201)
    const next = await response.json(); expect(next.id).not.toBe(run.id); expect(next.status).toBe('pending')
    await expect(page.getByRole('button', {name: 'Aprobar y aplicar', exact: true})).toBeDisabled()
})

for (const width of [390, 768, 1440]) test(`worker report stays usable at ${width}px`, async ({page}, testInfo) => {
    await page.setViewportSize({width, height: width === 390 ? 844 : width === 768 ? 1024 : 900})
    await openWorker(page, 'cost_completion')
    const run = await preview(page)
    const metrics = await page.evaluate(() => ({viewport: window.innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth}))
    expect(metrics.document).toBeLessThanOrEqual(metrics.viewport + 1)
    expect(metrics.body).toBeLessThanOrEqual(metrics.viewport + 1)
    await page.evaluate(() => window.scrollTo(0, 0))
    await expect(page.locator('#worker-report-title').locator('..')).not.toContainText('depth:')
    const calculation = page.getByText('Detalle del cálculo', {exact: true}).first()
    await expect(calculation).toBeVisible()
    expect(await calculation.locator('..').evaluate(element => element.hasAttribute('open'))).toBe(false)
    expect(await page.locator('#worker-report-title').locator('..').innerText()).not.toContain('6.4000000000000000')
    await page.screenshot({path: testInfo.outputPath(`workers-${width}.png`), fullPage: true})
    await calculation.click()
    await expect(page.getByText('Raciones originales', {exact: true}).first()).toBeVisible()
    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', {name: 'Descargar JSON', exact: true}).click()
    const download = await downloadPromise
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
    const exported = JSON.parse(Buffer.concat(chunks).toString('utf8'))
    expect(exported.source_version).toBe(run.input_digest)
    expect(exported.run.id).toBe(run.id)
    expect(exported.run.report.items[0].cost).toEqual(run.report.items[0].cost)
    await testInfo.attach('layout', {body: JSON.stringify(metrics), contentType: 'application/json'})
})

test('read-only schedules persist daily cadence and pause without implying a running executor', async ({page}) => {
    await openWorker(page, 'service_learning')
    await page.getByLabel('Día del servicio').fill('2026-10-11')
    await page.getByLabel('Desde (opcional)').fill('2026-10-01')
    await page.getByLabel('Hasta (opcional)').fill('2026-10-10')
    await page.getByText('Informes periódicos', {exact: true}).click()
    await expect(page.getByText(/El ejecutor periódico no está activado/)).toBeVisible()
    await expect(page.getByRole('checkbox', {name: 'Usar fecha del día en cada ejecución'})).toBeChecked()
    const createPromise = page.waitForResponse(response => response.url().endsWith('/api/cuaderno/workers/schedules/') && response.request().method() === 'POST')
    await page.getByRole('button', {name: 'Guardar programación', exact: true}).click()
    const response = await createPromise; expect(response.status()).toBe(201)
    const schedule = await response.json()
    expect(schedule.kind).toBe('service_learning'); expect(schedule.interval_hours).toBe(24); expect(schedule.enabled).toBe(true)
    expect(schedule.params.proposal).toBeUndefined()
    for (const key of ['date', 'start', 'end']) expect(schedule.params[key]).toBeUndefined()
    await expect(page.getByText('Programación guardada. La ejecución depende del ejecutor local.')).toBeVisible()
    const row = page.getByRole('listitem').filter({has: page.getByText('Próxima fecha prevista:', {exact: false})}).first()
    const pausePromise = page.waitForResponse(response => response.url().endsWith(`/api/cuaderno/workers/schedules/${schedule.id}/`))
    await row.getByRole('button', {name: 'Pausar', exact: true}).click()
    const paused = await pausePromise; expect(paused.status()).toBe(200); expect((await paused.json()).enabled).toBe(false)
    await expect(page.getByText('Programación en pausa.', {exact: true})).toBeVisible()
    await page.getByRole('checkbox', {name: 'Usar fecha del día en cada ejecución'}).uncheck()
    const fixedPromise = page.waitForResponse(response => response.url().endsWith('/api/cuaderno/workers/schedules/') && response.request().method() === 'POST')
    await page.getByRole('button', {name: 'Guardar programación', exact: true}).click()
    const fixedResponse = await fixedPromise; expect(fixedResponse.status()).toBe(201)
    const fixed = await fixedResponse.json()
    expect(fixed.params).toEqual({date: '2026-10-11', start: '2026-10-01', end: '2026-10-10'})
    const fixedPause = page.waitForResponse(response => response.url().endsWith(`/api/cuaderno/workers/schedules/${fixed.id}/`))
    await page.getByRole('listitem').filter({has: page.getByText('Próxima fecha prevista:', {exact: false})}).first().getByRole('button', {name: 'Pausar', exact: true}).click()
    const fixedPaused = await fixedPause; expect(fixedPaused.status()).toBe(200); expect((await fixedPaused.json()).enabled).toBe(false)
})
