import {randomUUID} from 'node:crypto'
import {request, type Locator, type Page, type TestInfo} from '@playwright/test'
import {appPath, authFile, fixturePrefix, type Identity} from './contracts.js'
import {api, assertNoHorizontalOverflow, enterApp, expect, rows, test} from './fixtures.js'
import {withNativeReadBarrier} from './native-read-barrier.js'

// Real DOM + native APIs against the guarded, disposable CUADERNO-E2E seed.
// No routing, response replacement, worker override or browser-error exemptions.
type Recipe = {id: number; name: string}
type Extras = {revision: string; is_favorite: boolean; can_edit: boolean; diets: {slug: string; label: string; status: string; note: string}[]; gallery: {id: number; url: string; caption: string}[]; variant_of: Recipe | null; variants: Recipe[]}
type Meal = {id: number; title: string; recipe: Recipe | null; meal_type: {id: number; name: string}; from_date: string; course: number | null; diet_status: string}
type Planning = {meal_plans: Meal[]; courses: {id: number; name: string; revision: string}[]; events: {id: number; title: string; kind: string; revision: string}[]; can_edit: boolean; can_manage_absences: boolean; can_merge_print: boolean}
type Template = {id: number; name: string; weeks: number; revision: string; entries: {recipe: number; day_index: number; meal_type: number}[]}
const slugs = ['celiacos', 'colesterol', 'diabetes', 'hiposodica', 'gastrica', 'fibra', 'sinfructosa', 'sinlactosa']
const farDate = '2041-04-01'
// Native retrieve/delete applies its default date filter even to an exact ID.
const nativePlanPath = (id: number) => `/api/meal-plan/${id}/?from_date=2000-01-01&to_date=2050-01-01`

