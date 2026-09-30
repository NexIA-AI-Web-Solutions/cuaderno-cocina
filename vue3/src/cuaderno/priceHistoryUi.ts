export const PRICE_HISTORY_PAGE_SIZE = 20

export type PriceVersionWrite = {amount: string; explicit_free: boolean}
export type OptionalPackagePrice = {value: string | null; explicit_free: boolean; error: string}
export type PriceVersionResult = {body: PriceVersionWrite | null; error: string}
export type PriceWriteResponse = PriceVersionWrite & {id: number; valid_from: string}

export type PriceHistoryItem = {
    id: number
    amount: string
    explicit_free: boolean
    valid_from: string
    created_at: string
    created_by: number
    note: string
    is_current: boolean
}

export type PriceHistoryEnvelope = {
    package: number
    currency: string
    as_of: string
    current_price_id: number | null
    count: number
    next_offset: number | null
    items: PriceHistoryItem[]
}

export type PackageSummary = {
    id: number
    food: number
    food_name: string
    unit: number
    unit_name: string
    label: string
    quantity: string
    is_reference: boolean
    current_price: null | {
        id: number
        amount: string
        explicit_free: boolean
        valid_from: string
    }
}

const DECIMAL_32_16 = /^\d{1,16}(?:\.\d{1,16})?$/

function normalizedDecimal(value: string): string | null {
    const trimmed = value.trim()
    if (!trimmed || (trimmed.includes('.') && trimmed.includes(','))) return null
    const normalized = trimmed.replace(',', '.')
    return DECIMAL_32_16.test(normalized) ? normalized : null
}

function exactZero(value: string): boolean {
    return /^0+(?:\.0+)?$/.test(value)
}

function canonicalDecimal(value: string): string | null {
    const normalized = normalizedDecimal(value)
    if (normalized === null) return null
    const [integer = '', fraction = ''] = normalized.split('.')
    const canonicalInteger = integer.replace(/^0+(?=\d)/, '')
    const canonicalFraction = fraction.replace(/0+$/, '')
    return canonicalFraction ? `${canonicalInteger}.${canonicalFraction}` : canonicalInteger
}

function priceError(value: string, explicitFree: boolean): string {
    if (!value.trim()) return 'Indica un importe; dejarlo vacío significa precio desconocido y no crea historial.'
    const normalized = normalizedDecimal(value)
    if (normalized === null) {
        return 'Introduce un decimal positivo con coma o punto, máximo 16 enteros y 16 decimales.'
    }
    const zero = exactZero(normalized)
    if (zero && !explicitFree) return 'Para guardar cero, marca “Gratis explícitamente”.'
    if (!zero && explicitFree) return 'Un precio marcado como gratis debe ser exactamente cero.'
    return ''
}

export function priceVersionBody(value: string, explicitFree: boolean): PriceVersionResult {
    const error = priceError(value, explicitFree)
    if (error) return {body: null, error}
    const amount = normalizedDecimal(value)
    if (amount === null) return {body: null, error: 'El importe no es válido.'}
    return {body: {amount, explicit_free: explicitFree}, error: ''}
}

export function optionalPackagePrice(value: string, explicitFree: boolean): OptionalPackagePrice {
    if (!value.trim() && !explicitFree) return {value: null, explicit_free: false, error: ''}
    const parsed = priceVersionBody(value, explicitFree)
    return {
        value: parsed.body?.amount ?? null,
        explicit_free: parsed.body?.explicit_free ?? explicitFree,
        error: parsed.error,
    }
}

function record(value: unknown): Record<string, unknown> | null {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
        ? value as Record<string, unknown>
        : null
}

