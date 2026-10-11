/** Presentation contract for deterministic, explicitly approved worker reports. */
export const WORKER_KINDS = [
    {id: 'cost_completion', title: 'Completar escandallos', description: 'Localiza precios, unidades y rendimientos que faltan.', icon: 'fa-solid fa-calculator', context: 'recipe'},
    {id: 'price_watch', title: 'Vigilar precios', description: 'Revisa cambios de precio y su efecto en las recetas.', icon: 'fa-solid fa-tags', context: 'price'},
    {id: 'service_briefing', title: 'Preparar el servicio', description: 'Reúne el menú, los comensales y los avisos del día.', icon: 'fa-solid fa-utensils', context: 'date'},
    {id: 'requirements_review', title: 'Revisar requisitos', description: 'Revisa declaraciones y requisitos que necesitan confirmación.', icon: 'fa-solid fa-list-check', context: 'requirements'},
    {id: 'purchase_review', title: 'Revisar compras', description: 'Revisa pedidos y prepara un borrador con una oferta conocida.', icon: 'fa-solid fa-cart-shopping', context: 'purchase'},
    {id: 'receipt_review', title: 'Revisar recepciones', description: 'Contrasta pedidos y recepciones sin confirmar mercancía.', icon: 'fa-solid fa-box', context: 'receipt'},
    {id: 'menu_candidates', title: 'Comparar platos', description: 'Encuentra recetas con coste conocido para un presupuesto.', icon: 'fa-solid fa-book-open', context: 'menu'},
    {id: 'service_learning', title: 'Aprender del servicio', description: 'Revisa servicios, producción y cancelaciones registrados.', icon: 'fa-solid fa-chart-line', context: 'date'},
] as const
export type WorkerKind = typeof WORKER_KINDS[number]['id']
export type WorkerStatus = 'read_only' | 'pending' | 'applied' | 'dismissed' | 'stale'
export type WorkerItem = {id?: string | number; title: string; detail?: string; severity?: string; action_url?: string; evidence?: unknown[]; values?: Record<string, unknown>}
export type WorkerProposal = {action: 'reference_prices' | 'purchase_draft'; label: string; payload: Record<string, unknown>; effects: string[]}
export type WorkerRun = {id: number; kind: WorkerKind; title: string; status: WorkerStatus; created_at: string; summary: string; input_digest: string; params: Record<string, unknown>; report: {items: WorkerItem[]; evidence: unknown[]; warnings: unknown[]; [key: string]: unknown}; proposal: WorkerProposal | null; [key: string]: unknown}
export type WorkerMetadata = {kinds: {id: WorkerKind; title: string; description: string; min_edition?: string}[]; policy: {version: string; require_approval: true; external_services: false; [key: string]: unknown}; runs: WorkerRun[]; can_approve?: boolean; history_scope?: 'own' | 'authorized'}
export type WorkerForm = {date: string; start?: string; end?: string; recipe_id?: number; package_id?: number; supplier_id?: number; order_id?: number; servings: string; budget: string}
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const id = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0
export const isWorkerKind = (value: unknown): value is WorkerKind => WORKER_KINDS.some(kind => kind.id === value)
export function workerContextQuery(query: unknown): {kind?: WorkerKind; recipe_id?: number; recipe_name?: string; order_id?: number; package_id?: number; date?: string} {
    if (!record(query)) return {}
    const result: {kind?: WorkerKind; recipe_id?: number; recipe_name?: string; order_id?: number; package_id?: number; date?: string} = {}
    if (isWorkerKind(query.kind)) result.kind = query.kind
    for (const key of ['recipe_id', 'order_id', 'package_id'] as const) {
        const value = query[key]
        if (typeof value === 'string' && /^[1-9]\d*$/.test(value) && Number(value) <= 2147483647) result[key] = Number(value)
    }
    if (typeof query.date === 'string' && validDate(query.date)) result.date = query.date
    if (result.recipe_id && typeof query.recipe_name === 'string' && query.recipe_name.trim()) result.recipe_name = query.recipe_name.trim().slice(0, 200)
    return result
}
export function workerDecimal(value: string, allowZero = false): string | null {
    if (typeof value !== 'string') return null
    const normalized = value.trim().replace(',', '.')
    return /^\d{1,16}(?:\.\d{1,16})?$/.test(normalized) && (allowZero || /[1-9]/.test(normalized)) ? normalized : null
}
function validDate(value: string) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
    const date = new Date(`${value}T12:00:00Z`)
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
}
export function workerParams(kind: WorkerKind, form: WorkerForm): {params: Record<string, unknown> | null; error: string} {
    const params: Record<string, unknown> = {}
    if (!isWorkerKind(kind)) return {params: null, error: 'Selecciona un trabajador disponible.'}
    if (form.date) {
        if (!validDate(form.date)) return {params: null, error: 'Indica una fecha válida.'}
        params.date = form.date
    }
    for (const key of ['start', 'end'] as const) {
        if (form[key]) {
            if (!validDate(form[key]!)) return {params: null, error: 'Indica un intervalo de fechas válido.'}
            params[key] = form[key]
        }
    }
    if (form.start && form.end && (form.end < form.start || Date.parse(form.end) - Date.parse(form.start) > 366 * 86400000)) return {params: null, error: 'El intervalo debe estar ordenado y abarcar como máximo 366 días.'}
    for (const key of ['recipe_id', 'package_id', 'supplier_id', 'order_id'] as const) {
        const value = form[key]
        if (value !== undefined) {
            if (!id(value)) return {params: null, error: 'Selecciona un registro válido.'}
            params[key] = value
        }
    }
    if (form.servings.trim()) {
        const servings = workerDecimal(form.servings)
        if (servings === null) return {params: null, error: 'Las raciones deben ser un decimal mayor que cero.'}
        params.servings = servings
    }
    if (form.budget.trim()) {
        const budget = workerDecimal(form.budget, true)
        if (budget === null) return {params: null, error: 'El presupuesto por persona debe ser un decimal igual o mayor que cero.'}
        params.budget = budget
    }
    return {params, error: ''}
}
/** Route destinations are app-relative, never executable or external. */
export function workerActionUrl(value: unknown): string | null {
    if (typeof value !== 'string' || /[\\\s\u0000-\u001f]/.test(value) || value.includes('%')) return null
    if (/^\/recipe\/[1-9]\d*(?:\?[^#]*)?$/.test(value)) return value
    if (/^\/(?:cuaderno\/(?:precios|lista|planificacion|produccion|almacen|reservas)|mealplan|shopping|pantry)(?:\?[^#]*)?$/.test(value)) return value
    return null
}
export function workerRun(value: unknown): WorkerRun | null {
    if (!record(value) || !id(value.id) || !isWorkerKind(value.kind) || typeof value.title !== 'string'
        || !['read_only', 'pending', 'applied', 'dismissed', 'stale'].includes(String(value.status))
        || typeof value.created_at !== 'string' || !Number.isFinite(Date.parse(value.created_at))
        || typeof value.summary !== 'string' || typeof value.input_digest !== 'string' || !value.input_digest
        || !record(value.report) || !Array.isArray(value.report.items)) return null
    const items: WorkerItem[] = []
    for (const item of value.report.items) {
        if (!record(item) || typeof (item.title ?? item.label ?? item.name) !== 'string') return null
        const extraValues = Object.fromEntries(Object.entries(item).filter(([key]) => !['id', 'title', 'label', 'name', 'detail', 'severity', 'action_url', 'evidence', 'values'].includes(key)))
        const defaultUrl = id(item.recipe_id) ? `/recipe/${item.recipe_id}` : ({price_watch: '/cuaderno/precios', service_briefing: '/cuaderno/produccion', purchase_review: '/cuaderno/almacen', receipt_review: '/cuaderno/almacen', service_learning: '/cuaderno/produccion'} as Partial<Record<WorkerKind, string>>)[value.kind]
        items.push({...item, title: String(item.title ?? item.label ?? item.name), action_url: item.action_url ? workerActionUrl(item.action_url) ?? undefined : defaultUrl,
            detail: typeof item.detail === 'string' ? item.detail : undefined,
            severity: typeof item.severity === 'string' ? item.severity : undefined,
            values: record(item.values) ? item.values : Object.keys(extraValues).length ? extraValues : undefined, evidence: Array.isArray(item.evidence) ? item.evidence : undefined})
    }
    const proposal = value.proposal
    if (proposal !== undefined && proposal !== null && (!record(proposal)
        || !['reference_prices', 'purchase_draft'].includes(String(proposal.action)) || typeof proposal.label !== 'string'
        || !record(proposal.payload) || !Array.isArray(proposal.effects) || !proposal.effects.length
        || proposal.effects.some(effect => typeof effect !== 'string' || !effect.trim()))) return null
    if (value.status === 'pending' && !proposal) return null
    return {...value, params: record(value.params) ? value.params : {},
        report: {...value.report, items, evidence: Array.isArray(value.report.evidence) ? value.report.evidence : [], warnings: Array.isArray(value.report.warnings) ? value.report.warnings : []},
        proposal: proposal ?? null} as WorkerRun
}
export function workerMetadata(value: unknown): WorkerMetadata | null {
    if (!record(value) || !Array.isArray(value.kinds) || !Array.isArray(value.runs) || !record(value.policy)
        || typeof value.policy.version !== 'string' || !value.policy.version || value.policy.require_approval !== true || value.policy.external_services !== false) return null
    if (value.kinds.some(kind => !record(kind) || !isWorkerKind(kind.id) || typeof kind.title !== 'string' || typeof kind.description !== 'string')
        || (value.can_approve !== undefined && typeof value.can_approve !== 'boolean')
        || (value.history_scope !== undefined && !['own', 'authorized'].includes(String(value.history_scope)))) return null
    const runs = value.runs.map(workerRun)
    if (runs.some(run => run === null)) return null
    return {...value, runs} as WorkerMetadata
}
export function workerApprovalBody(run: WorkerRun, approved: boolean, canApprove: boolean) {
    return approved && canApprove && run.status === 'pending' && run.proposal && run.input_digest
        ? {expected_digest: run.input_digest, approval: true} : null
}
export function workerStatusLabel(status: WorkerStatus): string {
    return {read_only: 'Solo lectura', pending: 'Pendiente de aprobación', applied: 'Aplicado', dismissed: 'Descartado', stale: 'Datos modificados'}[status]
}
const labels: Record<string, string> = {
    recipe_id: 'Receta', recipe: 'Receta', package_id: 'Formato', package: 'Formato', food_id: 'Ingrediente', food: 'Ingrediente', supplier_id: 'Proveedor', order_id: 'Pedido',
    status: 'Estado', quantity: 'Cantidad', amount: 'Importe', currency: 'Moneda', cost: 'Coste', per_serving: 'Coste por ración', total: 'Total', servings: 'Raciones', budget: 'Presupuesto por persona',
    date: 'Fecha', service_date: 'Día del servicio', source: 'Fuente', version: 'Versión', source_version: 'Versión de la fuente', title: 'Título', label: 'Concepto', detail: 'Detalle', code: 'Aviso',
    current: 'Actual', previous: 'Anterior', difference: 'Diferencia', name: 'Nombre', state: 'Estado', note: 'Nota', explicit_free: 'Gratis explícitamente',
    available: 'Disponible', required: 'Necesario', shortage: 'Falta', missing: 'Falta', price: 'Precio', unit: 'Unidad', unit_name: 'Unidad', price_policy: 'Política de precios',
    package_count: 'Número de envases', offer_id: 'Oferta', evidence: 'Evidencia', count: 'Cantidad de registros', updated_at: 'Última actualización', recorded_at: 'Registrado',
    type: 'Tipo', id: 'Registro', before: 'Antes', after: 'Después', difference_per_serving: 'Diferencia por ración', unrounded: 'Importe sin redondear',
    allergens: 'Alérgenos declarados', diets: 'Declaraciones dietéticas', requirement_candidates: 'Requisitos a contrastar', dietary_guarantees: 'Aptitud dietética garantizada',
    issues: 'Incidencias', blockers: 'Datos pendientes', needs: 'Necesidades', preparation: 'Preparación', service_id: 'Servicio', receipt_id: 'Recepción',
    reservations: 'Reservas', grouped_questions: 'Preguntas por dato pendiente', buying_needs: 'Necesidades de compra', pending_orders: 'Pedidos pendientes',
    stock_known: 'Existencias verificadas', stock_sufficient: 'Existencias suficientes', within_budget: 'Dentro del presupuesto', pending_quantity: 'Cantidad pendiente',
    produced_count: 'Servicios producidos', produced_covers: 'Comensales producidos', food_name: 'Ingrediente', package_name: 'Formato', supplier_name: 'Proveedor', action: 'Revisión recomendada',
    minimum_stock: 'Existencia mínima', usable_stock: 'Existencia utilizable', packages: 'Envases necesarios', purchase_quantity: 'Cantidad de compra', reference_price: 'Precio de referencia',
    arrival_assumed: 'Llegada asumida', arrival_unknown: 'Fecha de llegada desconocida', recipe_ids: 'Recetas afectadas', ingredient_ids: 'Ingredientes afectados', affected_recipe_count: 'Recetas afectadas', question: 'Dato por completar',
    action_url: 'Acceso a la ficha', service_drift: 'Diferencias con servicios confirmados', events: 'Actividad', event: 'Acción', actor: 'Usuario', data: 'Detalle', created_at: 'Registrado', applied_at: 'Aplicado', approved_by: 'Aprobado por',
    base_servings: 'Raciones originales', display: 'Importe mostrado', known_subtotal: 'Subtotal conocido', lines: 'Líneas de coste', warnings: 'Avisos', unit_id: 'Unidad', ingredient_id: 'Ingrediente de la receta', step_id: 'Paso', codes: 'Datos pendientes',
    frozen_cost: 'Coste confirmado', current_cost: 'Coste actual', comparison: 'Criterio de comparación', frozen: 'Datos confirmados', covers: 'Comensales', keyword: 'Requisito mencionado', matched_text: 'Texto de origen', requires_confirmation: 'Requiere confirmación',
    time: 'Hora', reservation_id: 'Reserva', items: 'Resultados', instruction: 'Instrucción', checked: 'Completado', source_step_id: 'Paso de origen', slug: 'Declaración', source_id: 'Fuente', updated_by: 'Actualizado por',
    received_quantity: 'Cantidad recibida', receipt_quantity: 'Cantidad en recepciones', price_snapshot: 'Precio del pedido', entry_id: 'Existencia', movement_id: 'Movimiento', reversed: 'Revertida', shortfall: 'Falta', unknown_conversion: 'Conversión desconocida',
    inventory_entry_ids: 'Existencias utilizadas', dietary_guarantee: 'Aptitud dietética garantizada', recorded_count: 'Servicios registrados', cancelled_count: 'Servicios cancelados', service_ids: 'Servicios', weekdays: 'Días de la semana',
}
export const workerFieldLabel = (key: string) => labels[key] ?? key.replace(/_/g, ' ')
export function workerValue(value: unknown, depth = 0): string {
    if (value === null || value === undefined) return 'Desconocido'
    if (value === true) return 'Sí'
    if (value === false) return 'No'
    if (typeof value === 'string') return ({complete: 'Completo', incomplete: 'Incompleto', invalid: 'Inválido', unavailable: 'No disponible', unknown: 'Desconocido', declared: 'Declarado', draft: 'Borrador', confirmed: 'Confirmado', produced: 'Producido', cancelled: 'Cancelado', pending: 'Pendiente', net: 'Neto', gross: 'Con impuestos', preview: 'Informe generado', applied: 'Propuesta aplicada', dismissed: 'Propuesta descartada', stale: 'Datos modificados', reference_prices: 'Precios de referencia', purchase_draft: 'Borrador de compra'} as Record<string, string>)[value] ?? value
    if (typeof value === 'number') return String(value)
    if (depth > 4) return 'Consultar el informe descargado'
    if (Array.isArray(value)) return value.map(item => workerValue(item, depth + 1)).join(' · ')
    if (record(value)) return Object.entries(value).map(([key, item]) => `${workerFieldLabel(key)}: ${workerValue(item, depth + 1)}`).join(' · ')
    return 'Desconocido'
}
export function workerReportText(run: WorkerRun, policyVersion: string): string {
    const lines = [run.title, workerStatusLabel(run.status), `Generado: ${run.created_at}`, `Versión de las reglas: ${policyVersion}`, `Versión de los datos: ${run.input_digest}`, '', run.summary]
    for (const item of run.report.items) {
        lines.push('', item.title)
        if (item.detail) lines.push(item.detail)
        if (item.values) lines.push(workerValue(item.values))
        if (item.evidence?.length) lines.push(`Evidencia: ${workerValue(item.evidence)}`)
        if (item.action_url) lines.push(`Abrir: ${item.action_url}`)
    }
    if (run.report.warnings.length) lines.push('', `Avisos: ${workerValue(run.report.warnings)}`)
    if (run.report.evidence.length) lines.push('', `Fuentes: ${workerValue(run.report.evidence)}`)
    for (const [key, value] of Object.entries(run.report)) if (!['kind','title','summary','items','evidence','warnings','generated_at','as_of','analysis_mode','read_only'].includes(key)) lines.push('', `${workerFieldLabel(key)}: ${workerValue(value)}`)
    if (run.proposal) lines.push('', `Propuesta: ${run.proposal.label}`, ...run.proposal.effects)
    return lines.join('\n')
}
export function workerPolicyVersion(run: WorkerRun | null, fallback: string): string {
    return run && record(run.policy) && typeof run.policy.version === 'string' ? run.policy.version : fallback
}
export function workerReportExport(run: WorkerRun, policyVersion: string) {
    return JSON.stringify({format: 'cuaderno-worker-report', version: 1, policy_version: policyVersion, source_version: run.input_digest, run}, null, 2)
}
export type WorkerSchedule = {id: number; kind: WorkerKind; params: Record<string, unknown>; interval_hours: number; enabled: boolean; next_run: string; last_run_id: number | null; last_error: string; created_at: string}
export function workerScheduleBody(kind: WorkerKind, params: Record<string, unknown> | null, interval: number, useExecutionDate = false) {
    const allowed = ['date','start','end','recipe_id','package_id','supplier_id','order_id','servings','budget','limit']
    return isWorkerKind(kind) && record(params) && Object.keys(params).every(key => allowed.includes(key)) && [24, 168].includes(interval)
        ? {kind, params: useExecutionDate ? Object.fromEntries(Object.entries(params).filter(([key]) => !['date', 'start', 'end'].includes(key))) : {...params}, interval_hours: interval} : null
}
export function workerScheduleRows(value: unknown): WorkerSchedule[] | null {
    if (!record(value) || !Array.isArray(value.schedules)) return null
    for (const row of value.schedules) {
        if (!record(row) || !id(row.id) || !isWorkerKind(row.kind) || !record(row.params)
            || ![24,168].includes(Number(row.interval_hours)) || typeof row.interval_hours !== 'number' || typeof row.enabled !== 'boolean'
            || typeof row.next_run !== 'string' || !Number.isFinite(Date.parse(row.next_run))
            || (row.last_run_id !== null && !id(row.last_run_id)) || typeof row.last_error !== 'string'
            || typeof row.created_at !== 'string' || !Number.isFinite(Date.parse(row.created_at))) return null
    }
    return value.schedules as WorkerSchedule[]
}
