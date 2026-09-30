export type ProductionWasteClassification = {
    schema_version: 1
    policy: 'declared_yield_estimate'
    classification_only: true
    included_in_gross_needs: true
    additional_stock_movement: false
    coverage: 'declared_yields_only'
    status: 'unknown' | 'incomplete' | 'declared'
    recorded_by: number
    recorded_at: string
    lines: ProductionWasteLine[]
}

export type ProductionWasteLine = {
    ingredient_id: number
    food_id: number | null
    food_name: string | null
    unit_id: number | null
    unit_name: string | null
    quantity_basis: 'gross' | 'net_usable'
    yield_ratio: string | null
    purchased_quantity: string
    useful_quantity: string | null
    waste_quantity: string | null
    cause: 'declared_yield'
}

const statuses = new Set(['unknown', 'incomplete', 'declared'])
const bases = new Set(['gross', 'net_usable'])

function record(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function exactKeys(value: Record<string, unknown>, expected: string[]) {
    const actual = Object.keys(value).sort()
    return actual.length === expected.length && expected.slice().sort().every((key, index) => key === actual[index])
}

function safeId(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function label(value: unknown): value is string {
    if (typeof value !== 'string') return false
    const characters = Array.from(value)
    return characters.length > 0 && characters.length <= 1024 && !characters.some(character => {
        const point = character.codePointAt(0) ?? 0
        return point < 32 || (point >= 127 && point <= 159) || (point >= 0xD800 && point <= 0xDFFF)
    })
}

function decimalString(value: unknown): value is string {
    if (typeof value !== 'string' || value.length > 160 || !/^[0-9]+(?:\.[0-9]+)?$/.test(value)) return false
    const [integer, fraction = ''] = value.split('.')
    const joined = `${integer}${fraction}`
    const first = joined.search(/[1-9]/)
    const significant = first === -1 ? 1 : joined.length - first
    if (significant > 64) return false
    const integerValue = integer.replace(/^0+/, '')
    if (integerValue) return integerValue.length - 1 <= 64
    if (first === -1) return true
    const firstFractionDigit = fraction.search(/[1-9]/)
    return firstFractionDigit !== -1 && -(firstFractionDigit + 1) >= -64
}

function ratioString(value: unknown): value is string {
    if (!decimalString(value) || !/[1-9]/.test(value)) return false
    const [integer, fraction = ''] = value.split('.')
    const normalizedInteger = integer.replace(/^0+/, '') || '0'
    return normalizedInteger === '0' || (normalizedInteger === '1' && !/[1-9]/.test(fraction))
}

function optionalIdentity(identifier: unknown, name: unknown) {
    return (identifier === null && name === null) || (safeId(identifier) && label(name))
}

function lineEnvelope(value: unknown): value is ProductionWasteLine {
    if (!record(value) || !exactKeys(value, [
        'ingredient_id', 'food_id', 'food_name', 'unit_id', 'unit_name', 'quantity_basis',
        'yield_ratio', 'purchased_quantity', 'useful_quantity', 'waste_quantity', 'cause',
    ])) return false
    if (!safeId(value.ingredient_id)
        || !optionalIdentity(value.food_id, value.food_name)
        || !optionalIdentity(value.unit_id, value.unit_name)
        || (value.food_id === null && value.unit_id !== null)
        || typeof value.quantity_basis !== 'string' || !bases.has(value.quantity_basis)
        || value.cause !== 'declared_yield' || !decimalString(value.purchased_quantity)) return false
    if (value.yield_ratio === null) {
        return value.quantity_basis === 'gross'
            && value.useful_quantity === null && value.waste_quantity === null
    }
    return ratioString(value.yield_ratio)
        && decimalString(value.useful_quantity) && decimalString(value.waste_quantity)
}

export function productionWasteEnvelope(value: unknown): ProductionWasteClassification | null {
    if (!record(value) || !exactKeys(value, [
        'schema_version', 'policy', 'classification_only', 'included_in_gross_needs',
        'additional_stock_movement', 'coverage', 'status', 'recorded_by', 'recorded_at', 'lines',
    ])) return null
    if (value.schema_version !== 1 || value.policy !== 'declared_yield_estimate'
        || value.classification_only !== true || value.included_in_gross_needs !== true
        || value.additional_stock_movement !== false || value.coverage !== 'declared_yields_only'
        || typeof value.status !== 'string' || !statuses.has(value.status)
        || !safeId(value.recorded_by) || typeof value.recorded_at !== 'string'
        || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value.recorded_at)
        || !Array.isArray(value.lines) || value.lines.length > 10000) return null
    const lines = value.lines
    if (!lines.every(lineEnvelope)) return null
    const incomplete = lines.some(line => line.yield_ratio === null
        || line.food_id === null || line.unit_id === null)
    const expectedStatus = lines.length === 0 ? 'unknown' : incomplete ? 'incomplete' : 'declared'
    return value.status === expectedStatus ? value as ProductionWasteClassification : null
}
