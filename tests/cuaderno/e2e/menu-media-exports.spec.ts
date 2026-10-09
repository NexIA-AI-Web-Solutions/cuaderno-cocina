import {randomUUID} from 'node:crypto'
import {readFile} from 'node:fs/promises'
import {fileURLToPath} from 'node:url'
import {type Browser, type Download, type Locator, type Page, type TestInfo} from '@playwright/test'
import {appPath, authFile, fixturePrefix, type Identity} from './contracts.js'
import {api, assertNoHorizontalOverflow, collectBrowserFailures, enterApp, expect, rows, test} from './fixtures.js'
import {withAuthenticatedReadBarrier} from './native-read-barrier.js'

// Real browser, upload/download streams and native APIs. No HTTP mocks or
// exemptions from the shared console/network collector. Only disposable CI seed.
const tomatoes = fileURLToPath(new URL('./assets/menu-media/mock-tomatoes.jpg', import.meta.url))
const coverFile = fileURLToPath(new URL('./assets/menu-media/mock-menu-cover.jpg', import.meta.url))
const date = '2041-10-09'
const viewports = [{width:390,height:844},{width:768,height:1024},{width:1024,height:768},{width:1440,height:900}]
type Named = {id:number;name:string}
type Media = {image:{url:string;caption:string}|null;can_edit:boolean;revision?:string}
type Template = Named & {revision:string;image:Media['image']}

async function start(page:Page, identity:Identity) {
  expect(fixturePrefix, 'mutations require the disposable CUADERNO-E2E seed').toBe('CUADERNO-E2E')
  await enterApp(page)
  const edition=await api<{edition:string;operational_role:{code:string}}>(page,'/api/cuaderno/edition/')
  expect(edition.status).toBe(200);expect(edition.body.edition).toBe(identity.edition)
  expect(edition.body.operational_role.code).toBe({consulta:'guest',cocina:'user',responsable:'admin'}[identity.role])
}
const marker=(info:TestInfo)=>`${fixturePrefix} media ${info.project.name} ${randomUUID().slice(0,8)}`
async function ownerPage(browser:Browser, page:Page, identity:Identity) {
  if(identity.role !== 'consulta') return {page,close:async()=>{}}
  const context=await browser.newContext({baseURL:process.env.BASE_URL || 'http://127.0.0.1:18081',storageState:authFile(identity.edition,'responsable'),ignoreHTTPSErrors:process.env.CUADERNO_E2E_SELF_SIGNED==='1',locale:'es-ES',timezoneId:'Europe/Madrid',viewport:page.viewportSize()!})
  const owner=await context.newPage(), assertClean=collectBrowserFailures(owner)
  await enterApp(owner)
  return {page:owner,close:async()=>{try {await assertClean()} finally {await context.close()}}}
}
async function observe<T>(page:Page,path:string,method:string,action:()=>Promise<unknown>,status=200):Promise<T> {
  const pending=page.waitForResponse(response=>new URL(response.url()).pathname===appPath(path) && response.request().method()===method)
  void pending.catch(()=>{})
  await action();const response=await pending;expect(response.status(),`${method} ${path}`).toBe(status);expect(await response.finished()).toBeNull();return await response.json() as T
}
async function select(page:Page,control:Locator,option:string) {
  await expect(control).toBeEnabled();await control.focus();await control.press('Enter');await expect(control).toHaveAttribute('aria-expanded','true');await page.getByRole('option',{name:option,exact:true}).click()
}
async function foodPanel(page:Page,id:number) {
  await withAuthenticatedReadBarrier(page,async()=>{
    await page.goto(appPath(`/edit/Food/${id}`))
    await expect(page.getByRole('heading',{name:'Foto del ingrediente',exact:true})).toBeVisible()
    await expect(page.locator('.entity-image-panel .v-progress-linear')).toHaveCount(0)
  },[`/api/food/${id}/`,`/api/cuaderno/foods/${id}/image/`])
  return page.locator('.entity-image-panel')
}
async function visibleImage(panel:Locator,caption:string) {
  const figure=panel.locator('figure').filter({hasText:caption})
  await expect(figure.locator('figcaption')).toHaveText(caption)
  await figure.scrollIntoViewIfNeeded();const img=figure.locator('img')
  await expect(img).toBeVisible();await expect(img).toHaveAttribute('alt',caption)
  await expect.poll(()=>img.evaluate(element=>element instanceof HTMLImageElement && element.complete && element.naturalWidth>0)).toBe(true)
}
async function responsive(page:Page,focus:Locator,info:TestInfo,label:string) {
  for(const viewport of viewports) {
    await page.setViewportSize(viewport);await focus.scrollIntoViewIfNeeded();await expect(focus).toBeVisible();await assertNoHorizontalOverflow(page,info)
    await info.attach(`${label}-${viewport.width}`,{body:await page.screenshot(),contentType:'image/png'})
  }
}

