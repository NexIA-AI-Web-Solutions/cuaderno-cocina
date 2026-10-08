import {test, expect, type Browser, type BrowserContext, type Page} from '@playwright/test'
import {createHash} from 'node:crypto'
import {chmod, lstat, mkdir, readFile, writeFile} from 'node:fs/promises'
import path from 'node:path'
import {appPath, authFile, editions, parseProject, roles, type Edition, type Identity} from './contracts.js'

const widths = [390, 768, 1024, 1440] as const
const quantities = [
  {input: '400.0000000000000000', raw: '400.0000000000000000', label: '400'},
  {input: '400,5000000000000000', raw: '400.5000000000000000', label: '400,5'},
  {input: '0.0000000000000001', raw: '0.0000000000000001', label: '0,0000000000000001'},
  {input: '9999999999999999.1234567890123456', raw: '9999999999999999.1234567890123456', label: '9999999999999999,1234567890123456'},
] as const
const warning = 'Puedes consultar las mermas. La edición requiere Profesional o Integral y permisos sobre la receta.'
const hash = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex')
const shaPattern = /^[a-f0-9]{64}$/
const sourcePattern = /^[a-f0-9]{40}$/

type Asset = {path: string; sha256: string}
type Binding = {
  schemaVersion: 1; mode: 'isolated-ci-quantity-precision'; repository: string
  sourceCommit: string; sourceIdentity: string; ciRunId: string; ciRunAttempt: string
  imageId: string; imageArchiveSha256: string
  runtime: {webId: string; databaseId: string; imageId: string; sourceCommit: string}
  frontendProvenance: Asset; changedAssetBindings: Asset[]
}
type Ingredient = {
  id: number; food_name: string; amount: string; unit: string
  quantity_basis: string; yield_ratio: null; is_subrecipe: boolean
}
type Envelope = {recipe_id: number; edition: Edition; revision: string; can_edit: boolean; ingredients: Ingredient[]}
type Fixture = {edition: Edition; recipeId: number; unitName: string; foodNames: string[]; ingredientIds: number[]; metadataSha256: string; token: string}
type Bounds = {x: number; y: number; width: number; height: number}
type Viewport = {
  width: number; pass: true; amounts: {ingredientId: number; raw: string; label: string; bounds: Bounds; yieldEnabled: boolean; basisEnabled: boolean}[]
  screenshot: string; sha256: string; bytes: number; pngWidth: number; pngHeight: number; croppedComponent: true
  readonlyWarningVisible: boolean; saveButtons: number; saveButtonsDisabled: boolean
}

function failUnless(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message)
}

function campaign() {
  failUnless(process.env.CI === '1' || process.env.CI === 'true', 'La campaña sólo se ejecuta en CI aislado.')
  failUnless(process.env.CUADERNO_ENV === 'test' && process.env.CUADERNO_E2E_PREFIX === '1', 'Se requiere el preview test prefijado.')
  failUnless(process.env.CUADERNO_E2E_SELF_SIGNED !== '1', 'Se requiere confianza TLS verificada.')
  const base = new URL(process.env.BASE_URL || '')
  failUnless(base.protocol === 'https:' && base.hostname === '127.0.0.1' && base.port &&
    base.pathname === '/cuaderno-cocina/' && !base.username && !base.password && !base.search && !base.hash,
  'El destino debe ser HTTPS loopback con el prefijo exacto.')
  const token = process.env.CUADERNO_QUANTITY_TOKEN || ''
  failUnless(/^[a-zA-Z0-9-]{6,80}$/.test(token), 'Token de campaña inválido.')
  const directory = path.resolve(process.env.CUADERNO_QUANTITY_RUN_DIR || '')
  const allowed = path.resolve(import.meta.dirname, '../../../.cuaderno-runs') + path.sep
  failUnless(directory.startsWith(allowed) && path.basename(directory) === `quantity-${token}`, 'El output sale de .cuaderno-runs/quantity-{token}.')
  return {base, token, directory}
}

