import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
import {createRequire} from 'node:module'
import {pathToFileURL} from 'node:url'
import {parse, compileScript} from '@vue/compiler-sfc'
import {createSSRApp} from 'vue'
import {renderToString} from '@vue/server-renderer'
const source = readFileSync(new URL('./workerUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const ui = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)
const run = () => ({id: 7, kind: 'price_watch', title: 'Precios del día', status: 'read_only', created_at: '2026-10-11T12:00:00Z', summary: 'Revisa el formato', input_digest: 'version-a', report: {items: [{title: 'Aceite', values: {amount: null}, action_url: '/cuaderno/precios'}], evidence: [{source: 'Catálogo', version: 'price-42'}], warnings: []}})
const pending = () => ({...run(), status: 'pending', proposal: {action: 'reference_prices', label: 'Actualizar precio', payload: {rows: []}, effects: ['Añadir una versión de precio al formato 3.']}})

test('rendered cost result shows a concise total and retains exact calculation details and raw exports', async () => {
    const vueSource = readFileSync(new URL('./components/WorkerValue.vue', import.meta.url), 'utf8')
    const {descriptor} = parse(vueSource)
    const compiled = compileScript(descriptor, {id: 'worker-value-test', inlineTemplate: true})
    const module = ts.transpileModule(compiled.content, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
        .replace(/from ["']vue["']/g, `from '${pathToFileURL(createRequire(import.meta.url).resolve('vue').replace(/index\.js$/, 'index.mjs')).href}'`)
        .replace(/from ["']@\/cuaderno\/workerUi["']/g, `from 'data:text/javascript;base64,${Buffer.from(js).toString('base64')}'`)
    const {default: WorkerValue} = await import(`data:text/javascript;base64,${Buffer.from(module).toString('base64')}`)
    const cost = {status: 'complete', display: '6.40', per_serving: '1.6000000000000000', total: '6.4000000000000000', unrounded: '6.4000000000000000', known_subtotal: '6.4000000000000000', base_servings: '4', lines: [{display: '6.40', quantity: '0.1000000000000001'}]}
    const app = createSSRApp(WorkerValue, {value: cost})
    app.component('v-btn', {template: '<button><slot /></button>'})
    const html = await renderToString(app)
    const summary = html.split('<details')[0]
    assert.match(summary, /Completo/); assert.match(summary, /Total/); assert.match(summary, /6\.40/)
    assert.match(summary, /Coste por ración/); assert.match(summary, /1\.6/)
    assert.doesNotMatch(summary, /Subtotal conocido|Raciones originales|Líneas de coste|Importe sin redondear/)
    assert.match(html, /<details[^>]*><summary>Detalle del cálculo<\/summary>/)
    assert.match(html, /0\.1000000000000001/); assert.doesNotMatch(html, /6\.4000000000000000|1\.6000000000000000/)
    const incompleteApp = createSSRApp(WorkerValue, {value: {...cost, status: 'incomplete', display: null}})
    incompleteApp.component('v-btn', {template: '<button><slot /></button>'})
    const incomplete = await renderToString(incompleteApp)
    assert.match(incomplete.split('<details')[0], /Incompleto[\s\S]*Desconocido[\s\S]*Subtotal conocido/)
    const raw = ui.workerReportExport({...run(), report: {...run().report, items: [{title: 'Receta', values: {cost}}]}}, 'v1')
    assert.equal(JSON.parse(raw).run.report.items[0].values.cost.unrounded, '6.4000000000000000')
})

test('worker parameters preserve exact decimal input and reject missing/invalid numbers', () => {
    const form = {date: '2026-10-11', recipe_id: 12, servings: '0,1000000000000001', budget: '32,50'}
    assert.deepEqual(ui.workerParams('menu_candidates', form).params, {date: '2026-10-11', recipe_id: 12, servings: '0.1000000000000001', budget: '32.50'})
    for (const value of ['-1', '+1', '1e3', 'NaN', '1,2.3', '١', '1'.repeat(17)]) assert.equal(ui.workerParams('menu_candidates', {...form, budget: value}).params, null, value)
    assert.equal(ui.workerParams('menu_candidates', {...form, servings: '0'}).params, null)
    assert.equal(ui.workerParams('service_briefing', {...form, date: '2026-02-30'}).params, null)
    assert.equal(ui.workerParams('receipt_review', {...form, order_id: 0}).params, null)
    assert.equal(ui.workerParams('purchase_review', {...form, supplier_id: true}).params, null)
})
test('reports show unknown prices and accept label items without granting unsafe links', () => {
    assert.equal(ui.workerValue(null), 'Desconocido')
    assert.equal(ui.workerValue('0.00'), '0.00')
    assert.equal(ui.workerRun(run()).report.items[0].values.amount, null)
    const parsed = ui.workerRun({...run(), report: {items: [{label: 'Unidad incompleta', action_url: 'javascript:alert(1)'}]}})
    assert.equal(parsed.report.items[0].title, 'Unidad incompleta')
    assert.equal(parsed.report.items[0].action_url, undefined)
})
test('only approved pending proposals carry the exact reviewed input digest', () => {
    const p = ui.workerRun(pending())
    assert.deepEqual(ui.workerApprovalBody(p, true, true), {expected_digest: 'version-a', approval: true})
    for (const status of ['read_only', 'applied', 'dismissed', 'stale']) assert.equal(ui.workerApprovalBody({...p, status}, true, true), null)
    assert.equal(ui.workerApprovalBody(p, false, true), null)
    assert.equal(ui.workerApprovalBody(p, true, false), null)
    assert.equal(ui.workerRun({...pending(), proposal: {action: 'confirm_receipt', label: 'Receive', payload: {}, effects: ['Stock']}}), null)
    assert.equal(ui.workerRun({...pending(), proposal: {...pending().proposal, effects: []}}), null)
    assert.equal(ui.workerRun({...pending(), proposal: null}), null)
})
test('metadata fails closed on unsupported policy, report shape or identities', () => {
    const metadata = {kinds: [{id: 'price_watch', title: 'Precios', description: 'Revisión'}], policy: {version: '1', require_approval: true, external_services: false}, runs: [run()]}
    assert.equal(ui.workerMetadata(metadata).runs.length, 1)
    for (const changes of [{external_services: true}, {require_approval: false}, {version: ''}]) assert.equal(ui.workerMetadata({...metadata, policy: {...metadata.policy, ...changes}}), null)
    for (const changes of [{id: -1}, {status: 'running'}, {input_digest: ''}, {created_at: 'yesterday'}, {report: {items: [{}]}}]) assert.equal(ui.workerRun({...run(), ...changes}), null)
})
test('links remain app-relative and resist encoded or executable navigation', () => {
    for (const path of ['/recipe/3', '/cuaderno/almacen', '/mealplan?date=2026-10-11']) assert.equal(ui.workerActionUrl(path), path)
    for (const path of ['//example.org', 'https://example.org', '/\\example.org', 'javascript:alert(1)', '/cuaderno/precios%0a', '/recipe/0', '/recipe/3\n', '/settings/api']) assert.equal(ui.workerActionUrl(path), null, path)
})
test('text and JSON exports preserve evidence, unknowns, proposal effects and source version', () => {
    const p = ui.workerRun(pending())
    const text = ui.workerReportText(p, 'rules-2')
    for (const expected of ['Desconocido', 'Catálogo', 'price-42', 'version-a', 'rules-2', 'Añadir una versión']) assert.ok(text.includes(expected), expected)
    const exported = JSON.parse(ui.workerReportExport(p, 'rules-2'))
    assert.equal(exported.source_version, 'version-a')
    assert.equal(exported.policy_version, 'rules-2')
    assert.equal(exported.run.report.items[0].values.amount, null)
})
test('native report items remain readable without an explicit values wrapper', () => {
    const parsed = ui.workerRun({...run(), report: {items: [{name: 'Sopa', recipe_id: 12, cost: null, blockers: ['precio desconocido']}]}})
    assert.equal(parsed.report.items[0].title, 'Sopa')
    assert.equal(parsed.report.items[0].values.cost, null)
    assert.equal(parsed.report.items[0].values.recipe_id, 12)
})
test('zero budget is an explicit budget and package/date range context stays validated', () => {
    const form = {date: '', start: '2026-10-01', end: '2026-10-11', package_id: 4, servings: '', budget: '0'}
    assert.deepEqual(ui.workerParams('service_learning', form).params, {start: '2026-10-01', end: '2026-10-11', package_id: 4, budget: '0'})
    assert.equal(ui.workerParams('service_learning', {...form, end: '2026-09-30'}).params, null)
})

// Execute the shipped Vue script with its actual presentation helpers and a
// controlled HTTP boundary. Browser rendering is checked separately.
const {default: vm} = await import('node:vm')
const deferred = () => {let resolve; const promise = new Promise(yes => {resolve = yes}); return {promise, resolve}}
const priceSource = readFileSync(new URL('./priceHistoryUi.ts', import.meta.url), 'utf8')
const priceJs = ts.transpileModule(priceSource, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const prices = await import(`data:text/javascript;base64,${Buffer.from(priceJs).toString('base64')}`)
function component(path, names, {globals}) {
    const source = readFileSync(new URL('../' + path, import.meta.url), 'utf8').match(/<script[^>]*>([\s\S]*?)<\/script>/)[1]
    const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText.replace(/^import[\s\S]*?\sfrom\s+['"][^'"]+['"];?\s*$/gm, '').replace(/^export \{\};?$/gm, '')
    const context = vm.createContext({useRoute: () => ({query: {}}), useDisplay: () => ({lgAndUp: {value: true}}), ref: value => ({value}), computed: fn => ({get value() {return fn()}}), watch() {}, onMounted() {}, onBeforeUnmount() {}, ...globals})
    new vm.Script(js + '\n;globalThis.exposed = {' + names.join(',') + '};').runInContext(context)
    return {exposed: context.exposed}
}
function workspace(fetcher) {
    const h = component('cuaderno/components/TrabajadoresPage.vue', [
        'metadata','operationalRole','selectedRun','approved','kind','recipe','supplier','date','servings','budget','prepareChange','proposalPackageId','amount','explicitFree','proposalEvidence','packageCount','offerId','matchingOffers',
        'generateReport','applyProposal','dismissProposal','rebuildReport','selectRun','formError','actionMessage','generating',
    ], {globals: {...ui, cuadernoFetch: fetcher, readJson: async value => value,
        apiError: (_status, data) => data.detail || 'Error del servidor',
        priceVersionBody: prices.priceVersionBody,
    }})
    const x = h.exposed
    x.metadata.value = {kinds: [], policy: {version: 'v1'}, runs: [], can_approve: true}
    x.operationalRole.value = {code: 'admin', can_operate_cuaderno: true}
    return x
}
const response = data => ({ok: true, status: 200, data})

test('actual workspace generates reports using context and keeps form on HTTP errors', async () => {
    const calls = []
    const x = workspace(async (url, options) => {calls.push({url, body: JSON.parse(options.body)}); return {ok: false, status: 503, data: {detail: 'Sin conexión'}}})
    x.kind.value = 'menu_candidates'; x.recipe.value = {id: 12}; x.servings.value = '4,5'; x.budget.value = '8,30'
    await x.generateReport()
    assert.equal(calls[0].url, '/api/cuaderno/workers/preview/')
    assert.equal(calls[0].body.params.servings, '4.5')
    assert.equal(calls[0].body.params.budget, '8.30')
    assert.equal(calls[0].body.proposal, undefined)
    assert.equal(x.formError.value, 'Sin conexión')
    assert.equal(x.budget.value, '8,30')
    assert.equal(x.generating.value, false)
})
test('actual workspace stores proposals without any apply request and requires evidence', async () => {
    const calls = []
    const x = workspace(async (url, options) => {calls.push({url, body: JSON.parse(options.body)}); return response(pending())})
    x.kind.value = 'price_watch'; x.prepareChange.value = true; x.proposalPackageId.value = 4; x.amount.value = '12,50'
    await x.generateReport()
    assert.equal(calls.length, 0)
    assert.match(x.formError.value, /fuente/)
    x.proposalEvidence.value = 'Tarifa octubre'; await x.generateReport()
    assert.equal(calls.length, 1)
    assert.deepEqual(calls[0].body.proposal.payload.rows, [{package_id: 4, amount: '12.50', explicit_free: false, note: ''}])
    assert.equal(x.selectedRun.value.status, 'pending')
    assert.equal(x.approved.value, false)
})
test('actual workspace prevents duplicate previews while a request is in flight', async () => {
    const wait = deferred(); let count = 0
    const x = workspace(async () => {count++; return wait.promise})
    const first = x.generateReport(); await x.generateReport()
    assert.equal(count, 1)
    wait.resolve(response(run())); await first
    assert.equal(x.generating.value, false)
})
test('actual approval requires review and marks stale on 409, rebuild keeps reviewed inputs', async () => {
    const calls = []
    const x = workspace(async (url, options) => {calls.push({url, body: JSON.parse(options.body)}); return url.endsWith('/apply/') ? {ok: false, status: 409, data: {}} : response({...pending(), id: 8})})
    const p = ui.workerRun({...pending(), params: {recipe_id: 12, date: '2026-10-11'}})
    x.selectRun(p); await x.applyProposal(); assert.equal(calls.length, 0)
    x.approved.value = true; await x.applyProposal()
    assert.deepEqual(calls[0].body, {expected_digest: 'version-a', approval: true})
    assert.equal(x.selectedRun.value.status, 'stale')
    assert.equal(x.approved.value, false)
    await x.applyProposal(); assert.equal(calls.length, 1)
    await x.rebuildReport()
    assert.deepEqual(calls[1].body.params, {recipe_id: 12, date: '2026-10-11'})
    assert.equal(calls[1].body.proposal.action, 'reference_prices')
    assert.equal(x.selectedRun.value.id, 8)
})
test('actual workspace does not announce apply/dismiss success for another run', async () => {
    const x = workspace(async () => response({...pending(), id: 99, status: 'applied'}))
    x.selectRun(ui.workerRun(pending())); x.approved.value = true
    await x.applyProposal()
    assert.equal(x.selectedRun.value.status, 'pending')
    assert.match(x.actionMessage.value, /confirmar/)
    await x.dismissProposal()
    assert.equal(x.selectedRun.value.status, 'pending')
    assert.match(x.actionMessage.value, /confirmar/)
})
test('actual workspace blocks guest writes and permits Cocina proposals but requires Responsable apply', async () => {
    let count = 0
    const x = workspace(async () => {count++; return response(pending())})
    x.operationalRole.value = {code: 'guest', can_operate_cuaderno: false}
    await x.generateReport(); assert.equal(count, 0)
    x.selectRun(ui.workerRun(pending())); x.approved.value = true
    x.operationalRole.value = {code: 'user', can_operate_cuaderno: true}
    await x.applyProposal(); assert.equal(count, 0)
})
test('Responsable can review an authorized Cocina proposal while metadata can revoke approval', async () => {
    let count = 0
    const x = workspace(async () => {count++; return response({...pending(), status: 'applied'})})
    x.metadata.value.history_scope = 'authorized'
    x.selectRun(ui.workerRun({...pending(), events: [{event: 'preview', actor: 19}]})); x.approved.value = true
    x.metadata.value.can_approve = false
    await x.applyProposal(); assert.equal(count, 0)
    x.metadata.value.can_approve = true
    await x.applyProposal(); assert.equal(count, 1)
    assert.equal(x.selectedRun.value.status, 'applied')
})
test('exports can preserve the reviewed policy version after rules change', () => {
    const reviewed = ui.workerRun({...run(), policy: {version: 'reviewed-v1'}})
    assert.equal(ui.workerPolicyVersion(reviewed, 'current-v2'), 'reviewed-v1')
    assert.equal(ui.workerPolicyVersion(ui.workerRun(run()), 'current-v2'), 'current-v2')
})

test('route context accepts native IDs/date/kind and ignores malformed query values', () => {
    assert.deepEqual(ui.workerContextQuery({kind: 'receipt_review', order_id: '9', recipe_id: '12', recipe_name: ' Sopa ', date: '2026-10-11'}), {kind: 'receipt_review', order_id: 9, recipe_id: 12, recipe_name: 'Sopa', date: '2026-10-11'})
    assert.deepEqual(ui.workerContextQuery({kind: 'chat', recipe_id: ['12'], order_id: '-3', package_id: '1e3', date: '2026-02-30'}), {})
    assert.deepEqual(ui.workerContextQuery({recipe_id: '2147483648', recipe_name: 'Sin receta'}), {})
})
test('scheduled worker reports cannot contain proposals and validate saved schedules', () => {
    assert.deepEqual(ui.workerScheduleBody('cost_completion', {recipe_id: 12}, 24), {kind: 'cost_completion', params: {recipe_id: 12}, interval_hours: 24})
    assert.equal(ui.workerScheduleBody('cost_completion', {proposal: {}}, 24), null)
    assert.equal(ui.workerScheduleBody('cost_completion', {}, 1), null)
    assert.equal(ui.workerScheduleRows({schedules: [{id: 1, kind: 'cost_completion', params: {}, interval_hours: 24, enabled: true, next_run: '2026-10-12T10:00:00Z', last_run_id: null, last_error: '', created_at: '2026-10-11T10:00:00Z'}]}).length, 1)
    assert.equal(ui.workerScheduleRows({schedules: [{id: 1, kind: 'chat', enabled: true}]}), null)
})
test('rolling schedules omit dates while fixed schedules retain their reviewed context', () => {
    const params = {date: '2026-10-11', start: '2026-10-01', end: '2026-10-10', recipe_id: 12, servings: '2.50'}
    assert.deepEqual(ui.workerScheduleBody('service_learning', params, 24, true), {kind: 'service_learning', params: {recipe_id: 12, servings: '2.50'}, interval_hours: 24})
    assert.deepEqual(ui.workerScheduleBody('service_learning', params, 168, false), {kind: 'service_learning', params, interval_hours: 168})
    assert.equal(params.date, '2026-10-11')
    assert.equal(ui.workerScheduleBody('service_learning', {...params, proposal: {}}, 24, true), null)
})
function schedulePanel(fetcher) {
    const props = {kind: 'price_watch', params: {package_id: 4}, canOperate: true}
    const h = component('cuaderno/components/WorkerSchedulePanel.vue', ['createSchedule','toggleSchedule','loadSchedules','schedules','message','runnerActive','useExecutionDate'], {globals: {...ui, defineProps: () => props, cuadernoFetch: fetcher, readJson: async value => value, apiError: (_status, data) => data.detail}})
    return {...h.exposed, props}
}
const schedule = () => ({id: 3, kind: 'price_watch', params: {package_id: 4}, interval_hours: 24, enabled: true, next_run: '2026-10-12T10:00:00Z', last_run_id: null, last_error: '', created_at: '2026-10-11T10:00:00Z'})
test('actual schedule panel sends only readonly kind/context and preserves the inactive runner notice', async () => {
    const calls = []
    const x = schedulePanel(async (url, options) => {calls.push({url, body: options?.body ? JSON.parse(options.body) : null}); return response(options ? schedule() : {schedules: [], runner_active: false})})
    await x.loadSchedules(); assert.equal(x.runnerActive.value, false)
    await x.createSchedule()
    assert.deepEqual(calls[1].body, {kind: 'price_watch', params: {package_id: 4}, interval_hours: 24})
    assert.equal(calls[1].body.proposal, undefined)
    assert.equal(x.schedules.value.length, 1)
    x.props.canOperate = false; await x.createSchedule(); assert.equal(calls.length, 2)
})
test('actual schedule panel confirms pause identity and leaves prior schedule on HTTP failure', async () => {
    const x = schedulePanel(async () => ({ok: false, status: 503, data: {detail: 'Sin conexión'}}))
    x.schedules.value = [schedule()]
    await x.toggleSchedule(x.schedules.value[0])
    assert.equal(x.schedules.value[0].enabled, true)
    assert.equal(x.message.value, 'Sin conexión')
})
test('actual schedule panel defaults to rolling dates and allows a fixed period explicitly', async () => {
    const bodies = []
    const x = schedulePanel(async (_url, options) => {bodies.push(JSON.parse(options.body)); return response(schedule())})
    x.props.params = {package_id: 4, date: '2026-10-11', start: '2026-10-01', end: '2026-10-10'}
    assert.equal(x.useExecutionDate.value, true)
    await x.createSchedule()
    assert.deepEqual(bodies[0].params, {package_id: 4})
    x.useExecutionDate.value = false
    await x.createSchedule()
    assert.deepEqual(bodies[1].params, x.props.params)
})
