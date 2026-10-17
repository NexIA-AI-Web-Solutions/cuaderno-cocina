<template>
    <v-container class="worker-workspace">
        <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-4">
            <div><h1 class="text-h5">Trabajadores digitales</h1><p class="text-body-2 text-medium-emphasis mt-1">Revisiones con reglas y cálculos de tu cuaderno. Sin servicios externos.</p></div>
            <v-btn variant="outlined" min-height="44" :loading="loading" :disabled="busy" @click="loadWorkspace">Actualizar</v-btn>
        </div>
        <v-alert type="info" variant="tonal" class="mb-4">Generar un informe no cambia precios, pedidos ni existencias. Las propuestas quedan pendientes hasta su aprobación por Responsable.</v-alert>
        <operational-role-notice :role="operationalRole" />
        <v-alert v-if="loadError" type="error" variant="tonal" class="mb-4" role="alert">{{ loadError }}</v-alert>
        <v-progress-linear v-if="loading && !metadata" indeterminate aria-label="Cargando trabajadores" class="mb-4" />
        <v-row v-if="metadata">
            <v-col cols="12" lg="4">
                <v-card variant="outlined" class="mb-4">
                    <v-card-title class="text-wrap">¿Qué necesitas revisar?</v-card-title>
                    <v-card-text>
                        <v-select v-model="kind" :items="availableKinds" item-title="title" item-value="id" label="Trabajador" :disabled="busy" hide-details class="mb-3" />
                        <p class="mb-4">{{ selectedKind?.description }}</p>
                        <form @submit.prevent="generateReport">
                            <v-model-select v-if="['recipe','menu','price','requirements'].includes(context)" v-model="recipe" model="Recipe" label="Receta (opcional)" search-on-load clearable :disabled="busy" hint="Vacío: revisa las recetas accesibles." />
                            <v-text-field v-if="['date','purchase','receipt','menu','requirements'].includes(context)" v-model="date" type="date" label="Día del servicio" :disabled="busy" />
                            <v-row v-if="kind === 'service_learning'">
                                <v-col cols="12" sm="6"><v-text-field v-model="start" type="date" label="Desde (opcional)" :disabled="busy" /></v-col>
                                <v-col cols="12" sm="6"><v-text-field v-model="end" type="date" label="Hasta (opcional)" :disabled="busy" /></v-col>
                            </v-row>
                            <v-model-select v-if="['purchase','receipt'].includes(context)" v-model="supplier" model="Supermarket" label="Proveedor (opcional)" search-on-load clearable :disabled="busy" />
                            <v-select v-if="['purchase','receipt'].includes(context)" v-model="orderId" :items="orders" item-title="title" item-value="id" label="Pedido (opcional)" clearable :disabled="busy" />
                            <v-select v-if="context === 'price'" v-model="filterPackageId" :items="packages" item-title="title" item-value="id" label="Formato para el informe (opcional)" clearable :disabled="busy" />
                            <v-text-field v-if="['recipe','menu'].includes(context)" v-model="servings" label="Raciones (opcional)" inputmode="decimal" :disabled="busy" hint="Solo afecta al cálculo del informe." persistent-hint />
                            <v-text-field v-if="context === 'menu'" v-model="budget" :label="currency ? `Presupuesto por persona (${currency})` : 'Presupuesto por persona'" inputmode="decimal" :disabled="busy" hint="Vacío: compara todos los costes conocidos." persistent-hint />
                            <v-alert v-if="catalogError && ['price','purchase','receipt'].includes(context)" type="warning" variant="tonal" class="my-3">{{ catalogError }}</v-alert>
                            <v-btn v-if="canOperate && ['price','purchase'].includes(context)" variant="text" min-height="44" block class="mt-3" :aria-expanded="prepareChange" :disabled="busy" @click="prepareChange = !prepareChange">{{ prepareChange ? 'Cerrar propuesta' : context === 'price' ? 'Preparar cambio de precio' : 'Preparar borrador de compra' }}</v-btn>
                            <div v-if="prepareChange && canOperate" class="proposal-form mt-3">
                                <h2 class="text-subtitle-1 mb-2">{{ context === 'price' ? 'Propuesta de precios' : 'Borrador de compra' }}</h2>
                                <p class="text-body-2 mb-3">Se guarda para revisión. Todavía no se aplicará ningún cambio.</p>
                                <v-select v-model="proposalPackageId" :items="packages" item-title="title" item-value="id" label="Formato" :disabled="busy" />
                                <template v-if="context === 'price'">
                                    <v-text-field v-model="amount" :label="currency ? `Nuevo precio del envase (${currency})` : 'Nuevo precio del envase'" inputmode="decimal" :disabled="busy || explicitFree" />
                                    <v-checkbox v-model="explicitFree" label="Gratis explícitamente" hide-details :disabled="busy" />
                                    <v-text-field v-model="priceNote" label="Nota del cambio" :disabled="busy" />
                                    <v-textarea v-model="csv" label="Varios precios en CSV (opcional)" rows="3" :disabled="busy" hint="Cabecera: package_id,amount,explicit_free,note. Usa punto decimal. Sustituye al formato individual." persistent-hint />
                                </template>
                                <template v-else>
                                    <v-text-field v-model="packageCount" label="Número de envases completos" inputmode="numeric" :disabled="busy" />
                                    <v-select v-model="offerId" :items="matchingOffers" item-title="title" item-value="id" label="Oferta guardada" clearable :disabled="busy" hint="Selecciona una oferta para conservar su precio en el pedido." persistent-hint />
                                    <p class="text-body-2 mb-3">El servidor calcula la cantidad. Aprobar crea un pedido en borrador; la recepción se confirma en Compras.</p>
                                </template>
                                <v-textarea v-model="proposalEvidence" label="Fuente o motivo del cambio" rows="2" :disabled="busy" hint="Por ejemplo, referencia de la tarifa o revisión del pedido. Obligatorio." persistent-hint />
                            </div>
                            <v-alert v-if="formError" type="error" variant="tonal" class="my-3" role="alert">{{ formError }}</v-alert>
                            <v-btn type="submit" color="primary" min-height="44" block class="mt-4" :loading="generating" :disabled="busy || !canGenerate">{{ prepareChange ? 'Generar informe y propuesta' : 'Generar informe' }}</v-btn>
                            <p v-if="!canGenerate" class="text-body-2 mt-2">Puedes consultar los informes guardados. Cocina o Responsable puede generar uno nuevo.</p>
                        </form>
                    </v-card-text>
                </v-card>
                <worker-schedule-panel :kind="kind" :params="scheduleContext.params" :validation-error="scheduleContext.error" :can-operate="canOperate" />
                <v-card variant="outlined">
                    <details :open="lgAndUp" class="worker-history-disclosure"><summary class="text-h6">Informes recientes</summary>
                    <v-card-text>
                        <v-select v-model="historyFilter" :items="historyFilters" item-title="title" item-value="id" label="Mostrar" hide-details class="mb-3" />
                        <p v-if="metadata.history_scope === 'authorized'" class="text-body-2 mb-3">Puedes revisar propuestas de Cocina que estén dentro de tus permisos.</p>
                        <p v-if="!filteredRuns.length" class="text-body-2">{{ historyFilter === 'pending' ? 'No hay propuestas pendientes.' : 'Todavía no hay informes. Selecciona un trabajador para empezar.' }}</p>
                        <ul v-else class="worker-history">
                            <li v-for="run in filteredRuns" :key="run.id"><button type="button" class="worker-history-button" :class="{'worker-history-selected': selectedRun?.id === run.id}" :disabled="busy" @click="selectRun(run)"><span class="font-weight-medium">{{ run.title }}</span><span class="text-caption">{{ workerStatusLabel(run.status) }} · {{ dateLabel(run.created_at) }}</span></button></li>
                        </ul>
                    </v-card-text>
                    </details>
                </v-card>
            </v-col>
            <v-col cols="12" lg="8">
                <v-card v-if="selectedRun" variant="outlined" aria-labelledby="worker-report-title">
                    <v-card-title id="worker-report-title" class="text-wrap">{{ selectedRun.title }}</v-card-title>
                    <v-card-text>
                        <div class="d-flex flex-wrap align-center ga-2 mb-3"><v-chip :color="statusColor(selectedRun.status)">{{ workerStatusLabel(selectedRun.status) }}</v-chip><span class="text-caption">{{ dateLabel(selectedRun.created_at) }}</span></div>
                        <p class="text-body-1 mb-4">{{ selectedRun.summary }}</p>
                        <v-alert v-if="selectedRun.status === 'read_only'" type="info" variant="tonal" class="mb-4">Informe de solo lectura. No ha cambiado datos operativos.</v-alert>
                        <v-alert v-if="selectedRun.status === 'stale'" type="warning" variant="tonal" class="mb-4" role="alert">Los datos han cambiado desde la revisión. Genera una nueva versión y vuelve a revisar sus efectos antes de aprobar.</v-alert>
                        <v-alert v-if="actionMessage" :type="actionSuccess ? 'success' : 'error'" variant="tonal" class="mb-4" role="status">{{ actionMessage }}</v-alert>
                        <v-alert v-for="(warning, index) in selectedRun.report.warnings" :key="`warning-${index}`" type="warning" variant="tonal" class="mb-3">{{ workerValue(warning) }}</v-alert>
                        <details v-if="Object.keys(reportContext).length" class="worker-evidence mb-4">
                            <summary>Contexto y datos del informe</summary>
                            <dl class="worker-values mt-3"><div v-for="(value, key) in reportContext" :key="key"><dt>{{ workerFieldLabel(String(key)) }}</dt><dd><worker-value :value="value" /></dd></div></dl>
                        </details>
                        <p v-if="!selectedRun.report.items.length && !Object.keys(reportContext).length" class="my-4">No se encontraron resultados para este contexto. Puedes cambiar los filtros y generar otro informe.</p>
                        <v-card v-for="(item, index) in selectedRun.report.items" :key="`${item.id ?? index}`" variant="tonal" class="mb-3">
                            <v-card-title class="text-subtitle-1 text-wrap">{{ item.title }}</v-card-title>
                            <v-card-text>
                                <p v-if="item.detail" class="mb-3">{{ item.detail }}</p>
                                <v-chip v-if="item.severity === 'warning' || item.severity === 'error'" size="small" color="warning" class="mb-3">Requiere revisión</v-chip>
                                <dl v-if="Object.keys(itemValues(item)).length" class="worker-values"><div v-for="(value, key) in itemValues(item)" :key="key"><dt>{{ workerFieldLabel(String(key)) }}</dt><dd><worker-value :value="value" /></dd></div></dl>
                                <details v-if="item.evidence?.length" class="worker-evidence mt-3"><summary>Evidencia de este resultado</summary><ul><li v-for="(evidence, evidenceIndex) in item.evidence" :key="evidenceIndex"><worker-value :value="evidence" /></li></ul></details>
                                <v-btn v-if="item.action_url" :to="item.action_url" variant="outlined" min-height="44" class="mt-3">Abrir para revisar</v-btn>
                            </v-card-text>
                        </v-card>
                        <div v-if="selectedRun.proposal" class="worker-proposal my-5">
                            <h2 class="text-h6 mb-2">{{ selectedRun.proposal.label }}</h2>
                            <p class="mb-2">Efectos previstos:</p><ul class="mb-3"><li v-for="(effect, index) in selectedRun.proposal.effects" :key="index">{{ effect }}</li></ul>
                            <details class="worker-evidence mb-3"><summary>Datos de la propuesta</summary><dl class="worker-values mt-2"><div v-for="(value, key) in selectedRun.proposal.payload" :key="key"><dt>{{ workerFieldLabel(String(key)) }}</dt><dd><worker-value :value="value" /></dd></div></dl></details>
                            <template v-if="selectedRun.status === 'pending'">
                                <v-checkbox v-if="canApprove" v-model="approved" label="He revisado la evidencia y los efectos de esta propuesta" :disabled="busy" hide-details />
                                <p v-else class="text-body-2 my-3">Solo Responsable puede aplicar esta propuesta.</p>
                                <div class="d-flex flex-wrap ga-2 mt-3"><v-btn v-if="canApprove" color="primary" min-height="44" :disabled="!approved || busy" :loading="applying" @click="applyProposal">Aprobar y aplicar</v-btn><v-btn v-if="canOperate" variant="outlined" min-height="44" :disabled="busy" @click="dismissProposal">Descartar propuesta</v-btn></div>
                            </template>
                        </div>
                        <div class="d-flex flex-wrap ga-2 my-4">
                            <v-btn v-if="canGenerate" variant="outlined" min-height="44" :disabled="busy" @click="rebuildReport">{{ selectedRun.status === 'stale' ? 'Generar nueva versión' : 'Volver a calcular' }}</v-btn>
                            <v-btn variant="text" min-height="44" :disabled="busy" @click="copyReport">Copiar informe</v-btn>
                            <v-btn variant="text" min-height="44" :disabled="busy" @click="downloadReport('text')">Descargar texto</v-btn>
                            <v-btn variant="text" min-height="44" :disabled="busy" @click="downloadReport('json')">Descargar JSON</v-btn>
                        </div>
                        <p v-if="exportMessage" class="text-body-2 mb-3" role="status">{{ exportMessage }}</p>
                        <details class="worker-evidence"><summary>Fuentes y versión de los datos</summary><p class="text-caption mt-2">Reglas: {{ reportPolicyVersion }} · Versión de los datos: <span class="worker-digest">{{ selectedRun.input_digest }}</span></p><ul v-if="selectedRun.report.evidence.length"><li v-for="(evidence, index) in selectedRun.report.evidence" :key="index"><worker-value :value="evidence" /></li></ul><p v-else class="mt-2">Este informe no incluye fuentes adicionales.</p></details>
                        <details v-if="Array.isArray(selectedRun.events) && selectedRun.events.length" class="worker-evidence mt-2"><summary>Registro de actividad</summary><worker-value :value="selectedRun.events" /></details>
                    </v-card-text>
                </v-card>
                <v-card v-else variant="outlined" class="worker-empty"><v-card-text><v-icon icon="fa-solid fa-list-check" size="40" class="mb-4" /><h2 class="text-h6 mb-2">Tu revisión, paso a paso</h2><p>Elige un trabajador y su contexto. Aquí verás los resultados, los datos que faltan y los enlaces para revisarlos.</p><p class="mt-3">Cada propuesta muestra sus efectos antes de pedir aprobación.</p></v-card-text></v-card>
            </v-col>
        </v-row>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref, watch} from 'vue'