test('media: foto Food real persiste, Consulta solo lee y eliminación conserva ingrediente en las tres ediciones',async({cleanPage:page,identity,browser},info)=>{
  test.setTimeout(90_000)
  await start(page,identity);const owner=await ownerPage(browser,page,identity),name=marker(info)
  let food:Named|undefined
  try {
    const created=await api<Named>(owner.page,'/api/food/',{method:'POST',body:{name}});expect(created.status).toBe(201);food=created.body
    let panel=await foodPanel(owner.page,food.id)
    // Unsupported input must fail locally, retaining the selected filename.
    await panel.locator('input[type=file]').setInputFiles({name:'invalid.svg',mimeType:'image/svg+xml',buffer:Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"/>')})
    let uploads=0;const listen=(request:import('@playwright/test').Request)=>{if(new URL(request.url()).pathname===appPath(`/api/cuaderno/foods/${food!.id}/image/`) && request.method()==='PUT')uploads++}
    owner.page.on('request',listen)
    try {await panel.getByRole('button',{name:'Guardar imagen',exact:true}).click();await expect(panel.getByRole('alert')).toContainText('JPG, PNG, WebP o GIF');expect(uploads).toBe(0);await expect(panel).toContainText('invalid.svg')} finally {owner.page.off('request',listen)}
    await panel.locator('input[type=file]').setInputFiles(tomatoes);await panel.getByLabel('Descripción de la imagen',{exact:true}).fill(name)
    const saved=await observe<Media>(owner.page,`/api/cuaderno/foods/${food.id}/image/`,'PUT',()=>panel.getByRole('button',{name:'Guardar imagen',exact:true}).click())
    expect(saved.image?.caption).toBe(name);await visibleImage(panel,name)
    panel=await foodPanel(owner.page,food.id);await visibleImage(panel,name)
    if(identity.role==='consulta') {
      const readonly=await foodPanel(page,food.id);await visibleImage(readonly,name)
      await expect(readonly.locator('input[type=file]')).toHaveCount(0);await expect(readonly.getByRole('button',{name:'Eliminar imagen',exact:true})).toHaveCount(0)
      expect((await api<Media>(page,`/api/cuaderno/foods/${food.id}/image/`)).body.can_edit).toBe(false)
      expect((await api(page,`/api/cuaderno/foods/${food.id}/image/`,{method:'DELETE'})).status).toBe(403)
      await responsive(page,readonly,info,'food-consulta')
    } else await responsive(page,panel,info,'food-operador')
    await panel.getByRole('button',{name:'Eliminar imagen',exact:true}).click()
    await expect(owner.page.getByRole('dialog')).toContainText('Se conservarán los demás datos')
    await observe(owner.page,`/api/cuaderno/foods/${food.id}/image/`,'DELETE',()=>owner.page.getByRole('dialog').getByRole('button',{name:'Confirmar eliminación',exact:true}).click())
    panel=await foodPanel(owner.page,food.id);await expect(panel).toContainText('Todavía no hay imagen.')
    const retained=await api<Named>(owner.page,`/api/food/${food.id}/`);expect(retained.status).toBe(200);expect(retained.body.name).toBe(name)
  } finally {try {if(food) {const row=await api<Named>(owner.page,`/api/food/${food.id}/`);expect(row.body.name).toBe(name);expect((await api(owner.page,`/api/food/${food.id}/`,{method:'DELETE'})).status).toBe(204)}} finally {await owner.close()}}
})

async function planningPage(page:Page,period?:string) {
  await withAuthenticatedReadBarrier(page,async()=>{await page.goto(appPath('/cuaderno/planificacion'));await expect(page.getByRole('heading',{name:'Organización de menús'})).toBeVisible();await expect(page.getByText(/^(Periodo cargado:|La organización profesional de menús está disponible)/)).toBeVisible();await expect(page.locator('.menu-planning .v-progress-linear')).toHaveCount(0)})
  if(period) {await page.getByLabel('Primer día',{exact:true}).fill(period);await observe(page,'/api/cuaderno/planning/','GET',()=>page.getByRole('button',{name:'Actualizar periodo',exact:true}).click());await expect(page.getByText(/^Periodo cargado:/)).toContainText(period)}
}
async function downloadBytes(page:Page,format:'PNG'|'PDF',info:TestInfo,orientation:string) {
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:`Descargar ${format}`,exact:true}).click();const download:Download=await pending
  expect(await download.failure()).toBeNull();expect(download.suggestedFilename()).toMatch(format==='PNG'?/^menus-pagina-1\.png$/:/^menus\.pdf$/)
  const file=info.outputPath(`${orientation}-${format.toLowerCase()}`);await download.saveAs(file);const bytes=await readFile(file);expect(bytes.length).toBeGreaterThan(10000);await info.attach(`${orientation}-${format}`,{path:file,contentType:format==='PNG'?'image/png':'application/pdf'});return bytes
}
async function prepareDocument(page:Page,name:string,recipeName:string,templateName:string,orientation:'portrait'|'landscape') {
  await page.getByRole('tab',{name:'Impresión',exact:true}).click()
  const groups=page.getByRole('button',{name:/^Quitar menú /});while(await groups.count()) await groups.first().click()
  await page.getByLabel('Nombre del menú',{exact:true}).fill(name)
  await select(page,page.getByRole('combobox',{name:'Portada de una plantilla (opcional)',exact:true}),templateName)
  const selection=page.getByRole('combobox',{name:'Platos del periodo',exact:true});await selection.focus();await selection.press('Enter');await page.getByRole('option').filter({hasText:recipeName}).click();await selection.press('Escape')
  await page.getByRole('button',{name:'Añadir menú a la impresión',exact:true}).click()
  await select(page,page.getByRole('combobox',{name:'Orientación',exact:true}),orientation==='portrait'?'Vertical':'Horizontal')
  await select(page,page.getByRole('combobox',{name:'Declaración dietética en el documento (opcional)',exact:true}),'Celíacos')
  await observe(page,'/api/cuaderno/planning/print/','POST',()=>page.getByRole('button',{name:'Preparar documento',exact:true}).click())
  return page.getByRole('region',{name:'Documento de menús'})
}