async function start(page: Page, identity: Identity) {
  expect(fixturePrefix, 'this mutating suite requires the isolated CI seed').toBe('CUADERNO-E2E')
  expect(identity.username).toBe(`demo-${identity.edition}-${identity.role}`)
  await enterApp(page)
  const edition = await api<{edition: string; operational_role: {code: string}}>(page, '/api/cuaderno/edition/')
  expect(edition.status).toBe(200)
  expect(edition.body.edition).toBe(identity.edition)
  expect(edition.body.operational_role.code).toBe({consulta: 'guest', cocina: 'user', responsable: 'admin'}[identity.role])
}
function marker(info: TestInfo) {return `${fixturePrefix} extras ${info.project.name} ${randomUUID().slice(0, 8)}`}
async function readExtras(page: Page, id: number) {
  const result = await api<Extras>(page, `/api/cuaderno/recipes/${id}/extras/`)
  expect(result.status).toBe(200); return result.body
}
async function publicSeed(page: Page) {
  const result = await api(page, `/api/recipe/?query=${encodeURIComponent(fixturePrefix + ' receta pública')}&page_size=100`)
  expect(result.status).toBe(200)
  const found = rows(result.body).filter(row => row.name === `${fixturePrefix} receta pública`)
  expect(found).toHaveLength(1)
  expect(Number.isSafeInteger(found[0]!.id)).toBe(true)
  return {id: Number(found[0]!.id), name: String(found[0]!.name)}
}
async function createRecipe(page: Page, name: string) {
  expect(name.startsWith(`${fixturePrefix} extras `)).toBe(true)
  const result = await api<Recipe>(page, '/api/recipe/', {method: 'POST', body: {name, private: true, servings: 4, steps: []}})
  expect(result.status).toBe(201); expect(result.body.name).toBe(name); return {id: result.body.id, name: result.body.name}
}
async function removeRecipe(page: Page, recipe: Recipe) {
  const current = await api<Recipe>(page, `/api/recipe/${recipe.id}/`)
  expect(current.status).toBe(200); expect(current.body.name).toBe(recipe.name)
  expect(recipe.name.startsWith(`${fixturePrefix} extras `)).toBe(true)
  expect((await api(page, `/api/recipe/${recipe.id}/`, {method: 'DELETE'})).status).toBe(204)
}
async function observe<T>(page: Page, path: string, method: string, action: () => Promise<unknown>, status = 200): Promise<T> {
  const pending = page.waitForResponse(response => new URL(response.url()).pathname === appPath(path) && response.request().method() === method, {timeout: 8_000})
  void pending.catch(() => {})
  await action()
  const response = await pending
  expect(response.status(), `${method} ${path}`).toBe(status)
  expect(await response.finished()).toBeNull()
  return (status === 204 ? null : await response.json()) as T
}
async function select(page: Page, control: Locator, option: string) {
  await expect(control).toBeEnabled()
  await control.focus(); await control.press('Enter')
  await expect(control).toHaveAttribute('aria-expanded', 'true')
  await page.getByRole('option', {name: option, exact: true}).click()
}
async function recipePage(page: Page, recipe: Recipe) {
  await observe(page, '/api/view-log/', 'POST', () => page.goto(appPath(`/recipe/${recipe.id}`)), 201)
  const panel = page.locator('.recipe-extras')
  await expect(panel.getByRole('heading', {name: 'Fotos, variantes y dietas'})).toBeVisible()
  await expect(panel.getByRole('button', {name: /^(Guardar en favoritas|En mis favoritas)$/})).toBeVisible()
  return panel
}
async function planningPage(page: Page, date?: string) {
  await withNativeReadBarrier(page, async () => {
    await page.goto(appPath('/cuaderno/planificacion'))
    await expect(page.getByRole('heading', {name: 'Organización de menús'})).toBeVisible()
    const settled = page.getByText(/^(Periodo cargado:|La organización profesional de menús está disponible)/)
    await expect(settled).toBeVisible()
    await expect(settled).not.toContainText('pendiente')
  })
  if (date) {
    await expect(page.getByRole('button', {name: 'Actualizar periodo', exact: true})).toBeVisible()
    await expect(page.getByText(/Periodo cargado:/)).not.toContainText('pendiente')
    await page.getByLabel('Primer día', {exact: true}).fill(date)
    await observe<Planning>(page, '/api/cuaderno/planning/', 'GET', () => page.getByRole('button', {name: 'Actualizar periodo', exact: true}).click())
    await expect(page.getByText(/Periodo cargado:/)).toContainText(date)
  }
}
async function planningRead(page: Page, date: string) {
  const result = await api<Planning>(page, `/api/cuaderno/planning/?from_date=${date}&to_date=${date}`)
  expect(result.status).toBe(200); return result.body
}
async function createPlan(page: Page, recipe: Recipe, date: string) {
  const result = await api(page, `/api/meal-type/?query=${encodeURIComponent(fixturePrefix + ' servicio')}&page_size=100`)
  expect(result.status).toBe(200)
  const types = rows(result.body).filter(row => row.name === `${fixturePrefix} servicio`)
  expect(types).toHaveLength(1)
  const type = types[0] as {id: number; name: string}
  const created = await api<Meal>(page, '/api/meal-plan/', {method: 'POST', body: {title: recipe.name, recipe: {id: recipe.id, name: recipe.name}, servings: 4, from_date: `${date}T12:00:00+02:00`, to_date: `${date}T12:00:00+02:00`, meal_type: type}})
  expect(created.status).toBe(201); return {id: created.body.id, title: recipe.name, recipe, meal_type: type}
}
async function removePlan(page: Page, id: number, recipe: Recipe) {
  const row = await api<Meal>(page, nativePlanPath(id))
  expect(row.status).toBe(200); expect(row.body.recipe?.id).toBe(recipe.id)
  expect(row.body.title).toBe(recipe.name)
  expect((await api(page, nativePlanPath(id), {method: 'DELETE'})).status).toBe(204)
}
async function declareUnsuitable(page: Page, recipe: Recipe) {
  const before = await readExtras(page, recipe.id)
  expect((await api(page, `/api/cuaderno/recipes/${recipe.id}/extras/`, {method: 'PUT', body: {revision: before.revision, diets: [{slug: 'celiacos', status: 'unsuitable', note: 'Declaración sintética de CI'}]}})).status).toBe(200)
}