import {useRoute} from 'vue-router'
import {useDisplay} from 'vuetify'
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import OperationalRoleNotice from '@/cuaderno/components/OperationalRoleNotice.vue'
import WorkerValue from '@/cuaderno/components/WorkerValue.vue'
import WorkerSchedulePanel from '@/cuaderno/components/WorkerSchedulePanel.vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {editionOperationalRole, type OperationalRole} from '@/cuaderno/operationalRoleUi'
import {editionCurrency, priceVersionBody} from '@/cuaderno/priceHistoryUi'
import {WORKER_KINDS, workerContextQuery, workerParams, workerDecimal, workerRun, workerMetadata, workerApprovalBody, workerStatusLabel, workerFieldLabel, workerValue, workerReportText, workerReportExport, workerPolicyVersion, type WorkerKind, type WorkerStatus, type WorkerRun, type WorkerMetadata, type WorkerItem} from '@/cuaderno/workerUi'

type Choice = {id?: number; name?: string | null}
type CatalogChoice = {id: number; title: string; package_id?: number; supplier_id?: number}
const route = useRoute()
const {lgAndUp} = useDisplay()
const preset = workerContextQuery(route.query)
const metadata = ref<WorkerMetadata | null>(null)
const operationalRole = ref<OperationalRole | null>(null)
const currency = ref<string | null>(null)
const kind = ref<WorkerKind>(preset.kind ?? 'cost_completion')
const recipe = ref<Choice | number | null>(preset.recipe_id ? (preset.recipe_name ? {id: preset.recipe_id, name: preset.recipe_name} : preset.recipe_id) : null), supplier = ref<Choice | null>(null)
const date = ref(preset.date ?? localDate()), start = ref(''), end = ref(''), servings = ref(''), budget = ref('')
const orderId = ref<number | null>(preset.order_id ?? null), filterPackageId = ref<number | null>(preset.package_id ?? null)
const packages = ref<CatalogChoice[]>([]), orders = ref<CatalogChoice[]>([]), offers = ref<CatalogChoice[]>([])
const prepareChange = ref(false), proposalPackageId = ref<number | null>(null), offerId = ref<number | null>(null)
const amount = ref(''), explicitFree = ref(false), priceNote = ref(''), csv = ref(''), packageCount = ref(''), proposalEvidence = ref('')
const selectedRun = ref<WorkerRun | null>(null), approved = ref(false), historyFilter = ref('all')
const loading = ref(false), generating = ref(false), applying = ref(false)
const loadError = ref(''), catalogError = ref(''), formError = ref(''), actionMessage = ref(''), exportMessage = ref(''), actionSuccess = ref(false)
let disposed = false
const busy = computed(() => loading.value || generating.value || applying.value)
const canOperate = computed(() => operationalRole.value?.can_operate_cuaderno === true)
const canApprove = computed(() => operationalRole.value?.code === 'admin' && metadata.value?.can_approve === true)
const canGenerate = computed(() => canOperate.value)
const availableKinds = computed(() => metadata.value?.kinds ?? [])
const selectedKind = computed(() => availableKinds.value.find(item => item.id === kind.value))
const context = computed(() => WORKER_KINDS.find(item => item.id === kind.value)?.context ?? 'recipe')
const matchingOffers = computed(() => offers.value.filter(offer => offer.package_id === proposalPackageId.value && (!supplier.value?.id || offer.supplier_id === supplier.value.id)))
const historyFilters = [{id: 'all', title: 'Todos los informes'}, {id: 'pending', title: 'Pendientes de aprobación'}, {id: 'read_only', title: 'Solo lectura'}, {id: 'applied', title: 'Aplicados'}]
const filteredRuns = computed(() => (metadata.value?.runs ?? []).filter(run => historyFilter.value === 'all' || run.status === historyFilter.value))
const scheduleContext = computed(currentParams)
const reportPolicyVersion = computed(() => workerPolicyVersion(selectedRun.value, metadata.value?.policy.version ?? ''))
const reportContext = computed(() => Object.fromEntries(Object.entries(selectedRun.value?.report ?? {}).filter(([key]) => !['kind','title','summary','items','evidence','warnings','generated_at','as_of','analysis_mode','read_only'].includes(key))))
watch(kind, () => {prepareChange.value = false; formError.value = ''})
watch(proposalPackageId, () => {offerId.value = null})
onBeforeUnmount(() => {disposed = true})
onMounted(loadWorkspace)
function localDate() {const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`}
function dateLabel(value: string) {const parsed = new Date(value); return Number.isFinite(parsed.getTime()) ? parsed.toLocaleString('es-ES') : value}
function statusColor(status: WorkerStatus) {return {read_only: 'info', pending: 'warning', applied: 'success', dismissed: undefined, stale: 'error'}[status]}
function itemValues(item: WorkerItem) {return Object.fromEntries(Object.entries(item.values ?? {}).filter(([key]) => key !== 'action_url' || !item.action_url))}
function selectRun(run: WorkerRun) {selectedRun.value = run; approved.value = false; actionMessage.value = ''; exportMessage.value = ''}
function rememberRun(run: WorkerRun) {if (!metadata.value) return; metadata.value.runs = [run, ...metadata.value.runs.filter(previous => previous.id !== run.id)].slice(0, 50); selectRun(run)}
async function loadWorkspace() {
    if (busy.value) return
    loading.value = true; loadError.value = ''
    try {
        const results = await Promise.allSettled(['/api/cuaderno/workers/', '/api/cuaderno/edition/'].map(async url => readJson(await cuadernoFetch(url))))
        if (disposed) return
        const workerResult = results[0], editionResult = results[1]
        if (workerResult?.status === 'fulfilled') {
            if (!workerResult.value.ok) loadError.value = apiError(workerResult.value.status, workerResult.value.data)
            else {
                const parsed = workerMetadata(workerResult.value.data)
                if (!parsed) loadError.value = 'El servidor devolvió un informe incompleto. Conservamos la revisión anterior.'
                else {
                    metadata.value = parsed
                    if (!parsed.kinds.some(item => item.id === kind.value) && parsed.kinds[0]) kind.value = parsed.kinds[0].id
                    const updated = parsed.runs.find(run => run.id === selectedRun.value?.id)
                    if (updated) selectRun(updated)
                    else if (!selectedRun.value && parsed.runs[0]) selectRun(parsed.runs[0])
                }
            }
        } else loadError.value = 'No se ha podido cargar el espacio de trabajadores. Reintenta.'
        if (editionResult?.status === 'fulfilled' && editionResult.value.ok) {
            operationalRole.value = editionOperationalRole(editionResult.value.data)
            currency.value = editionCurrency(editionResult.value.data)
        } else {operationalRole.value = null; loadError.value ||= 'No se han podido confirmar tus permisos. Actualiza para reintentar.'}
        await loadCatalogs()
    } finally {if (!disposed) loading.value = false}
}
async function loadCatalogs() {
    catalogError.value = ''
    const responses = await Promise.allSettled(['/api/cuaderno/packages/', '/api/cuaderno/purchase-orders/', '/api/cuaderno/purchase-offers/'].map(async url => readJson(await cuadernoFetch(url))))
    if (disposed) return
    const lists: CatalogChoice[][] = []
    for (const result of responses) {
        if (result.status !== 'fulfilled' || !result.value.ok) {lists.push([]); continue}
        const data = result.value.data
        const rows = Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : []
        lists.push(rows.filter((row: Record<string, unknown>) => row && Number.isSafeInteger(row.id) && Number(row.id) > 0).map((row: Record<string, unknown>) => ({id: Number(row.id), package_id: typeof row.package === 'number' ? row.package : undefined, supplier_id: typeof row.supplier === 'number' ? row.supplier : undefined, title: row.label ? `${row.food_name ?? 'Ingrediente'} — ${row.label}` : row.state ? `Pedido ${row.id} · ${row.supplier_name ?? 'Sin proveedor'} · ${row.state}` : `Oferta ${row.id} · ${row.amount ?? 'Precio desconocido'} ${row.currency ?? ''}`})))
    }
    packages.value = lists[0] ?? []; orders.value = lists[1] ?? []; offers.value = lists[2] ?? []
    if (responses.some(result => result.status !== 'fulfilled' || (!result.value.ok && result.value.status !== 403))) catalogError.value = 'No se pudieron cargar algunos formatos, pedidos u ofertas. Actualiza para reintentar.'
}
function currentParams() {
    return workerParams(kind.value, {date: ['date','purchase','receipt','menu','requirements'].includes(context.value) ? date.value : '', start: kind.value === 'service_learning' ? start.value : '', end: kind.value === 'service_learning' ? end.value : '',
        recipe_id: ['recipe','menu','price','requirements'].includes(context.value) ? typeof recipe.value === 'number' ? recipe.value : recipe.value?.id : undefined,
        package_id: context.value === 'price' ? filterPackageId.value ?? undefined : undefined,
        supplier_id: ['purchase','receipt'].includes(context.value) ? supplier.value?.id : undefined,
        order_id: ['purchase','receipt'].includes(context.value) ? orderId.value ?? undefined : undefined,
        servings: ['recipe','menu'].includes(context.value) ? servings.value : '', budget: context.value === 'menu' ? budget.value : ''})
}
function currentProposal(): Record<string, unknown> | null {
    if (!prepareChange.value || !canOperate.value) return null
    if (!proposalEvidence.value.trim()) {formError.value = 'Indica la fuente o el motivo de la propuesta.'; return null}
    if (context.value === 'price' && csv.value.trim()) return {action: 'reference_prices', payload: {csv: csv.value, evidence: proposalEvidence.value.trim()}}
    if (!proposalPackageId.value) {formError.value = 'Selecciona un formato para la propuesta.'; return null}
    if (context.value === 'price') {
        const parsed = priceVersionBody(explicitFree.value ? '0' : amount.value, explicitFree.value)
        if (!parsed.body) {formError.value = parsed.error; return null}
        return {action: 'reference_prices', payload: {rows: [{package_id: proposalPackageId.value, ...parsed.body, note: priceNote.value.trim()}], evidence: proposalEvidence.value.trim()}}
    }
    const count = workerDecimal(packageCount.value)
    if (!count || !/^\d+(?:\.0+)?$/.test(count)) {formError.value = 'Indica un número entero de envases mayor que cero.'; return null}
    if (offerId.value && !matchingOffers.value.some(offer => offer.id === offerId.value)) {formError.value = 'La oferta no corresponde al formato y proveedor seleccionados.'; return null}
    return {action: 'purchase_draft', payload: {package_id: proposalPackageId.value, package_count: count, ...(offerId.value ? {offer_id: offerId.value} : {}), evidence: proposalEvidence.value.trim()}}
}
async function generateReport() {
    if (busy.value || !canGenerate.value) return
    formError.value = ''
    const parsed = currentParams()
    if (!parsed.params) {formError.value = parsed.error; return}
    const proposal = currentProposal()
    if (prepareChange.value && !proposal) return
    await preview({kind: kind.value, params: parsed.params, ...(proposal ? {proposal} : {})})
}
async function preview(body: Record<string, unknown>) {
    generating.value = true; formError.value = ''; actionMessage.value = ''
    try {
        const response = await readJson(await cuadernoFetch('/api/cuaderno/workers/preview/', {method: 'POST', body: JSON.stringify(body)}))
        if (disposed) return
        if (!response.ok) {formError.value = apiError(response.status, response.data); return}
        const parsed = workerRun(response.data)
        if (!parsed) {formError.value = 'El servidor no confirmó un informe válido. No se ha aplicado ningún cambio.'; return}
        rememberRun(parsed)
    } finally {if (!disposed) generating.value = false}
}
async function rebuildReport() {
    if (busy.value || !canGenerate.value || !selectedRun.value) return
    const run = selectedRun.value
    await preview({kind: run.kind, params: run.params, ...(run.proposal ? {proposal: {action: run.proposal.action, payload: run.proposal.payload}} : {})})
}
async function applyProposal() {
    if (busy.value || !selectedRun.value) return
    const run = selectedRun.value
    const body = workerApprovalBody(run, approved.value, canApprove.value)
    if (!body) return
    applying.value = true; actionMessage.value = ''; actionSuccess.value = false
    try {
        const response = await readJson(await cuadernoFetch(`/api/cuaderno/workers/${run.id}/apply/`, {method: 'POST', body: JSON.stringify(body)}))
        if (disposed) return
        approved.value = false
        if (response.status === 409) {run.status = 'stale'; actionMessage.value = 'Los datos cambiaron. La propuesta no se ha aplicado. Genera una nueva versión.'; return}
        if (!response.ok) {actionMessage.value = apiError(response.status, response.data); return}
        const parsed = workerRun(response.data)
        if (!parsed || parsed.id !== run.id || parsed.status !== 'applied') {actionMessage.value = 'No se pudo confirmar el resultado. Actualiza el informe antes de volver a actuar.'; return}
        rememberRun(parsed); actionSuccess.value = true; actionMessage.value = 'Propuesta aplicada. La operación quedó registrada.'
    } finally {if (!disposed) applying.value = false}
}
async function dismissProposal() {
    if (busy.value || !canOperate.value || selectedRun.value?.status !== 'pending') return
    const run = selectedRun.value
    applying.value = true; actionMessage.value = ''; actionSuccess.value = false
    try {
        const response = await readJson(await cuadernoFetch(`/api/cuaderno/workers/${run.id}/dismiss/`, {method: 'POST', body: '{}'}))
        if (disposed) return
        if (!response.ok) {actionMessage.value = apiError(response.status, response.data); return}
        const parsed = workerRun(response.data)
        if (!parsed || parsed.id !== run.id || parsed.status !== 'dismissed') {actionMessage.value = 'No se pudo confirmar el descarte. Actualiza el informe.'; return}
        rememberRun(parsed); actionSuccess.value = true; actionMessage.value = 'Propuesta descartada. No se aplicaron sus cambios.'
    } finally {if (!disposed) applying.value = false}
}
async function copyReport() {
    if (!selectedRun.value || !metadata.value) return
    try {await navigator.clipboard.writeText(workerReportText(selectedRun.value, reportPolicyVersion.value)); exportMessage.value = 'Informe copiado con evidencia y versión de los datos.'}
    catch {exportMessage.value = 'No se pudo copiar. Puedes descargar el informe en texto.'}
}
function downloadReport(format: 'text' | 'json') {
    if (!selectedRun.value || !metadata.value) return
    const run = selectedRun.value
    const content = format === 'json' ? workerReportExport(run, reportPolicyVersion.value) : workerReportText(run, reportPolicyVersion.value)
    const url = URL.createObjectURL(new Blob([content], {type: format === 'json' ? 'application/json;charset=utf-8' : 'text/plain;charset=utf-8'}))
    const link = document.createElement('a'); link.href = url; link.download = `cuaderno-informe-${run.kind}-${run.id}.${format === 'json' ? 'json' : 'txt'}`
    document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
    exportMessage.value = 'Descarga preparada con evidencia y versión de los datos.'
}
</script>

<style scoped>
.worker-workspace {max-width: 1440px;}
.worker-values {margin: 0;}
.worker-values > div {display: grid; grid-template-columns: minmax(110px, 1fr) minmax(0, 2fr); gap: 12px; padding: 8px 0; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .12);}
.worker-values dt {font-weight: 600;}
.worker-values dd {margin: 0; overflow-wrap: anywhere;}
.worker-evidence summary {cursor: pointer; min-height: 44px; display: flex; align-items: center; text-decoration: underline;}
.worker-evidence summary::before {content: '▸'; margin-right: 8px;}
.worker-evidence[open] summary::before {content: '▾';}
.worker-evidence ul, .worker-proposal ul {padding-left: 24px;}
.worker-evidence li, .worker-proposal li {margin: 6px 0; overflow-wrap: anywhere;}
.worker-digest {overflow-wrap: anywhere;}
.worker-history {list-style: none; padding: 0; max-height: 420px; overflow-y: auto;}
.worker-history-disclosure > summary {cursor: pointer; min-height: 44px; padding: 16px;}
.worker-history-disclosure > summary:focus-visible {outline: 3px solid rgb(var(--v-theme-primary)); outline-offset: -3px;}
.worker-history-button {width: 100%; text-align: left; display: flex; flex-direction: column; gap: 4px; border: 1px solid rgba(var(--v-theme-on-surface), .16); border-radius: 6px; padding: 12px; min-height: 60px; margin-bottom: 8px;}
.worker-history-selected {background: rgba(var(--v-theme-primary), .08); border-color: rgb(var(--v-theme-primary));}
.worker-history-button:focus-visible, .worker-evidence summary:focus-visible {outline: 3px solid rgb(var(--v-theme-primary)); outline-offset: 3px;}
.worker-empty {text-align: center; padding: 40px 16px;}
.proposal-form, .worker-proposal {border: 1px solid rgba(var(--v-theme-primary), .35); border-radius: 8px; padding: 16px;}
@media (max-width: 599px) {.worker-values > div {grid-template-columns: 1fr; gap: 3px;} .worker-empty {padding: 24px 8px;}}
</style>