test('media: portada de menú aparece al crear, persiste y descarga PNG/PDF A4 con permisos y cuatro tamaños',async({cleanPage:page,identity,browser},info)=>{
  test.setTimeout(120_000)
  await start(page,identity)
  if(identity.edition==='esencial') {await planningPage(page);await expect(page.getByText(/organización profesional de menús está disponible/)).toBeVisible();await expect(page.getByRole('button',{name:'Descargar PNG',exact:true})).toHaveCount(0);return}
  const owner=await ownerPage(browser,page,identity),name=marker(info),recipeName=name+' sopa gástrica',courseName=name+' Primero'
  let recipe:Named|undefined,mealId:number|undefined,template:Template|undefined,course:Named&{revision:string}|undefined
  try {
    const created=await api<Named>(owner.page,'/api/recipe/',{method:'POST',body:{name:recipeName,private:false,servings:25,steps:[]}});expect(created.status).toBe(201);recipe=created.body
    const extras=await api<{revision:string}>(owner.page,`/api/cuaderno/recipes/${recipe.id}/extras/`);expect(extras.status).toBe(200)
    expect((await api(owner.page,`/api/cuaderno/recipes/${recipe.id}/extras/`,{method:'PUT',body:{revision:extras.body.revision,diets:[{slug:'celiacos',status:'unsuitable',note:'Declaración sintética CI'}]}})).status).toBe(200)
    const mealTypes=await api(owner.page,`/api/meal-type/?query=${encodeURIComponent(fixturePrefix+' servicio')}&page_size=100`);expect(mealTypes.status).toBe(200);const types=rows(mealTypes.body).filter(row=>row.name===fixturePrefix+' servicio');expect(types).toHaveLength(1);const mealType=types[0] as Named
    const plan=await api<{id:number}>(owner.page,'/api/meal-plan/',{method:'POST',body:{title:recipeName.slice(0,64),recipe:{id:recipe.id,name:recipeName},servings:25,from_date:`${date}T12:00:00+02:00`,to_date:`${date}T12:00:00+02:00`,meal_type:mealType}});expect(plan.status).toBe(201);mealId=plan.body.id
    const addedCourse=await api<Named&{revision:string}>(owner.page,'/api/cuaderno/planning/courses/',{method:'POST',body:{name:courseName,meal_type:mealType.id,position:0}});expect(addedCourse.status).toBe(201);course=addedCourse.body
    expect((await api(owner.page,`/api/cuaderno/planning/meal-plans/${mealId}/`,{method:'PUT',body:{course:course.id}})).status).toBe(200)
    await planningPage(owner.page,date);await owner.page.getByLabel('Nombre de la plantilla',{exact:true}).fill(name)
    await owner.page.getByLabel('Portada opcional de la nueva plantilla (hasta 5 MiB)',{exact:true}).setInputFiles(coverFile)
    await owner.page.getByLabel('Descripción de la portada',{exact:true}).fill(name+' portada')
    template=await observe<Template>(owner.page,'/api/cuaderno/planning/templates/','POST',()=>owner.page.getByRole('button',{name:'Guardar nueva plantilla',exact:true}).click(),201)
    const card=owner.page.locator('.v-card').filter({has:owner.page.getByRole('button',{name:'Aplicar al calendario',exact:true})}).filter({hasText:name})
    await visibleImage(card.locator('.entity-image-panel'),name+' portada') // before any navigation/reload
    await expect(owner.page.getByRole('status').filter({hasText:'Plantilla guardada.'})).toBeVisible()
    const saved=await api<Template>(owner.page,`/api/cuaderno/planning/templates/${template.id}/`);expect(saved.status).toBe(200);expect(saved.body.image?.caption).toBe(name+' portada');expect(saved.body.image?.url).toMatch(/\?v=[a-f0-9]{16}$/)
    await planningPage(page,date)
    const shown=page.locator('.v-card').filter({has:page.getByRole('button',{name:'Aplicar al calendario',exact:true})}).filter({hasText:name}),panel=shown.locator('.entity-image-panel')
    await visibleImage(panel,name+' portada')
    if(identity.role==='consulta') {await expect(panel.locator('input[type=file]')).toHaveCount(0);await expect(panel.getByRole('button',{name:'Eliminar imagen',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Guardar nueva plantilla',exact:true})).toBeDisabled();expect((await api(page,`/api/cuaderno/planning/templates/${template.id}/image/`,{method:'DELETE'})).status).toBe(403)}
    for(const orientation of ['portrait','landscape'] as const) {
      const preview=await prepareDocument(page,name,recipeName,name,orientation)
      await expect(preview.getByRole('heading',{name,exact:true})).toBeVisible();await expect(preview.locator('table')).toContainText(recipeName);await expect(preview.locator('table')).toContainText(date);await expect(preview.locator('table')).toContainText(mealType.name);await expect(preview.locator('table')).toContainText(courseName);await expect(preview.locator('table')).toContainText('25');await expect(preview.locator('table')).toContainText('No apto');await expect(preview).toContainText('Declaración consultada: Celíacos');await visibleImage(preview,name+' portada')
      const png=await downloadBytes(page,'PNG',info,orientation);expect(png.subarray(0,8)).toEqual(Buffer.from([137,80,78,71,13,10,26,10]));expect([png.readUInt32BE(16),png.readUInt32BE(20)]).toEqual(orientation==='portrait'?[1588,2246]:[2246,1588])
      const pdf=await downloadBytes(page,'PDF',info,orientation),text=pdf.toString('latin1');expect(text.startsWith('%PDF-1.4')).toBe(true);expect(text.trimEnd().endsWith('%%EOF')).toBe(true);expect(text).toContain('/Filter /DCTDecode');expect(text).toContain('/Count 1');expect(text).toContain(orientation==='portrait'?'/Width 1588 /Height 2246':'/Width 2246 /Height 1588');expect(text).toContain(orientation==='portrait'?'/MediaBox [0 0 595.28 841.89]':'/MediaBox [0 0 841.89 595.28]');const offset=Number(text.match(/startxref\n(\d+)/)?.[1]);expect(text.slice(offset,offset+4)).toBe('xref')
      if(orientation==='portrait') await responsive(page,preview,info,'menu-preview')
    }
  } finally {
    try {
      if(template) {const current=await api<Template>(owner.page,`/api/cuaderno/planning/templates/${template.id}/`);expect(current.body.name).toBe(name);expect((await api(owner.page,`/api/cuaderno/planning/templates/${template.id}/?revision=${current.body.revision}`,{method:'DELETE'})).status).toBe(204)}
      if(mealId) {const path=`/api/meal-plan/${mealId}/?from_date=2000-01-01&to_date=2050-01-01`;const current=await api<{recipe:{id:number}}>(owner.page,path);expect(current.body.recipe.id).toBe(recipe!.id);expect((await api(owner.page,path,{method:'DELETE'})).status).toBe(204)}
      if(course) {const current=await api<{courses:(Named&{revision:string})[]}>(owner.page,`/api/cuaderno/planning/?from_date=${date}&to_date=${date}`);const own=current.body.courses.find(row=>row.id===course!.id);expect(own?.name).toBe(courseName);expect((await api(owner.page,`/api/cuaderno/planning/courses/${course.id}/?revision=${own!.revision}`,{method:'DELETE'})).status).toBe(204)}
      if(recipe) {const current=await api<Named>(owner.page,`/api/recipe/${recipe.id}/`);expect(current.body.name).toBe(recipeName);expect((await api(owner.page,`/api/recipe/${recipe.id}/`,{method:'DELETE'})).status).toBe(204)}
    } finally {await owner.close()}
  }
})
