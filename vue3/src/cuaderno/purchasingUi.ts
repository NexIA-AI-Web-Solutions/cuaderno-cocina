export type PurchaseOfferRow = {id: number; package: number; supplier: number; amount: string; currency: string; valid_from: string}
export type PurchaseOrderRow = {id: number; quantity: string; received_quantity: string; unit: number; supplier_name: string; package: number | null; price_snapshot: string | null; currency_snapshot: string; state: string}
export type PurchaseReceiptRow = {id: number; quantity: string; movement: number; reversed_by: number | null}

function record(value: unknown): Record<string, unknown> | null {
    return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null
}
function id(value: unknown): value is number { return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 }
function decimal(value: unknown, zero = true): value is string {
    return typeof value === 'string' && /^\d+(?:\.\d+)?$/.test(value) && (zero || /[1-9]/.test(value))
}
function currency(value: unknown): value is string { return typeof value === 'string' && /^[A-Z]{3}$/.test(value) }
function items(value: unknown): unknown[] | null {
    if (Array.isArray(value)) return value
    const envelope = record(value)
    return envelope && Array.isArray(envelope.results) ? envelope.results : null
}

export function purchaseOffers(value: unknown): PurchaseOfferRow[] | null {
    const rows = items(value); if (rows === null) return null
    const parsed: PurchaseOfferRow[] = []
    for (const item of rows) {
        const row = record(item)
        if (!row || !id(row.id) || !id(row.package) || !id(row.supplier) || !decimal(row.amount)
            || !currency(row.currency) || typeof row.valid_from !== 'string' || !Number.isFinite(Date.parse(row.valid_from))) return null
        parsed.push(row as PurchaseOfferRow)
    }
    return new Set(parsed.map(row => row.id)).size === parsed.length ? parsed : null
}

const ORDER_STATES = new Set(['draft', 'ordered', 'part_received', 'received', 'cancelled'])
export function purchaseOrders(value: unknown): PurchaseOrderRow[] | null {
    const rows = items(value); if (rows === null) return null
    const parsed: PurchaseOrderRow[] = []
    for (const item of rows) {
        const row = record(item)
        if (!row || !id(row.id) || !decimal(row.quantity, false) || !decimal(row.received_quantity)
            || !id(row.unit) || typeof row.supplier_name !== 'string'
            || (row.package !== null && !id(row.package))
            || (row.price_snapshot !== null && !decimal(row.price_snapshot))
            || !currency(row.currency_snapshot) || typeof row.state !== 'string' || !ORDER_STATES.has(row.state)) return null
        parsed.push(row as PurchaseOrderRow)
    }
    return new Set(parsed.map(row => row.id)).size === parsed.length ? parsed : null
}

export function purchaseReceipts(value: unknown): PurchaseReceiptRow[] | null {
    const rows = items(value); if (rows === null) return null
    const parsed: PurchaseReceiptRow[] = []
    for (const item of rows) {
        const row = record(item)
        if (!row || !id(row.id) || !decimal(row.quantity, false) || !id(row.movement)
            || (row.reversed_by !== null && !id(row.reversed_by))) return null
        parsed.push(row as PurchaseReceiptRow)
    }
    return new Set(parsed.map(row => row.id)).size === parsed.length ? parsed : null
}