// Every edition, role and viewport: real personal mutation, not shared recipe CRUD.
test('extras: favorita personal persiste y ocho dietas empiezan desconocidas', async ({cleanPage: page, identity}, info) => {
  await start(page, identity)
  const recipe = await publicSeed(page), before = await readExtras(page, recipe.id)
  expect(before.diets.map(row => row.slug)).toEqual(slugs)
  expect(before.diets.every(row => row.status === 'unknown')).toBe(true)
  const peerRole = identity.role === 'consulta' ? 'responsable' : 'consulta'
  const peer = await request.newContext({baseURL: process.env.BASE_URL || 'http://127.0.0.1:18081', storageState: authFile(identity.edition, peerRole), ignoreHTTPSErrors: process.env.CUADERNO_E2E_SELF_SIGNED === '1'})
  const peerRead = async () => {const response = await peer.get(appPath(`/api/cuaderno/recipes/${recipe.id}/extras/`)); expect(response.status()).toBe(200); return (await response.json()) as Extras}
  const peerBefore = await peerRead()
  try {
    expect((await api(page, `/api/cuaderno/recipes/${recipe.id}/favorite/`, {method: 'PUT', body: {favorite: false}})).status).toBe(200)
    const panel = await recipePage(page, recipe)
    if (identity.role === 'consulta') {
      await expect(panel.getByRole('button', {name: 'Guardar declaraciones'})).toHaveCount(0)
      await expect(panel.locator('.diet-row .v-chip')).toHaveText(Array(8).fill('No declarado'))
      const denied = await api(page, `/api/cuaderno/recipes/${recipe.id}/extras/`, {method: 'PUT', body: {revision: before.revision, diets: [{slug: 'celiacos', status: 'suitable', note: ''}]}})
      expect(denied.status).toBe(403)
    } else {
      await expect(panel.getByRole('combobox', {name: /^Declaración:/})).toHaveCount(8)
      await expect(panel.locator('.v-select__selection-text')).toHaveText(Array(8).fill('No declarado'))
    }
    await observe(page, `/api/cuaderno/recipes/${recipe.id}/favorite/`, 'PUT', () => panel.getByRole('button', {name: 'Guardar en favoritas', exact: true}).click())
    await page.reload(); await expect(panel.getByRole('button', {name: 'En mis favoritas', exact: true})).toHaveAttribute('aria-pressed', 'true')
    await page.goto(appPath('/cuaderno/favoritas'))
    await expect(page.getByRole('heading', {name: 'Recetas favoritas'})).toBeVisible()
    await expect(page.locator(`a[href="${appPath(`/recipe/${recipe.id}`)}"]`).filter({hasText: recipe.name})).toBeVisible()
    expect((await peerRead()).is_favorite).toBe(peerBefore.is_favorite)
    await assertNoHorizontalOverflow(page, info)
  } finally {
    try {expect((await api(page, `/api/cuaderno/recipes/${recipe.id}/favorite/`, {method: 'PUT', body: {favorite: before.is_favorite}})).status).toBe(200)} finally {await peer.dispose()}
  }
})

test('extras: operador guarda dieta y foto real, recarga y elimina solo su foto', async ({cleanPage: page, identity}, info) => {
  await start(page, identity)
  if (identity.role === 'consulta') {
    const recipe = await publicSeed(page), panel = await recipePage(page, recipe)
    await expect(panel.locator('input[type="file"]')).toHaveCount(0)
    await expect(panel.getByRole('button', {name: 'Guardar declaraciones', exact: true})).toHaveCount(0)
    expect((await readExtras(page, recipe.id)).can_edit).toBe(false)
    expect((await api(page, `/api/cuaderno/recipes/${recipe.id}/gallery/`, {method: 'POST'})).status).toBe(403)
    return
  }
  const recipe = await createRecipe(page, marker(info))
  try {
    let panel = await recipePage(page, recipe)
    await select(page, panel.getByRole('combobox', {name: 'Declaración: Celíacos', exact: true}), 'No apto · declaración manual')
    await panel.getByLabel('Nota: Celíacos', {exact: true}).fill('Prueba sintética; revisar ingredientes')
    await observe(page, `/api/cuaderno/recipes/${recipe.id}/extras/`, 'PUT', () => panel.getByRole('button', {name: 'Guardar declaraciones', exact: true}).click())
    const png = await page.evaluate(() => {const canvas = document.createElement('canvas'); canvas.width = canvas.height = 4; const context = canvas.getContext('2d')!; context.fillStyle = '#b98766'; context.fillRect(0, 0, 4, 4); return canvas.toDataURL('image/png').split(',')[1]!})
    await panel.locator('input[type="file"]').setInputFiles({name: 'ci-recipe.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64')})
    await panel.getByLabel('Descripción de la foto', {exact: true}).fill(recipe.name)
    const uploaded = await observe<Extras>(page, `/api/cuaderno/recipes/${recipe.id}/gallery/`, 'POST', () => panel.getByRole('button', {name: 'Añadir foto', exact: true}).click(), 201)
    expect(uploaded.gallery).toHaveLength(1)
    await page.reload(); panel = page.locator('.recipe-extras')
    await expect(panel.getByLabel('Nota: Celíacos', {exact: true})).toHaveValue('Prueba sintética; revisar ingredientes')
    await expect(panel.locator('.v-select__selection-text').first()).toHaveText('No apto · declaración manual')
    const image = panel.locator('img')
    await expect(image).toHaveCount(1); await expect(image).toHaveAttribute('alt', recipe.name)
    await expect(image).toBeVisible()
    await expect.poll(() => image.evaluate(element => element instanceof HTMLImageElement && element.complete && element.naturalWidth > 0)).toBe(true)
    expect((await page.context().request.get(new URL(uploaded.gallery[0]!.url, page.url()).href)).status()).toBe(200)
    await panel.getByRole('button', {name: `Eliminar foto: ${recipe.name}`, exact: true}).click()
    await observe(page, `/api/cuaderno/recipes/${recipe.id}/gallery/${uploaded.gallery[0]!.id}/`, 'DELETE', () => page.getByRole('dialog').getByRole('button', {name: 'Eliminar foto', exact: true}).click())
    await page.reload(); await expect(page.locator('.recipe-extras').getByText('Todavía no hay fotos adicionales.', {exact: true})).toBeVisible()
    const restored = await readExtras(page, recipe.id)
    expect(restored.gallery).toEqual([])
    expect((await api(page, `/api/cuaderno/recipes/${recipe.id}/extras/`, {method: 'PUT', body: {revision: restored.revision, diets: restored.diets.map(row => ({slug: row.slug, status: 'unknown', note: ''}))}})).status).toBe(200)
    expect((await readExtras(page, recipe.id)).diets.every(row => row.status === 'unknown')).toBe(true)
  } finally {await removeRecipe(page, recipe)}
})

