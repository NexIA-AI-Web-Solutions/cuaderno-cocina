export type QuantityBasis = 'gross' | 'net_usable'

export type IngredientYieldBody = {
    ingredient: number
    quantity_basis: QuantityBasis
    yield_ratio: string | null
}

export type IngredientYield = {
    id: number
    food_name: string | null
    amount: string
    unit: string | null
    quantity_basis: QuantityBasis
    yield_ratio: string | null
    is_subrecipe: boolean
}

export type IngredientYieldResponse = {
    recipe_id: number
    edition: 'esencial' | 'profesional' | 'integral'
    can_edit: boolean
    revision: string
    ingredients: IngredientYield[]
}

export type IngredientYieldWriteBody = IngredientYieldBody & {revision: string}

function isRecord(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isPositiveId(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function isRevision(value: unknown): value is string {
    return typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
}

function isFixedDecimal(value: unknown): value is string {
    if (typeof value !== 'string') return false
    const match = /^-?(\d+)(?:\.(\d+))?$/.exec(value)
    if (!match) return false
    const whole = match[1] || ''
    const fraction = match[2] || ''
    return whole.length <= 16 && fraction.length <= 16 && whole.length + fraction.length <= 32
}

export function ingredientAmountLabel(amount: unknown): string {
    if (!isFixedDecimal(amount)) return 'Cantidad no válida'
    const negative = amount.startsWith('-')
    const [rawWhole, rawFraction = ''] = (negative ? amount.slice(1) : amount).split('.')
    const whole = (rawWhole || '0').replace(/^0+(?=\d)/, '')
    const fraction = rawFraction.replace(/0+$/, '')
    const sign = negative && (whole !== '0' || fraction) ? '-' : ''
    return `${sign}${whole}${fraction ? `,${fraction}` : ''}`
}

function isYieldRatio(value: unknown): value is string {
    if (typeof value !== 'string') return false
    const belowOne = /^0\.(\d{1,16})$/.exec(value)
    if (belowOne) return /[1-9]/.test(belowOne[1] || '')
    return /^1(?:\.0{1,16})?$/.test(value)
}

export function ingredientYieldEnvelope(data: unknown): IngredientYieldResponse | null {
    if (!isRecord(data)
        || !isPositiveId(data.recipe_id)
        || (data.edition !== 'esencial' && data.edition !== 'profesional' && data.edition !== 'integral')
        || typeof data.can_edit !== 'boolean'
        || !isRevision(data.revision)
        || !Array.isArray(data.ingredients)) return null
    if (data.edition === 'esencial' && data.can_edit) return null
    const ingredients: IngredientYield[] = []
    const ingredientIds = new Set<number>()
    for (const ingredient of data.ingredients) {
        if (!isRecord(ingredient)
            || !isPositiveId(ingredient.id)
            || (ingredient.food_name !== null && typeof ingredient.food_name !== 'string')
            || !isFixedDecimal(ingredient.amount)
            || (ingredient.unit !== null && typeof ingredient.unit !== 'string')
            || (ingredient.quantity_basis !== 'gross' && ingredient.quantity_basis !== 'net_usable')
            || typeof ingredient.is_subrecipe !== 'boolean') return null
        if (ingredientIds.has(ingredient.id)) return null
        ingredientIds.add(ingredient.id)
        if (ingredient.is_subrecipe) {
            if (ingredient.quantity_basis !== 'gross' || ingredient.yield_ratio !== null) return null
        } else if (ingredient.yield_ratio === null) {
            if (ingredient.quantity_basis === 'net_usable') return null
        } else if (!isYieldRatio(ingredient.yield_ratio)) return null
        ingredients.push({
            id: ingredient.id, food_name: ingredient.food_name, amount: ingredient.amount,
            unit: ingredient.unit, quantity_basis: ingredient.quantity_basis,
            yield_ratio: ingredient.yield_ratio, is_subrecipe: ingredient.is_subrecipe,
        })
    }
    return {
        recipe_id: data.recipe_id,
        edition: data.edition,
        can_edit: data.can_edit,
        revision: data.revision,
        ingredients,
    }
}

export function ingredientYieldSaveEnvelope(
    data: unknown,
    recipeId: unknown,
    ingredientId: unknown,
): IngredientYieldResponse | null {
    if (!isPositiveId(recipeId) || !isPositiveId(ingredientId)) return null
    const envelope = ingredientYieldEnvelope(data)
    if (envelope === null || envelope.recipe_id !== recipeId) return null
    return envelope.ingredients.filter(ingredient => ingredient.id === ingredientId).length === 1 ? envelope : null
}

export function withYieldRevision(
    body: IngredientYieldBody,
    revision: unknown,
): {body: IngredientYieldWriteBody | null; error: string} {
    if (!isRevision(revision)) {
        return {body: null, error: 'La versión de las mermas no es válida; recarga los datos antes de guardar.'}
    }
    return {body: {...body, revision}, error: ''}
}

export function ingredientYieldConflictMessage(status: number): string {
    return status === 409
        ? 'Otra persona cambió las mermas de esta receta. Conservamos tus cambios; recarga los datos cuando quieras compararlos.'
        : ''
}

const YIELD_SCALE = BigInt('10000000000000000')

export function ingredientYieldBody(
    ingredient: number,
    quantityBasis: QuantityBasis,
    rawRatio: unknown,
    isSubrecipe = false,
): {body: IngredientYieldBody | null; error: string} {
    if (isSubrecipe) {
        return {body: null, error: 'Las subelaboraciones ya tienen rendimiento propio; evita aplicar una doble merma.'}
    }
    if (!Number.isInteger(ingredient) || ingredient <= 0 || !['gross', 'net_usable'].includes(quantityBasis)) {
        return {body: null, error: 'El ingrediente o la base de cantidad no son válidos.'}
    }
    if (typeof rawRatio !== 'string') {
        return {body: null, error: 'El rendimiento debe ser un decimal exacto escrito como texto.'}
    }
    const ratio = rawRatio.trim().replace(',', '.')
    if (!ratio) {
        if (quantityBasis === 'net_usable') {
            return {body: null, error: 'La cantidad neta útil necesita un rendimiento entre 0 y 1.'}
        }
        return {body: {ingredient, quantity_basis: quantityBasis, yield_ratio: null}, error: ''}
    }
    const belowOne = /^0\.(\d{1,16})$/.exec(ratio)
    const one = /^1(?:\.0{1,16})?$/.test(ratio)
    const belowOneFraction = belowOne?.[1] || ''
    if ((!belowOne || !/[1-9]/.test(belowOneFraction)) && !one) {
        return {body: null, error: 'El rendimiento debe ser un decimal exacto entre 0 y 1, con hasta 16 decimales.'}
    }
    return {body: {ingredient, quantity_basis: quantityBasis, yield_ratio: ratio}, error: ''}
}

export function quantityBasisLabel(basis: QuantityBasis): string {
    return basis === 'net_usable' ? 'Cantidad neta útil' : 'Cantidad bruta'
}

function scaledRatio(ratio: string): bigint | null {
    const match = /^(0|1)(?:\.(\d{1,16}))?$/.exec(ratio)
    if (!match) return null
    const whole = match[1]
    if (whole !== '0' && whole !== '1') return null
    return BigInt(whole) * YIELD_SCALE + BigInt((match[2] || '').padEnd(16, '0') || '0')
}

function percentLabel(scaled: bigint): string {
    const percent = scaled * 100n
    const whole = percent / YIELD_SCALE
    const fraction = (percent % YIELD_SCALE).toString().padStart(16, '0').replace(/0+$/, '')
    return `${whole}${fraction ? `,${fraction}` : ''} %`
}

export function yieldSummary(ratio: string | null): string {
    if (ratio == null) return 'Rendimiento no declarado'
    const scaled = scaledRatio(ratio)
    if (scaled == null || scaled <= 0n || scaled > YIELD_SCALE) return 'Rendimiento no declarado'
    return `Rendimiento ${percentLabel(scaled)} · merma ${percentLabel(YIELD_SCALE - scaled)}`
}
