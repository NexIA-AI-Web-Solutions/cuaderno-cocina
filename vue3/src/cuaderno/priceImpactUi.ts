export type ImpactSheet = {
    status: 'complete' | 'incomplete' | 'needs_conversion' | 'invalid'
    unrounded: string | null
    per_serving: string | null
    servings: string
    warnings: string[]
}

export type PriceImpact = {
    recipe_id: number
    package: number
    as_of: string
    current_price_id: number | null
    previous_price_id: number | null
    affected: boolean
    before: ImpactSheet
    after: ImpactSheet
    difference: string | null
    difference_per_serving: string | null
    currency: string
    price_policy: '' | 'net' | 'gross'
}

function positiveId(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function servingsText(value: string): string | null {
    const text = value.trim().replace(',', '.')
    return /^[0-9]{1,16}(?:\.[0-9]{1,16})?$/.test(text) && /[1-9]/.test(text) ? text : null
}

function object(value: unknown): Record<string, unknown> | null {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
        ? value as Record<string, unknown> : null
}

function moneyText(value: unknown, signed = false): value is string {
    if (typeof value !== 'string' || value.length > 2050) return false
    return (signed ? /^-?[0-9]+(?:\.[0-9]+)?$/ : /^[0-9]+(?:\.[0-9]+)?$/).test(value)
}

function decimalKey(value: string): string {
    const [whole = '', fraction = ''] = value.split('.')
    return `${whole.replace(/^0+(?=[0-9])/, '')}.${fraction.replace(/0+$/, '')}`
}

function sheet(value: unknown, target: string): ImpactSheet | null {
    const data = object(value)
    if (!data || typeof data.status !== 'string'
        || !['complete', 'incomplete', 'needs_conversion', 'invalid'].includes(data.status)) return null
    if (typeof data.servings !== 'string' || servingsText(data.servings) === null
        || decimalKey(data.servings) !== decimalKey(target)) return null
    if (!Array.isArray(data.warnings) || data.warnings.some(value => typeof value !== 'string')) return null
    if (data.status === 'complete') {
        if (!moneyText(data.unrounded) || !moneyText(data.per_serving)) return null
    } else if (data.unrounded !== null || data.per_serving !== null) return null
    return data as ImpactSheet
}

export function priceImpactRequest(recipeId: number, packageId: number, servings: string): string | null {
    const target = servingsText(servings)
    if (!positiveId(recipeId) || !positiveId(packageId) || target === null) return null
    return `/api/cuaderno/recipes/${recipeId}/price-impact/?package=${packageId}&servings=${target}`
}

export function priceImpactEnvelope(
    value: unknown, recipeId: number, packageId: number, servings: string,
): PriceImpact | null {
    const data = object(value)
    const target = servingsText(servings)
    if (!data || target === null || !positiveId(recipeId) || !positiveId(packageId)
        || data.recipe_id !== recipeId || data.package !== packageId || typeof data.affected !== 'boolean') return null
    if ((data.current_price_id !== null && !positiveId(data.current_price_id))
        || (data.previous_price_id !== null && !positiveId(data.previous_price_id))) return null
    if (typeof data.as_of !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(data.as_of)
        || !Number.isFinite(Date.parse(data.as_of))) return null
    if (typeof data.currency !== 'string' || !/^[A-Z]{3}$/.test(data.currency)
        || typeof data.price_policy !== 'string' || !['', 'net', 'gross'].includes(data.price_policy)) return null
    const before = sheet(data.before, target)
    const after = sheet(data.after, target)
    if (before === null || after === null) return null
    if (before.status === 'complete' && after.status === 'complete') {
        if (!moneyText(data.difference, true) || !moneyText(data.difference_per_serving, true)) return null
    } else if (data.difference !== null || data.difference_per_serving !== null) return null
    if (!data.affected) {
        const equivalentMoney = (left: string | null, right: string | null) => left === null || right === null
            ? left === right : decimalKey(left) === decimalKey(right)
        if (before.status !== after.status || !equivalentMoney(before.unrounded, after.unrounded)
            || !equivalentMoney(before.per_serving, after.per_serving)
            || JSON.stringify(before.warnings) !== JSON.stringify(after.warnings)) return null
        if (before.status === 'complete'
            && (!/^-?0+(?:\.0+)?$/.test(data.difference as string)
                || !/^-?0+(?:\.0+)?$/.test(data.difference_per_serving as string))) return null
    }
    return data as PriceImpact
}
