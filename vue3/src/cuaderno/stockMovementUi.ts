type UnknownRecord = Record<string, unknown>

function record(value: unknown): UnknownRecord | null {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
        ? value as UnknownRecord
        : null
}

function positiveInteger(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function decimalText(value: unknown): value is string {
    return typeof value === 'string' && /^\d+(?:\.\d+)?$/.test(value)
}

export function buildStandaloneWasteCause(value: unknown): string | null {
    if (typeof value !== 'string') return null
    if (Array.from(value).some(character => {
        const codePoint = character.codePointAt(0) ?? -1
        return codePoint <= 0x1f
            || (codePoint >= 0x7f && codePoint <= 0x9f)
            || (codePoint >= 0xd800 && codePoint <= 0xdfff)
    })) return null
    const cause = value.trim()
    return cause && Array.from(cause).length <= 256 ? cause : null
}

export function standaloneWasteCauseLength(value: unknown): number {
    return typeof value === 'string' ? Array.from(value.trim()).length : 0
}

export function movementOriginType(row: unknown): string | null {
    const movement = record(row)
    const metadata = record(movement?.metadata_snapshot)
    const origin = record(metadata?.origin)
    return typeof origin?.type === 'string' ? origin.type : null
}

export function isPurchaseMovement(row: unknown): boolean {
    return movementOriginType(row) === 'purchase_order'
}

export function isServiceProductionMovement(row: unknown): boolean {
    return movementOriginType(row) === 'service_plan'
}

export function standaloneWasteCause(row: unknown): string | null {
    if (movementOriginType(row) !== 'standalone_waste') return null
    const movement = record(row)
    const metadata = record(movement?.metadata_snapshot)
    const origin = record(metadata?.origin)
    return buildStandaloneWasteCause(origin?.cause)
}

export function canReverseGeneric(row: unknown, history: unknown): boolean {
    const movement = record(row)
    if (!movement || !positiveInteger(movement.id)) return false
    if (movement.kind === 'reversal' || (movement.reverses !== null && movement.reverses !== undefined)) return false
    if (isPurchaseMovement(movement) || isServiceProductionMovement(movement)) return false
    if (!Array.isArray(history)) return false
    return !history.some(item => {
        const candidate = record(item)
        return candidate?.reverses === movement.id
    })
}

function pricePolicyText(value: unknown): string {
    if (value === 'net') return 'precio neto'
    if (value === 'gross') return 'precio bruto'
    return 'política de precio desconocida'
}

function replacementValuation(row: unknown): UnknownRecord | null {
    const movement = record(row)
    const metadata = record(movement?.metadata_snapshot)
    const valuation = record(metadata?.valuation)
    return valuation?.policy === 'replacement_estimate' ? valuation : null
}

export function hasReplacementValuation(row: unknown): boolean {
    return replacementValuation(row) !== null
}

export function replacementValuationLabel(row: unknown): string | null {
    const valuation = replacementValuation(row)
    if (!valuation) return null
    if (valuation.status !== 'complete' || valuation.amount === null) {
        return 'Coste de reposición estimado: desconocido.'
    }
    const input = record(valuation.input)
    const currency = valuation.currency
    if (
        !decimalText(valuation.amount)
        || !input
        || !decimalText(input.quantity)
        || typeof currency !== 'string'
        || !/^[A-Z]{3}$/.test(currency)
    ) {
        return 'Coste de reposición estimado: desconocido.'
    }
    return `Coste de reposición estimado: ${valuation.amount} ${currency} (${pricePolicyText(valuation.price_policy)}).`
}
