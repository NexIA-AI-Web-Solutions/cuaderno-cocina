export type ServicePreparationState = 'draft' | 'confirmed' | 'produced' | 'cancelled'

export type ServicePreparationItem = {
    id: number
    source_step_id: number | null
    position: number
    recipe_id: number
    name: string
    instruction: string
    checked: boolean
    checked_at: string | null
    updated_by: number | null
}

export type ServicePreparationEnvelope = {
    service_id: number
    state: ServicePreparationState
    can_edit: boolean
    revision: string
    items: ServicePreparationItem[]
}

export type ServicePreparationWrite = {item: number; checked: boolean; revision: string}

const ENVELOPE_KEYS = ['can_edit', 'items', 'revision', 'service_id', 'state']
const ITEM_KEYS = [
    'checked', 'checked_at', 'id', 'instruction', 'name', 'position',
    'recipe_id', 'source_step_id', 'updated_by',
]
const STATES = new Set<ServicePreparationState>(['draft', 'confirmed', 'produced', 'cancelled'])
const REVISION = /^[0-9a-f]{64}$/
const AWARE_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/

function record(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
    const keys = Object.keys(value).sort()
    return keys.length === expected.length && keys.every((key, index) => key === expected[index])
}

function positiveId(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function position(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function revision(value: unknown): value is string {
    return typeof value === 'string' && REVISION.test(value)
}

function awareTimestamp(value: unknown): value is string {
    return typeof value === 'string'
        && AWARE_TIMESTAMP.test(value)
        && Number.isFinite(Date.parse(value))
}

export function servicePreparationEnvelope(data: unknown, serviceId?: number): ServicePreparationEnvelope | null {
    if (!record(data) || !exactKeys(data, ENVELOPE_KEYS)) return null
    if (!positiveId(data.service_id) || (serviceId !== undefined && data.service_id !== serviceId)) return null
    if (typeof data.state !== 'string' || !STATES.has(data.state as ServicePreparationState)) return null
    if (typeof data.can_edit !== 'boolean' || (data.state !== 'confirmed' && data.can_edit)) return null
    if (!revision(data.revision) || !Array.isArray(data.items)) return null

    const ids = new Set<number>()
    const items: ServicePreparationItem[] = []
    for (let index = 0; index < data.items.length; index += 1) {
        const raw = data.items[index]
        if (!record(raw) || !exactKeys(raw, ITEM_KEYS)) return null
        if (!positiveId(raw.id) || ids.has(raw.id)
            || (raw.source_step_id !== null && !positiveId(raw.source_step_id))
            || !position(raw.position) || raw.position !== index
            || !positiveId(raw.recipe_id)
            || typeof raw.name !== 'string' || typeof raw.instruction !== 'string'
            || typeof raw.checked !== 'boolean'
            || (raw.updated_by !== null && !positiveId(raw.updated_by))) return null
        if (raw.checked) {
            if (!awareTimestamp(raw.checked_at) || !positiveId(raw.updated_by)) return null
        } else if (raw.checked_at !== null) return null
        ids.add(raw.id)
        items.push({
            id: raw.id,
            source_step_id: raw.source_step_id,
            position: raw.position,
            recipe_id: raw.recipe_id,
            name: raw.name,
            instruction: raw.instruction,
            checked: raw.checked,
            checked_at: raw.checked_at,
            updated_by: raw.updated_by,
        })
    }
    if (items.length === 0 && data.can_edit) return null
    return {
        service_id: data.service_id,
        state: data.state as ServicePreparationState,
        can_edit: data.can_edit,
        revision: data.revision,
        items,
    }
}

export function servicePreparationWrite(
    item: unknown,
    checked: unknown,
    revision: unknown,
): {body: ServicePreparationWrite | null; error: string} {
    if (!positiveId(item)) return {body: null, error: 'Selecciona una tarea de preparación válida.'}
    if (typeof checked !== 'boolean') return {body: null, error: 'El estado de la tarea de preparación no es válido.'}
    if (!revisionValid(revision)) {
        return {body: null, error: 'La versión de la preparación no es válida; recarga los datos.'}
    }
    return {body: {item, checked, revision}, error: ''}
}

function revisionValid(value: unknown): value is string {
    return revision(value)
}

export function servicePreparationSaveEnvelope(
    data: unknown,
    serviceId: number,
    itemId: number,
    checked: boolean,
    before?: unknown,
): ServicePreparationEnvelope | null {
    if (!positiveId(serviceId) || !positiveId(itemId) || typeof checked !== 'boolean') return null
    const parsed = servicePreparationEnvelope(data, serviceId)
    const previous = servicePreparationEnvelope(before, serviceId)
    if (parsed === null || previous === null || parsed.state !== 'confirmed' || !parsed.can_edit) return null
    if (parsed.revision === previous.revision || parsed.items.length !== previous.items.length) return null
    for (let index = 0; index < previous.items.length; index += 1) {
        const oldItem = previous.items[index]
        const newItem = parsed.items[index]
        if (!oldItem || !newItem
            || newItem.id !== oldItem.id
            || newItem.position !== oldItem.position
            || newItem.recipe_id !== oldItem.recipe_id
            || newItem.name !== oldItem.name
            || newItem.instruction !== oldItem.instruction
            || !(newItem.source_step_id === oldItem.source_step_id
                || (oldItem.source_step_id !== null && newItem.source_step_id === null))) return null
        if (oldItem.id !== itemId
            && (newItem.checked !== oldItem.checked
                || newItem.checked_at !== oldItem.checked_at
                || newItem.updated_by !== oldItem.updated_by)) return null
    }
    const saved = parsed.items.filter(item => item.id === itemId)
    return saved.length === 1 && saved[0]?.checked === checked ? parsed : null
}

export function servicePreparationConflictMessage(status: number): string {
    return status === 409
        ? 'Otra persona cambió esta preparación. Conservamos la vista actual; usa Recargar para ver los cambios del servidor.'
        : ''
}
