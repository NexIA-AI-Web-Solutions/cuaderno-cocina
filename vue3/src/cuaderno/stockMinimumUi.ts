export type StockMinimumBody = {
    food: number
    unit: number
    quantity: string | null
    location: number | null
}

export type StockMinimumLocation = {id: number; name: string}

export type StockMinimumRow = {
    id: number
    household: number
    food: number
    food_name: string
    unit: number
    unit_name: string
    quantity: string
    location: number | null
    location_name: string | null
    updated_by: number
    updated_at: string
}

export type StockMinimumEnvelope = {
    edition: 'integral'
    items: StockMinimumRow[]
    household: {id: number; name: string}
    locations: StockMinimumLocation[]
}

function record(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function canonicalPositiveDecimal(value: unknown): value is string {
    if (typeof value !== 'string') return false
    const match = /^(?:0\.(\d*[1-9])|([1-9]\d*)(?:\.(\d*[1-9]))?)$/.exec(value)
    if (!match) return false
    const whole = match[2] || '0'
    const fraction = match[1] || match[3] || ''
    return whole.length <= 16 && fraction.length <= 16 && whole.length + fraction.length <= 32
}

export function stockMinimumEnvelope(data: unknown): StockMinimumEnvelope | null {
    if (!record(data)) return null
    const envelope = data
    if (envelope.edition !== 'integral') return null
    if (!Array.isArray(envelope.items) || !Array.isArray(envelope.locations)) return null
    if (!record(envelope.household)) return null
    const household = envelope.household
    if (!positiveId(household.id) || typeof household.name !== 'string') return null
    const locations: StockMinimumLocation[] = []
    const locationNames = new Map<number, string>()
    for (const location of envelope.locations) {
        if (!record(location) || !positiveId(location.id) || typeof location.name !== 'string') return null
        if (locationNames.has(location.id)) return null
        locationNames.set(location.id, location.name)
        locations.push({id: location.id, name: location.name})
    }
    const items: StockMinimumRow[] = []
    for (const item of envelope.items) {
        if (!record(item)
            || !positiveId(item.id) || !positiveId(item.household) || item.household !== household.id
            || !positiveId(item.food) || typeof item.food_name !== 'string'
            || !positiveId(item.unit) || typeof item.unit_name !== 'string'
            || !canonicalPositiveDecimal(item.quantity)
            || !positiveId(item.updated_by) || typeof item.updated_at !== 'string') return null
        if (item.location === null) {
            if (item.location_name !== null) return null
        } else if (!positiveId(item.location)
            || typeof item.location_name !== 'string'
            || locationNames.get(item.location) !== item.location_name) return null
        items.push({
            id: item.id, household: item.household, food: item.food, food_name: item.food_name,
            unit: item.unit, unit_name: item.unit_name, quantity: item.quantity,
            location: item.location, location_name: item.location_name,
            updated_by: item.updated_by, updated_at: item.updated_at,
        })
    }
    return {
        edition: 'integral',
        items,
        household: {id: household.id, name: household.name},
        locations,
    }
}

export function stockMinimumItems(data: unknown): StockMinimumRow[] | null {
    return stockMinimumEnvelope(data)?.items ?? null
}

export type ReplenishmentLocationShortfall = {
    location: number
    location_name: string
    minimum_stock: string
    usable_stock: string
    missing: string
}

export type ReplenishmentRow = {
    food: number
    unit: number
    required: string
    minimum_stock: string | null
    target_stock: string | null
    usable_stock: string
    missing: string
    package: number | null
    packages: string | null
    purchase_quantity: string | null
    reference_price: string | null
    currency: string
    location_shortfalls: ReplenishmentLocationShortfall[]
}

export type ReplenishmentEnvelope = {items: ReplenishmentRow[]}

function canonicalDecimal(value: unknown): value is string {
    if (typeof value !== 'string' || value.length > 1024) return false
    const match = /^(?:0|0\.(\d*[1-9])|([1-9]\d*)(?:\.(\d*[1-9]))?)$/.exec(value)
    if (!match) return false
    const whole = match[2] || '0'
    const fraction = match[1] || match[3] || ''
    // Replenishment includes unit conversions calculated with the backend's
    // 64-digit Decimal context. Fractional zeroes before the first non-zero
    // digit express scale and do not consume significant precision.
    const significantDigits = `${whole}${fraction}`.replace(/^0+/, '').replace(/0+$/, '')
    return significantDigits.length <= 64
}

function canonicalNullableDecimal(value: unknown): value is string | null {
    return value === null || canonicalDecimal(value)
}

export function replenishmentEnvelope(data: unknown): ReplenishmentEnvelope | null {
    if (!record(data) || !Array.isArray(data.items)) return null
    const items: ReplenishmentRow[] = []
    for (const item of data.items) {
        if (!record(item)
            || !positiveId(item.food) || !positiveId(item.unit)
            || !canonicalDecimal(item.required) || !canonicalNullableDecimal(item.minimum_stock)
            || !canonicalNullableDecimal(item.target_stock) || !canonicalDecimal(item.usable_stock)
            || !canonicalDecimal(item.missing)
            || (item.package !== null && !positiveId(item.package))
            || !canonicalNullableDecimal(item.packages)
            || !canonicalNullableDecimal(item.purchase_quantity)
            || !canonicalNullableDecimal(item.reference_price)
            || typeof item.currency !== 'string' || !/^[A-Z]{3}$/.test(item.currency)
            || !Array.isArray(item.location_shortfalls)) return null
        if (item.package === null
            ? item.packages !== null || item.purchase_quantity !== null
            : item.packages === null || item.purchase_quantity === null) return null
        const locationShortfalls: ReplenishmentLocationShortfall[] = []
        for (const shortfall of item.location_shortfalls) {
            if (!record(shortfall) || !positiveId(shortfall.location)
                || typeof shortfall.location_name !== 'string'
                || !canonicalDecimal(shortfall.minimum_stock)
                || !canonicalDecimal(shortfall.usable_stock)
                || !canonicalDecimal(shortfall.missing)) return null
            locationShortfalls.push({
                location: shortfall.location, location_name: shortfall.location_name,
                minimum_stock: shortfall.minimum_stock, usable_stock: shortfall.usable_stock,
                missing: shortfall.missing,
            })
        }
        items.push({
            food: item.food, unit: item.unit, required: item.required,
            minimum_stock: item.minimum_stock, target_stock: item.target_stock,
            usable_stock: item.usable_stock, missing: item.missing,
            package: item.package, packages: item.packages, purchase_quantity: item.purchase_quantity,
            reference_price: item.reference_price, currency: item.currency,
            location_shortfalls: locationShortfalls,
        })
    }
    return {items}
}

function positiveId(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function positiveDecimal(value: unknown): {value: string | null; error: string} {
    if (typeof value !== 'string') {
        return {value: null, error: 'La cantidad debe ser un decimal exacto escrito como texto.'}
    }
    const normalized = value.trim().replace(',', '.')
    if (!normalized) return {value: null, error: ''}
    const match = /^(\d+)(?:\.(\d+))?$/.exec(normalized)
    const whole = match?.[1] || ''
    const fraction = match?.[2] || ''
    if (!match || whole.length > 16 || whole.length + fraction.length > 32 || fraction.length > 16) {
        return {value: null, error: 'Introduce un decimal exacto positivo, con hasta 32 dígitos y 16 decimales.'}
    }
    if (!/[1-9]/.test(`${whole}${fraction}`)) {
        return {value: null, error: 'La cantidad mínima debe ser un decimal positivo.'}
    }
    return {value: normalized, error: ''}
}

export function stockMinimumBody(
    food: unknown,
    unit: unknown,
    quantity: unknown,
    location: unknown,
): {body: StockMinimumBody | null; error: string} {
    if (!positiveId(food) || !positiveId(unit) || (location !== null && !positiveId(location))) {
        return {body: null, error: 'Selecciona un alimento, una unidad y una ubicación válidos.'}
    }
    const parsed = positiveDecimal(quantity)
    if (parsed.error) return {body: null, error: parsed.error}
    return {body: {food, unit, quantity: parsed.value, location}, error: ''}
}

type DecimalParts = {integer: bigint; scale: number}

function decimalParts(value: string): DecimalParts | null {
    const match = /^(\d+)(?:\.(\d+))?$/.exec(value)
    if (!match) return null
    const whole = match[1]
    if (whole === undefined) return null
    const fraction = match[2] || ''
    return {integer: BigInt(`${whole}${fraction}`), scale: fraction.length}
}

function powerOfTen(exponent: number): bigint {
    return BigInt(`1${'0'.repeat(exponent)}`)
}

function decimalText(integer: bigint, scale: number): string {
    const negative = integer < 0n
    const unsigned = negative ? -integer : integer
    const digits = unsigned.toString().padStart(scale + 1, '0')
    const whole = scale ? digits.slice(0, -scale) : digits
    const fraction = scale ? digits.slice(-scale).replace(/0+$/, '') : ''
    return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`
}

export function replenishmentExcess(purchaseQuantity: string | null, missing: string): string | null {
    if (purchaseQuantity === null) return null
    const purchase = decimalParts(purchaseQuantity)
    const shortage = decimalParts(missing)
    if (!purchase || !shortage) return null
    const scale = Math.max(purchase.scale, shortage.scale)
    const value = purchase.integer * powerOfTen(scale - purchase.scale)
        - shortage.integer * powerOfTen(scale - shortage.scale)
    return decimalText(value, scale)
}

export function minimumScopeLabel(locationName: string | null): string {
    return locationName ? `Ubicación: ${locationName}` : 'Todo el hogar'
}