test('extras: variante usa la copia nativa y conserva el vínculo tras recarga', async ({cleanPage: page, identity}, info) => {
  await start(page, identity)
  if (identity.role === 'consulta') {
    const recipe = await publicSeed(page)
    await recipePage(page, recipe)
    await page.locator('button').filter({has: page.locator('.fa-ellipsis-v')}).filter({visible: true}).first().click()
    await expect(page.getByText('Crear variante vinculada', {exact: true})).toHaveCount(0)
    await page.keyboard.press('Escape')
    expect((await api(page, '/api/recipe/', {method: 'POST', body: {name: marker(info), private: true, servings: 4, steps: []}})).status).toBe(403)
    return
  }
  const recipe = await createRecipe(page, marker(info)); let copy: Recipe | undefined
  try {
    await recipePage(page, recipe)
    const menu = page.locator('button').filter({has: page.locator('.fa-ellipsis-v')}).filter({visible: true}).first()
    await menu.click()
    const created = await observe<Recipe>(page, '/api/recipe/', 'POST', () => page.getByText('Crear variante vinculada', {exact: true}).click(), 201)
    copy = {id: created.id, name: created.name}
    expect(copy.id).not.toBe(recipe.id); expect(copy.name.startsWith(recipe.name)).toBe(true)
    await expect(page).toHaveURL(new RegExp(`${appPath('/recipe/')}${copy.id}/?$`))
    await expect(page.locator('.recipe-extras').getByRole('link', {name: recipe.name, exact: true})).toBeVisible()
    await page.reload()
    expect((await readExtras(page, copy.id)).variant_of).toEqual(recipe)
    expect((await readExtras(page, recipe.id)).variants).toContainEqual(copy)
  } finally {try {if (copy) await removeRecipe(page, copy)} finally {await removeRecipe(page, recipe)}}
})