async function metadata(): Promise<{binding: Binding; sha256: string}> {
  const file = process.env.CUADERNO_QUANTITY_METADATA || ''
  const expected = process.env.CUADERNO_QUANTITY_METADATA_SHA256 || ''
  failUnless(path.isAbsolute(file) && shaPattern.test(expected), 'Falta metadata con SHA-256 fijado.')
  const stat = await lstat(file)
  failUnless(stat.isFile() && !stat.isSymbolicLink() && stat.size < 1_000_000, 'Metadata no regular o demasiado grande.')
  const bytes = await readFile(file)
  failUnless(hash(bytes) === expected, 'SHA-256 de metadata incorrecto.')
  const binding = JSON.parse(bytes.toString()) as Binding
  failUnless(binding.schemaVersion === 1 && binding.mode === 'isolated-ci-quantity-precision', 'Modo/schema de metadata inválido.')
  failUnless(binding.repository === process.env.GITHUB_REPOSITORY && binding.repository === 'NexIA-AI-Web-Solutions/cuaderno-cocina', 'Repositorio CI no vinculado.')
  failUnless(sourcePattern.test(binding.sourceCommit) && binding.sourceCommit === process.env.GITHUB_SHA &&
    binding.sourceCommit === process.env.CUADERNO_QUANTITY_SOURCE_COMMIT, 'Commit CI/candidato no vinculado.')
  failUnless(typeof binding.sourceIdentity === 'string' && binding.sourceIdentity.startsWith(binding.sourceCommit), 'Identidad fuente inválida.')
  failUnless(/^[1-9][0-9]*$/.test(binding.ciRunId) && binding.ciRunId === process.env.GITHUB_RUN_ID &&
    /^[1-9][0-9]*$/.test(binding.ciRunAttempt) && binding.ciRunAttempt === process.env.GITHUB_RUN_ATTEMPT, 'Run/attempt CI no vinculado.')
  failUnless(/^sha256:[a-f0-9]{64}$/.test(binding.imageId) && binding.imageId === process.env.CUADERNO_CANDIDATE_IMAGE &&
    shaPattern.test(binding.imageArchiveSha256), 'Imagen CI no vinculada.')
  failUnless(shaPattern.test(binding.runtime.webId) && shaPattern.test(binding.runtime.databaseId) &&
    binding.runtime.webId !== binding.runtime.databaseId && binding.runtime.imageId === binding.imageId &&
    binding.runtime.sourceCommit === binding.sourceCommit, 'Runtime nativo no vinculado.')
  const prefix = campaign().base.pathname + 'static/vue3/'
  function asset(value: Asset) {
    failUnless(value && typeof value.path === 'string' && value.path.startsWith(prefix) &&
      !value.path.includes('..') && !/[?#\\\u0000-\u0020]/.test(value.path) && shaPattern.test(value.sha256), 'Asset no vinculado al prefijo.')
  }
  asset(binding.frontendProvenance)
  failUnless(binding.frontendProvenance.path === prefix + 'cuaderno-build-provenance.json', 'Ruta de procedencia incorrecta.')
  failUnless(Array.isArray(binding.changedAssetBindings) && binding.changedAssetBindings.length > 0, 'Faltan los JS modificados.')
  binding.changedAssetBindings.forEach(value => {asset(value); failUnless(value.path.endsWith('.js'), 'El asset modificado debe ser JS.')})
  failUnless(new Set(binding.changedAssetBindings.map(value => value.path)).size === binding.changedAssetBindings.length, 'Assets duplicados.')
  return {binding, sha256: expected}
}

async function writePrivate(filename: string, data: unknown) {
  await writeFile(filename, JSON.stringify(data, null, 2) + '\n', {flag: 'wx', mode: 0o600})
}

async function nativeApi<T>(context: BrowserContext, endpoint: string, status: number, body?: unknown): Promise<T> {
  const {base} = campaign()
  const csrf = (await context.cookies(base.href)).find(cookie => cookie.name === 'cuaderno_csrftoken')
  failUnless(csrf?.value, 'La sesión sintética no contiene CSRF del prefijo.')
  const response = await context.request.fetch(new URL(appPath(endpoint), base).href, {
    method: body === undefined ? 'GET' : 'POST', timeout: 20_000, maxRedirects: 0, failOnStatusCode: false,
    headers: {Accept: 'application/json', 'X-CSRFToken': csrf.value, Origin: base.origin,
      ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
    ...(body === undefined ? {} : {data: JSON.stringify(body)}),
  })
  expect(response.status(), `API nativa ${endpoint}`).toBe(status)
  const result: unknown = await response.json()
  await response.dispose()
  return result as T
}

function validateEnvelope(envelope: Envelope, fixture: Fixture, identity: Identity) {
  expect(envelope.recipe_id).toBe(fixture.recipeId)
  expect(envelope.edition).toBe(identity.edition)
  expect(envelope.revision).toMatch(shaPattern)
  expect(envelope.can_edit).toBe(identity.edition !== 'esencial' && identity.role !== 'consulta')
  expect(envelope.ingredients).toHaveLength(4)
  expect(new Set(envelope.ingredients.map(row => row.id)).size).toBe(4)
  quantities.forEach((quantity, index) => {
    const row = envelope.ingredients.find(item => item.id === fixture.ingredientIds[index])
    expect(row).toEqual({id: fixture.ingredientIds[index], food_name: fixture.foodNames[index], amount: quantity.raw,
      unit: fixture.unitName, quantity_basis: 'gross', yield_ratio: null, is_subrecipe: false})
  })
}

async function fixtureFor(browser: Browser, edition: Edition, bindingHash: string): Promise<Fixture> {
  const {token, directory, base} = campaign()
  const filename = path.join(directory, `fixture-${edition}.json`)
  try {
    const stat = await lstat(filename)
    failUnless(stat.isFile() && !stat.isSymbolicLink(), 'Fixture cache no regular.')
    const fixture = JSON.parse(await readFile(filename, 'utf8')) as Fixture
    failUnless(fixture.edition === edition && fixture.token === token && fixture.metadataSha256 === bindingHash &&
      Number.isSafeInteger(fixture.recipeId) && fixture.recipeId > 0 && fixture.foodNames.length === 4 &&
      fixture.ingredientIds.length === 4, 'Fixture cache no vinculada.')
    return fixture
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
  const owner = await browser.newContext({baseURL: base.href, storageState: authFile(edition, 'responsable'), ignoreHTTPSErrors: false})
  try {
    const tag = `Cuaderno quantity ${token} ${edition}`
    const unitName = `Q${token.slice(-8)} g`
    const unit = await nativeApi<{id: number}>(owner, '/api/unit/', 201, {name: unitName, base_unit: 'g'})
    const foodNames = quantities.map((_quantity, index) => `${tag} ${index + 1}`)
    const foods: {id: number}[] = []
    for (const name of foodNames) foods.push(await nativeApi<{id: number}>(owner, '/api/food/', 201, {name}))
    const recipe = await nativeApi<{id: number}>(owner, '/api/recipe/', 201, {
      name: tag, private: false, servings: 4, steps: [{name: 'Cantidades exactas',
        instruction: 'Fixture sintética en preview CI aislado.', ingredients: quantities.map((quantity, index) => ({
          food: {id: foods[index]!.id, name: foodNames[index]}, unit: {id: unit.id, name: unitName},
          amount: quantity.input, no_amount: false,
        }))}],
    })
    failUnless(Number.isSafeInteger(recipe.id) && recipe.id > 0, 'La API no creó una receta nativa.')
    const envelope = await nativeApi<Envelope>(owner, `/api/cuaderno/recipes/${recipe.id}/ingredient-yields/`, 200)
    const fixture: Fixture = {edition, recipeId: recipe.id, unitName, foodNames,
      ingredientIds: foodNames.map(name => envelope.ingredients.find(row => row.food_name === name)!.id),
      metadataSha256: bindingHash, token}
    validateEnvelope(envelope, fixture, parseProject(`${edition}-responsable-1440`))
    await writePrivate(filename, fixture)
    return fixture
  } finally {
    await owner.close()
  }
}

function strictCollector(page: Page) {
  const failures: string[] = [], warnings: string[] = []
  const pending = new Set<Promise<void>>(), requests = new Set<unknown>(), assets = new Map<string, string>()
  const {base} = campaign()
  page.on('pageerror', error => failures.push(`pageerror: ${error.message.slice(0, 600)}`))
  page.on('console', message => {
    if (message.type() === 'error') failures.push(`console: ${message.text().slice(0, 600)}`)
    if (message.type() === 'warning') warnings.push(message.text().slice(0, 600))
  })
  page.on('request', request => {
    requests.add(request)
    const url = new URL(request.url())
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname)) failures.push(`Fuera de app: ${request.method()} ${url.pathname}`)
  })
  page.on('requestfinished', request => requests.delete(request))
  page.on('requestfailed', request => {
    requests.delete(request)
    failures.push(`network: ${request.method()} ${new URL(request.url()).pathname}: ${request.failure()?.errorText}`)
  })
  page.on('response', response => {
    const url = new URL(response.url())
    if (response.status() >= 400) failures.push(`HTTP ${response.status()} ${response.request().method()} ${url.pathname}`)
    if (url.origin === base.origin && url.pathname.startsWith(base.pathname + 'static/vue3/') && url.pathname.endsWith('.js')) {
      const capture = response.body().then(bytes => {assets.set(url.pathname, hash(bytes))})
        .catch(() => {failures.push(`No se pueden verificar bytes JS: ${url.pathname}`)})
      pending.add(capture)
      void capture.finally(() => pending.delete(capture))
    }
  })
  return {failures, warnings, assets, drain: async () => {
    await expect.poll(() => requests.size, {timeout: 20_000, message: 'Peticiones reales deben terminar sin abortos.'}).toBe(0)
    while (pending.size) await Promise.all([...pending])
    expect(failures, failures.join('\n')).toEqual([])
  }}
}

async function verifyProvenance(context: BrowserContext, binding: Binding) {
  const response = await context.request.get(new URL(binding.frontendProvenance.path, campaign().base).href,
    {maxRedirects: 0, timeout: 20_000, failOnStatusCode: false})
  expect(response.status()).toBe(200)
  const bytes = await response.body()
  expect(hash(bytes)).toBe(binding.frontendProvenance.sha256)
  const provenance = JSON.parse(bytes.toString()) as {
    schema_version: number; rollup: {main: {chunks: {file_name: string; sha256: string; modules: {id: string}[]}[]}}
    final_assets: {file_name: string; sha256: string}[]
  }
  expect(provenance.schema_version).toBe(1)
  const chunks = provenance.rollup.main.chunks.filter(chunk => chunk.modules.some(module =>
    module.id === 'vue:src/cuaderno/components/IngredientYieldPanel.vue' || module.id === 'vue:src/cuaderno/ingredientYieldUi.ts'))
  expect(chunks.length, 'El grafo debe incluir los módulos de etiquetas de merma.').toBeGreaterThan(0)
  const prefix = campaign().base.pathname + 'static/vue3/'
  const expected = chunks.map(chunk => {
    expect(provenance.final_assets).toContainEqual(expect.objectContaining({file_name: chunk.file_name, sha256: chunk.sha256}))
    return {path: prefix + chunk.file_name, sha256: chunk.sha256}
  }).sort((a, b) => a.path.localeCompare(b.path))
  expect([...binding.changedAssetBindings].sort((a, b) => a.path.localeCompare(b.path))).toEqual(expected)
  await response.dispose()
  return bytes
}

// One worker runs the nine configured projects in order. The last project's
// hook checks persisted records and actual PNG bytes, including earlier cases.
test.afterAll(async ({}, testInfo) => {
  const identity = parseProject(testInfo.project.name)
  if (identity.edition !== 'integral' || identity.role !== 'responsable') return
  const {directory, token} = campaign()
  const {binding, sha256} = await metadata()
  const reports: Record<string, unknown>[] = [], screenshots: Record<string, unknown>[] = [], failures: string[] = []
  for (const edition of editions) for (const role of roles) {
    const index = editions.indexOf(edition) * 3 + roles.indexOf(role)
    try {
      const report = JSON.parse(await readFile(path.join(directory, `report-${index}-${edition}-${role}.json`), 'utf8')) as Record<string, unknown>
      failUnless(report.pass === true && report.accountIndex === index && report.edition === edition && report.role === role &&
        report.token === token && report.newCritical12Claimed === false && Array.isArray(report.failures) &&
        report.failures.length === 0, `Caso ${index} no passed/vinculado.`)
      const reportBinding = report.binding as Binding & {metadataSha256: string}
      failUnless(reportBinding.metadataSha256 === sha256 && JSON.stringify(reportBinding) === JSON.stringify({...binding, metadataSha256: sha256}), 'Binding de caso distinto.')
      failUnless(JSON.stringify(report.apiEnvelopeBefore) === JSON.stringify(report.apiEnvelopeAfter), 'La API persistida cambió.')
      const viewports = report.viewports as Viewport[]
      failUnless(viewports.length === 4 && JSON.stringify(viewports.map(row => row.width)) === JSON.stringify(widths), 'La matriz de anchos no es exacta.')
      for (const viewport of viewports) {
        const expectedName = `${index}-${edition}-${role}-${viewport.width}.png`
        failUnless(viewport.pass === true && viewport.croppedComponent === true && viewport.amounts.length === 4 &&
          viewport.screenshot === expectedName, 'Screenshot/viewport no vinculado.')
        const filename = path.join(directory, expectedName), stat = await lstat(filename), bytes = await readFile(filename)
        failUnless(stat.isFile() && !stat.isSymbolicLink() && (stat.mode & 0o777) === 0o600 &&
          bytes.length === viewport.bytes && hash(bytes) === viewport.sha256 && bytes.length > 24 &&
          bytes.subarray(0, 8).toString('hex') === '89504e470d0a1a0a' && bytes.readUInt32BE(16) === viewport.pngWidth &&
          bytes.readUInt32BE(20) === viewport.pngHeight && viewport.pngWidth > 0 && viewport.pngHeight > 0, 'Bytes PNG no verificables.')
        screenshots.push({path: expectedName, sha256: viewport.sha256, bytes: viewport.bytes, viewportWidth: viewport.width,
          width: viewport.pngWidth, height: viewport.pngHeight, croppedComponent: true, mode: '0600'})
      }
      reports.push(report)
    } catch (error) {
      failures.push(`${edition}/${role}: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  const passed = failures.length === 0 && reports.length === 9 && screenshots.length === 36
  await writePrivate(path.join(directory, 'summary.json'), {mode: 'native-quantity-precision', token, passed,
    failed: failures.length, cases: reports.length, expectedCases: 9, expectedScreenshots: 36, reports, screenshots, failures,
    binding: {...binding, metadataSha256: sha256}, newCritical12Claimed: false})
  expect(failures, failures.join('\n')).toEqual([])
  expect(reports).toHaveLength(9)
  expect(screenshots).toHaveLength(36)
})

test('cantidades nativas exactas y merma accesible en cuatro anchos', async ({browser, page}, testInfo) => {
  const {directory, token} = campaign()
  await mkdir(directory, {recursive: true, mode: 0o700})
  await chmod(directory, 0o700)
  const identity = parseProject(testInfo.project.name)
  expect(identity.browser).toBe('chromium')
  expect(identity.width).toBe(1440)
  const accountIndex = editions.indexOf(identity.edition) * 3 + roles.indexOf(identity.role)
  const report: Record<string, unknown> = {mode: 'native-quantity-precision', token, accountIndex,
    edition: identity.edition, role: identity.role, pass: false, failures: [], viewports: [],
    newCritical12Claimed: false, startedAtUnixMs: Date.now()}
  const collector = strictCollector(page)
  try {
    const {binding, sha256} = await metadata()
    report.binding = {...binding, metadataSha256: sha256}
    const provenance = await verifyProvenance(page.context(), binding)
    const fixture = await fixtureFor(browser, identity.edition, sha256)
    report.recipeId = fixture.recipeId
    const endpoint = `/api/cuaderno/recipes/${fixture.recipeId}/ingredient-yields/`
    const before = await nativeApi<Envelope>(page.context(), endpoint, 200)
    validateEnvelope(before, fixture, identity)
    report.apiEnvelopeBefore = before
    report.canEdit = before.can_edit
    await page.goto(appPath(`/recipe/${fixture.recipeId}`))
    await expect(page).not.toHaveURL(/\/accounts\/login\//)
    const panel = page.getByRole('region', {name: 'Mermas de ingredientes'})
    await expect(panel).toBeVisible()
    await expect(panel.locator('.yield-row')).toHaveCount(4)
    await expect(panel.getByRole('status')).toHaveCount(0)
    const viewports: Viewport[] = []
    report.viewports = viewports
    for (const width of widths) {
      await page.setViewportSize({width, height: width === 390 ? 844 : width === 768 ? 1024 : 900})
      await panel.scrollIntoViewIfNeeded()
      await collector.drain()
      const amounts: Viewport['amounts'] = []
      for (let index = 0; index < quantities.length; index += 1) {
        const quantity = quantities[index]!
        const row = panel.locator('.yield-row').filter({has: page.getByText(fixture.foodNames[index]!, {exact: true})})
        await expect(row).toHaveCount(1)
        await expect(row.getByText(quantity.label + ' ' + fixture.unitName, {exact: true})).toBeVisible()
        const input = row.getByRole('textbox', {name: 'Rendimiento (0 a 1)'})
        if (before.can_edit) await expect(input).toBeEnabled()
        else await expect(input).toBeDisabled()
        const basis = row.getByRole('combobox', {name: 'Base de la cantidad'})
        if (before.can_edit) await expect(basis).toBeEnabled()
        else await expect(basis).toBeDisabled()
        const bounds = await row.boundingBox()
        failUnless(bounds, 'La fila no tiene bounds visibles.')
        expect(bounds.x).toBeGreaterThanOrEqual(-1)
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 1)
        const labelBounds = await row.getByText(quantity.label + ' ' + fixture.unitName, {exact: true}).boundingBox()
        failUnless(labelBounds, 'La etiqueta no tiene bounds visibles.')
        expect(labelBounds.x + labelBounds.width).toBeLessThanOrEqual(width + 1)
        amounts.push({ingredientId: fixture.ingredientIds[index]!, raw: quantity.raw, label: quantity.label, bounds,
          yieldEnabled: await input.isEnabled(), basisEnabled: await basis.isEnabled()})
      }
      const save = panel.getByRole('button', {name: 'Guardar merma', exact: true})
      await expect(save).toHaveCount(before.can_edit ? 4 : 0)
      if (before.can_edit) for (const button of await save.all()) await expect(button).toBeDisabled()
      await expect(panel.getByText(warning, {exact: true})).toHaveCount(before.can_edit ? 0 : 1)
      if (!before.can_edit) await expect(panel.getByText(warning, {exact: true})).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
      const screenshot = `${accountIndex}-${identity.edition}-${identity.role}-${width}.png`
      const filename = path.join(directory, screenshot)
      const bytes = await panel.screenshot({path: filename, animations: 'disabled'})
      await chmod(filename, 0o600)
      expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
      viewports.push({width, pass: true, amounts, screenshot, sha256: hash(bytes), bytes: bytes.length,
        pngWidth: bytes.readUInt32BE(16), pngHeight: bytes.readUInt32BE(20), croppedComponent: true,
        readonlyWarningVisible: await panel.getByText(warning, {exact: true}).isVisible(), saveButtons: await save.count(),
        saveButtonsDisabled: (await Promise.all((await save.all()).map(button => button.isDisabled()))).every(Boolean)})
    }
    const after = await nativeApi<Envelope>(page.context(), endpoint, 200)
    validateEnvelope(after, fixture, identity)
    expect(after).toEqual(before)
    report.apiEnvelopeAfter = after
    await collector.drain()
    for (const asset of binding.changedAssetBindings) expect(collector.assets.get(asset.path), `JS real ${asset.path}`).toBe(asset.sha256)
    report.assetBindings = [...collector.assets].map(([assetPath, sha256]) => ({path: assetPath, sha256}))
    report.frontendProvenanceSha256 = binding.frontendProvenance.sha256
    // The complete sanitized build graph contains no browser/session state.
    if (accountIndex === 0) await writeFile(path.join(directory, 'frontend-provenance.json'), provenance, {flag: 'wx', mode: 0o600})
    expect(viewports).toHaveLength(4)
    report.pass = true
  } catch (error) {
    report.error = error instanceof Error ? error.message : String(error)
    throw error
  } finally {
    report.failures = collector.failures
    report.warnings = collector.warnings
    report.completedAtUnixMs = Date.now()
    await writePrivate(path.join(directory, `report-${accountIndex}-${identity.edition}-${identity.role}.json`), report)
  }
})
