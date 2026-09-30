export type QuantityBasis = 'gross' | 'net_usable'

export type IngredientYieldBody = {
    ingredient: number
    quantity_basis: QuantityBasis
    yield_ratio: string | null
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