test('planificación: calendario nativo cinco semanas, filtro real y límite de edición', async ({cleanPage: page, identity}, info) => {
  await start(page, identity)
  const professional = identity.edition !== 'esencial'
  let recipe: Recipe | undefined, planId: number | undefined
  try {
    if (professional && identity.role !== 'consulta') {
      recipe = await createRecipe(page, marker(info))
      const today = await page.evaluate(() => {const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`})
      planId = (await createPlan(page, recipe, today)).id
      await declareUnsuitable(page, recipe)
    }
    await page.goto(appPath('/mealplan'))
    await select(page, page.getByRole('combobox', {name: 'Vista de 1 a 5 semanas', exact: true}), '5')
    await expect(page.locator('.cuaderno-calendar .cv-week')).toHaveCount(5)
    await expect(page.locator('.cuaderno-calendar .cv-day')).toHaveCount(35)
    if (professional) {
      await expect(page.getByRole('link', {name: 'Plantillas y organización', exact: true})).toBeVisible()
      await select(page, page.getByRole('combobox', {name: 'Consultar dieta', exact: true}), 'Celíacos')
      if (recipe) {
        const item = page.locator('.cuaderno-calendar .cv-item').filter({hasText: recipe.name})
        await expect(item).toHaveClass(/diet-unsuitable/)
        await expect(item).toContainText('No apto · declaración manual')
        await page.getByRole('checkbox', {name: 'Solo aptos declarados', exact: true}).check()
        await expect(item).toHaveCount(0)
        await page.getByRole('checkbox', {name: 'Solo aptos declarados', exact: true}).uncheck()
        await expect(item).toBeVisible()
      }
    } else await expect(page.getByRole('combobox', {name: 'Consultar dieta', exact: true})).toHaveCount(0)
    await planningPage(page)
    if (!professional) {
      await expect(page.getByText(/organización profesional de menús está disponible/)).toBeVisible()
      await expect(page.getByRole('tab', {name: 'Plantillas', exact: true})).toHaveCount(0)
      expect((await api(page, `/api/cuaderno/planning/?from_date=${farDate}&to_date=${farDate}`)).status).toBe(403)
    } else {
      await expect(page.getByRole('tab', {name: 'Plantillas', exact: true})).toBeVisible()
      if (identity.role === 'consulta') await expect(page.getByRole('button', {name: 'Guardar nueva plantilla', exact: true})).toBeDisabled()
    }
    await assertNoHorizontalOverflow(page, info)
  } finally {if (recipe) {try {if (planId) await removePlan(page, planId, recipe)} finally {await removeRecipe(page, recipe)}}}
})

test('planificación: tipo de plato creado en UI se asigna a MealPlan nativo', async ({cleanPage: page, identity}, info) => {
  await start(page, identity)
  if (identity.edition === 'esencial' || identity.role === 'consulta') {
    await planningPage(page)
    if (identity.edition === 'esencial') {
      await expect(page.getByText(/organización profesional de menús está disponible/)).toBeVisible()
      await expect(page.getByRole('tab', {name: 'Tipos de plato', exact: true})).toHaveCount(0)
    } else {
      await page.getByRole('tab', {name: 'Tipos de plato', exact: true}).click()
      await expect(page.getByLabel('Nombre', {exact: true})).toBeDisabled()
      await expect(page.getByRole('button', {name: 'Añadir tipo de plato', exact: true})).toBeDisabled()
    }
    expect((await api(page, '/api/cuaderno/planning/courses/', {method: 'POST', body: {name: marker(info), meal_type: 1, position: 0}})).status).toBe(403)
    return
  }
  const recipe = await createRecipe(page, marker(info)); let planId: number | undefined, courseId: number | undefined
  try {
    const plan = await createPlan(page, recipe, farDate); planId = plan.id
    await planningPage(page, farDate)
    await page.getByRole('tab', {name: 'Tipos de plato', exact: true}).click()
    await page.getByLabel('Nombre', {exact: true}).fill(recipe.name)
    const type = page.getByRole('combobox', {name: 'Comida', exact: true})
    await type.fill(plan.meal_type.name)
    await page.getByRole('option', {name: plan.meal_type.name, exact: true}).click()
    const course = await observe<{id: number}>(page, '/api/cuaderno/planning/courses/', 'POST', () => page.getByRole('button', {name: 'Añadir tipo de plato', exact: true}).click(), 201)
    courseId = course.id
    const card = page.locator('.v-card').filter({has: page.getByText(recipe.name, {exact: true})}).filter({has: page.getByRole('combobox', {name: 'Tipo de plato', exact: true})})
    await observe(page, `/api/cuaderno/planning/meal-plans/${plan.id}/`, 'PUT', () => select(page, card.getByRole('combobox', {name: 'Tipo de plato', exact: true}), recipe.name))
    await planningPage(page, farDate); await page.getByRole('tab', {name: 'Tipos de plato', exact: true}).click()
    await expect(page.locator('.v-card').filter({has: page.getByText(recipe.name, {exact: true})}).filter({has: page.getByRole('combobox', {name: 'Tipo de plato', exact: true})}).locator('.v-select__selection-text')).toHaveText(recipe.name)
    const stored = (await planningRead(page, farDate)).meal_plans.find(row => row.id === plan.id)
    expect(stored?.course).toBe(course.id)
    expect((await api<Meal>(page, nativePlanPath(plan.id))).body.recipe?.id).toBe(recipe.id)
  } finally {
    try {if (planId) await removePlan(page, planId, recipe)} finally {
      try {if (courseId) {const row = (await planningRead(page, farDate)).courses.find(row => row.id === courseId); expect(row?.name).toBe(recipe.name); expect((await api(page, `/api/cuaderno/planning/courses/${courseId}/?revision=${row!.revision}`, {method: 'DELETE'})).status).toBe(204)}} finally {await removeRecipe(page, recipe)}
    }
  }
})

test('planificación: eventos persisten y solo Responsable puede anotar ausencias', async ({cleanPage: page, identity}, info) => {
  await start(page, identity)
  if (identity.edition === 'esencial') {
    await planningPage(page)
    await expect(page.getByText(/organización profesional de menús está disponible/)).toBeVisible()
    await expect(page.getByRole('tab', {name: 'Eventos y ausencias', exact: true})).toHaveCount(0)
    expect((await api(page, '/api/cuaderno/planning/events/', {method: 'POST', body: {kind: 'event', title: marker(info), member_name: '', start_date: farDate, end_date: farDate, note: ''}})).status).toBe(403)
    return
  }
  const name = marker(info), eventIds: number[] = []
  try {
    await planningPage(page, farDate)
    await page.getByRole('tab', {name: 'Eventos y ausencias', exact: true}).click()
    if (identity.role === 'consulta') {
      await expect(page.getByRole('button', {name: 'Guardar anotación', exact: true})).toBeDisabled()
      expect((await api(page, '/api/cuaderno/planning/events/', {method: 'POST', body: {kind: 'event', title: name, member_name: '', start_date: farDate, end_date: farDate, note: ''}})).status).toBe(403)
      return
    }
    await page.getByLabel('Título', {exact: true}).fill(name)
    await page.getByLabel('Desde', {exact: true}).fill(farDate); await page.getByLabel('Hasta', {exact: true}).fill(farDate)
    eventIds.push((await observe<{id: number}>(page, '/api/cuaderno/planning/events/', 'POST', () => page.getByRole('button', {name: 'Guardar anotación', exact: true}).click(), 201)).id)
    if (identity.role === 'responsable') {
      await select(page, page.getByRole('combobox', {name: 'Tipo', exact: true}), 'Ausencia')
      await page.getByLabel('Título', {exact: true}).fill(name + ' ausencia')
      await page.getByLabel('Persona del equipo', {exact: true}).fill('Persona sintética CI')
      await page.getByLabel('Desde', {exact: true}).fill(farDate); await page.getByLabel('Hasta', {exact: true}).fill(farDate)
      eventIds.push((await observe<{id: number}>(page, '/api/cuaderno/planning/events/', 'POST', () => page.getByRole('button', {name: 'Guardar anotación', exact: true}).click(), 201)).id)
    } else {
      const type = page.getByRole('combobox', {name: 'Tipo', exact: true})
      await type.focus(); await type.press('Enter')
      await expect(page.getByRole('option', {name: 'Ausencia', exact: true})).toHaveCount(0)
      await type.press('Escape')
      expect((await api(page, '/api/cuaderno/planning/events/', {method: 'POST', body: {kind: 'absence', title: name + ' denegada', member_name: 'Persona sintética CI', start_date: farDate, end_date: farDate, note: ''}})).status).toBe(403)
    }
    await planningPage(page, farDate); await page.getByRole('tab', {name: 'Eventos y ausencias', exact: true}).click()
    await expect(page.getByText(name, {exact: true})).toBeVisible()
    const stored = (await planningRead(page, farDate)).events.filter(row => eventIds.includes(row.id))
    expect(stored.map(row => row.kind).sort()).toEqual(identity.role === 'responsable' ? ['absence', 'event'] : ['event'])
  } finally {
    const own = (await planningRead(page, farDate)).events.filter(row => eventIds.includes(row.id))
    expect(own).toHaveLength(eventIds.length)
    for (const row of own) {expect(row.title.startsWith(name)).toBe(true); expect((await api(page, `/api/cuaderno/planning/events/${row.id}/?revision=${row.revision}`, {method: 'DELETE'})).status).toBe(204)}
  }
})

test('planificación: captura cinco semanas y aplica una plantilla en el calendario nativo', async ({cleanPage: page, identity}, info) => {
  await start(page, identity)
  if (identity.edition === 'esencial' || identity.role === 'consulta') {
    await planningPage(page)
    if (identity.edition === 'esencial') {
      await expect(page.getByText(/organización profesional de menús está disponible/)).toBeVisible()
      await expect(page.getByRole('tab', {name: 'Plantillas', exact: true})).toHaveCount(0)
    } else {
      await expect(page.getByLabel('Nombre de la plantilla', {exact: true})).toBeDisabled()
      await expect(page.getByRole('button', {name: 'Guardar nueva plantilla', exact: true})).toBeDisabled()
    }
    expect((await api(page, '/api/cuaderno/planning/templates/', {method: 'POST', body: {name: marker(info), weeks: 1, entries: [{day_index: 0, meal_type: 1, recipe: null, title: 'Entrada sintética denegada', servings: '1'}]}})).status).toBe(403)
    return
  }
  const recipe = await createRecipe(page, marker(info)); let originalId: number | undefined, templateId: number | undefined; const createdIds: number[] = []
  try {
    originalId = (await createPlan(page, recipe, farDate)).id
    await planningPage(page, farDate)
    await select(page, page.getByRole('combobox', {name: 'Semanas', exact: true}), '5')
    await observe(page, '/api/cuaderno/planning/', 'GET', () => page.getByRole('button', {name: 'Actualizar periodo', exact: true}).click())
    await page.getByLabel('Nombre de la plantilla', {exact: true}).fill(recipe.name)
    const template = await observe<Template>(page, '/api/cuaderno/planning/templates/', 'POST', () => page.getByRole('button', {name: 'Guardar nueva plantilla', exact: true}).click(), 201)
    templateId = template.id; expect(template.weeks).toBe(5); expect(template.entries).toHaveLength(1); expect(template.entries[0]!.recipe).toBe(recipe.id)
    const card = page.locator('.v-card').filter({hasText: recipe.name}).filter({has: page.getByRole('button', {name: 'Aplicar al calendario', exact: true})})
    await card.getByRole('button', {name: 'Aplicar al calendario', exact: true}).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Primer día de la plantilla', {exact: true}).fill('2041-06-01')
    const applied = await observe<{created_ids: number[]; replaced_ids: number[]}>(page, `/api/cuaderno/planning/templates/${template.id}/apply/`, 'POST', () => dialog.getByRole('button', {name: 'Aplicar plantilla', exact: true}).click(), 201)
    createdIds.push(...applied.created_ids); expect(createdIds).toHaveLength(1); expect(applied.replaced_ids).toEqual([])
    await expect(dialog).not.toBeVisible()
    const native = await api<Meal>(page, nativePlanPath(createdIds[0]!))
    expect(native.status).toBe(200); expect(native.body.recipe?.id).toBe(recipe.id); expect(native.body.from_date.slice(0, 10)).toBe('2041-06-01')
    await page.getByLabel('Primer día', {exact: true}).fill('2041-06-01')
    await observe(page, '/api/cuaderno/planning/', 'GET', () => page.getByRole('button', {name: 'Actualizar periodo', exact: true}).click())
    await page.getByRole('tab', {name: 'Tipos de plato', exact: true}).click()
    await expect(page.locator('.v-card').getByText(recipe.name, {exact: true}).filter({visible: true})).toBeVisible()
  } finally {
    try {for (const id of createdIds) await removePlan(page, id, recipe); if (originalId) await removePlan(page, originalId, recipe)} finally {
      try {if (templateId) {const current = await api<Template>(page, `/api/cuaderno/planning/templates/${templateId}/`); expect(current.status).toBe(200); expect(current.body.name).toBe(recipe.name); expect((await api(page, `/api/cuaderno/planning/templates/${templateId}/?revision=${current.body.revision}`, {method: 'DELETE'})).status).toBe(204)}} finally {await removeRecipe(page, recipe)}
    }
  }
})

test('planificación: documento autorizado vertical/horizontal y unión solo Integral', async ({cleanPage: page, identity}, info) => {
  await start(page, identity)
  if (identity.edition === 'esencial') {
    await planningPage(page)
    await expect(page.getByText(/organización profesional de menús está disponible/)).toBeVisible()
    await expect(page.getByRole('tab', {name: 'Impresión', exact: true})).toHaveCount(0)
    expect((await api(page, '/api/cuaderno/planning/print/', {method: 'POST', body: {orientation: 'portrait', menus: [{name: 'Documento sintético denegado', meal_plan_ids: [1]}]}})).status).toBe(403)
    return
  }
  const seed = await publicSeed(page)
  const native = await api(page, '/api/meal-plan/?page_size=100')
  expect(native.status).toBe(200)
  const seedPlans = rows(native.body).filter(row => (row.recipe as Recipe | null)?.id === seed.id)
  expect(seedPlans).toHaveLength(2)
  const seedDate = String(seedPlans[0]!.from_date).slice(0, 10)
  await planningPage(page, seedDate)
  await page.getByRole('tab', {name: 'Impresión', exact: true}).click()
  const selection = page.getByRole('combobox', {name: 'Platos del periodo', exact: true})
  await selection.focus(); await selection.press('Enter')
  const options = page.getByRole('option').filter({hasText: `${fixturePrefix} receta pública`})
  await expect(options).toHaveCount(2)
  await options.nth(0).click(); await selection.press('Escape')
  await page.getByLabel('Nombre del menú', {exact: true}).fill('Menú sintético uno')
  await page.getByRole('button', {name: 'Añadir menú a la impresión', exact: true}).click()
  if (identity.edition === 'integral') {
    await selection.focus(); await selection.press('Enter'); await options.nth(1).click(); await selection.press('Escape')
    await page.getByLabel('Nombre del menú', {exact: true}).fill('Menú sintético dos')
    await page.getByRole('button', {name: 'Añadir menú a la impresión', exact: true}).click()
  } else await expect(page.getByRole('button', {name: 'Añadir menú a la impresión', exact: true})).toBeDisabled()
  await select(page, page.getByRole('combobox', {name: 'Declaración dietética en el documento (opcional)', exact: true}), 'Celíacos')
  for (const orientation of ['portrait', 'landscape'] as const) {
    await select(page, page.getByRole('combobox', {name: 'Orientación', exact: true}), orientation === 'portrait' ? 'Vertical' : 'Horizontal')
    const document = await observe<{orientation: string; merged: boolean; diet: string; menus: {name: string; entries: Meal[]}[]}>(page, '/api/cuaderno/planning/print/', 'POST', () => page.getByRole('button', {name: 'Preparar documento', exact: true}).click())
    expect(document.orientation).toBe(orientation); expect(document.diet).toBe('celiacos'); expect(document.merged).toBe(identity.edition === 'integral')
    expect(document.menus).toHaveLength(identity.edition === 'integral' ? 2 : 1)
    expect(document.menus.every(menu => menu.entries.length === 1 && menu.entries[0]!.recipe?.name === `${fixturePrefix} receta pública`)).toBe(true)
    const printed = page.getByRole('region', {name: 'Documento de menús'})
    await expect(printed.locator('article')).toHaveCount(document.menus.length)
    await expect(printed.getByText('No declarado', {exact: true})).toHaveCount(document.menus.length)
    await printed.getByRole('button', {name: orientation === 'portrait' ? 'Imprimir en vertical' : 'Imprimir en horizontal', exact: true}).click()
    expect(await page.locator('head style').allTextContents()).toContain(`@page {size: A4 ${orientation}; margin: 12mm}`)
    await page.emulateMedia({media: 'print'}); await expect(printed.locator('table').first()).toBeVisible()
    await expect(page.getByRole('tab', {name: 'Impresión', exact: true})).toBeHidden()
    await page.emulateMedia({media: 'screen'})
  }
  if (identity.edition === 'profesional') {
    const today = await page.getByLabel('Primer día', {exact: true}).inputValue()
    const plans = (await planningRead(page, today)).meal_plans.filter(row => row.recipe?.name === `${fixturePrefix} receta pública`)
    expect(plans).toHaveLength(2)
    expect((await api(page, '/api/cuaderno/planning/print/', {method: 'POST', body: {orientation: 'portrait', menus: plans.map((row, index) => ({name: `Denegado ${index}`, meal_plan_ids: [row.id]}))}})).status).toBe(403)
  }
  await assertNoHorizontalOverflow(page, info)
})