function positiveId(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function offsetValue(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function timestamp(value: unknown): value is string {
    return typeof value === 'string'
        && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
        && Number.isFinite(Date.parse(value))
}

function currencyCode(value: unknown): value is string {
    return typeof value === 'string' && /^[A-Z]{3}$/.test(value)
}

export function editionCurrency(value: unknown): string | null {
    const data = record(value)
    return data !== null && currencyCode(data.currency) ? data.currency : null
}

export function priceWriteResponse(value: unknown, requested: PriceVersionWrite): PriceWriteResponse | null {
    const data = record(value)
    const requestedAmount = canonicalDecimal(requested.amount)
    if (
        data === null
        || !positiveId(data.id)
        || typeof data.amount !== 'string'
        || canonicalDecimal(data.amount) === null
        || normalizedDecimal(data.amount) !== data.amount
        || canonicalDecimal(data.amount) !== requestedAmount
        || typeof data.explicit_free !== 'boolean'
        || data.explicit_free !== requested.explicit_free
        || exactZero(data.amount) !== data.explicit_free
        || !timestamp(data.valid_from)
    ) return null
    return {
        id: data.id,
        amount: data.amount,
        explicit_free: data.explicit_free,
        valid_from: data.valid_from,
    }
}

export function packageSummaries(value: unknown): PackageSummary[] | null {
    if (!Array.isArray(value)) return null
    const rows: PackageSummary[] = []
    for (const valueRow of value) {
        const row = record(valueRow)
        if (
            row === null
            || !positiveId(row.id)
            || !positiveId(row.food)
            || !positiveId(row.unit)
            || typeof row.food_name !== 'string'
            || typeof row.unit_name !== 'string'
            || typeof row.label !== 'string'
            || typeof row.quantity !== 'string'
            || normalizedDecimal(row.quantity) !== row.quantity
            || typeof row.is_reference !== 'boolean'
        ) return null
        let currentPrice: PackageSummary['current_price'] = null
        if (row.current_price !== null) {
            const current = record(row.current_price)
            if (
                current === null
                || !positiveId(current.id)
                || typeof current.amount !== 'string'
                || normalizedDecimal(current.amount) !== current.amount
                || typeof current.explicit_free !== 'boolean'
                || exactZero(current.amount) !== current.explicit_free
                || !timestamp(current.valid_from)
            ) return null
            currentPrice = {
                id: current.id,
                amount: current.amount,
                explicit_free: current.explicit_free,
                valid_from: current.valid_from,
            }
        }
        rows.push({
            id: row.id,
            food: row.food,
            food_name: row.food_name,
            unit: row.unit,
            unit_name: row.unit_name,
            label: row.label,
            quantity: row.quantity,
            is_reference: row.is_reference,
            current_price: currentPrice,
        })
    }
    return rows
}

function historyItem(value: unknown, currentPriceId: number | null): PriceHistoryItem | null {
    const row = record(value)
    if (row === null || !positiveId(row.id) || typeof row.amount !== 'string') return null
    const amount = normalizedDecimal(row.amount)
    if (amount === null || amount !== row.amount || typeof row.explicit_free !== 'boolean') return null
    const zero = exactZero(amount)
    if (zero !== row.explicit_free) return null
    if (!timestamp(row.valid_from) || !timestamp(row.created_at) || !positiveId(row.created_by)) return null
    if (typeof row.note !== 'string' || typeof row.is_current !== 'boolean') return null
    if (row.is_current !== (row.id === currentPriceId)) return null
    return row as PriceHistoryItem
}

export function priceHistoryEnvelope(
    value: unknown,
    packageId: number,
    offset: number,
): PriceHistoryEnvelope | null {
    const data = record(value)
    if (data === null || !positiveId(packageId) || !offsetValue(offset) || data.package !== packageId) return null
    if (!currencyCode(data.currency) || !timestamp(data.as_of)) return null
    const currentPriceId = data.current_price_id
    if (currentPriceId !== null && !positiveId(currentPriceId)) return null
    if (!offsetValue(data.count) || (data.next_offset !== null && !offsetValue(data.next_offset))) return null
    if (!Array.isArray(data.items) || data.items.length > PRICE_HISTORY_PAGE_SIZE) return null
    const items = data.items.map(item => historyItem(item, currentPriceId))
    if (items.some(item => item === null)) return null
    const typedItems = items as PriceHistoryItem[]
    if (new Set(typedItems.map(item => item.id)).size !== typedItems.length) return null
    if (typedItems.some(item => item.is_current && Date.parse(item.valid_from) > Date.parse(data.as_of as string))) return null
    const consumed = offset + typedItems.length
    const expectedNext = consumed < data.count ? consumed : null
    if (data.next_offset !== expectedNext || consumed < offset || offset > data.count) return null
    return data as PriceHistoryEnvelope
}

export function priceHistoryRequest(packageId: number, offset: number): string {
    if (!positiveId(packageId) || !offsetValue(offset)) throw new Error('Página de historial no válida.')
    return `/api/cuaderno/packages/${packageId}/prices/?limit=${PRICE_HISTORY_PAGE_SIZE}&offset=${offset}`
}

export function priceAmountLabel(amount: string, currency: string): string {
    const normalized = normalizedDecimal(amount)
    if (normalized === null || !currencyCode(currency)) return '—'
    return `${normalized.replace('.', ',')} ${currency}`
}

export function priceTimingLabel(item: PriceHistoryItem, asOf: string): string {
    if (item.is_current) return 'Actual'
    if (Date.parse(item.valid_from) > Date.parse(asOf)) return 'Programado; todavía no actual'
    return 'Histórico'
}
