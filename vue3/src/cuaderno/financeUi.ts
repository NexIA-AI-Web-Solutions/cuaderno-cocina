export type FinanceInput = {value: string | null; error: string}
export type FinancePayload = {
    selling_price_per_serving: string | null
    budget_per_person: string | null
}
export type FinanceErrors = Partial<Record<keyof FinancePayload, string>>
export type RecipeFinance = FinancePayload & {
    ingredient_cost_per_serving: string | null
    difference_per_serving: string | null
    food_cost_ratio: string | null
    budget_gap_per_person: string | null
    price_policy: string | null
    status: string
    warnings?: string[]
    net_profit: null
}

export function financeDecimalInput(value: string): FinanceInput {
    const normalized = value.trim().replace(',', '.')
    if (!normalized) return {value: null, error: ''}
    if (/^\d+\.\d{5,}$/.test(normalized)) {
        return {value: null, error: 'Usa como máximo cuatro decimales.'}
    }
    if (!/^\d{1,28}(?:\.\d{1,4})?$/.test(normalized)) {
        return {value: null, error: 'Introduce un decimal positivo o cero, con un máximo de 28 dígitos enteros.'}
    }
    return {value: normalized, error: ''}
}

export function financeBody(sellingPrice: string, budget: string): {
    body: FinancePayload | null
    errors: FinanceErrors
} {
    const selling = financeDecimalInput(sellingPrice)
    const perPerson = financeDecimalInput(budget)
    const errors: FinanceErrors = {}
    if (selling.error) errors.selling_price_per_serving = selling.error
    if (perPerson.error) errors.budget_per_person = perPerson.error
    return {
        body: Object.keys(errors).length ? null : {
            selling_price_per_serving: selling.value,
            budget_per_person: perPerson.value,
        },
        errors,
    }
}

export function pricePolicyLabel(policy: string | null): string {
    if (policy === 'net') return 'neto'
    if (policy === 'gross') return 'bruto'
    return 'política desconocida'
}

function groupedInteger(value: string): string {
    const normalized = value.replace(/^0+(?=\d)/, '') || '0'
    return normalized.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

function decimalParts(value: string): {sign: string; whole: string; fraction: string} | null {
    const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value)
    if (!match) return null
    const [, sign = '', whole = '', fraction = ''] = match
    return {sign, whole, fraction}
}

export function financeMoneyLabel(value: string | null, currency = '€'): string {
    if (value == null) return '—'
    const parts = decimalParts(value)
    if (!parts) return '—'
    const fraction = parts.fraction.padEnd(3, '0')
    const unroundedCents = `${parts.whole}${fraction.slice(0, 2)}`.replace(/^0+(?=\d)/, '')
    const roundingDigit = fraction.slice(2, 3)
    const roundedCents = BigInt(unroundedCents || '0') + ('56789'.includes(roundingDigit) ? 1n : 0n)
    const digits = roundedCents.toString().padStart(3, '0')
    const whole = digits.slice(0, -2)
    const cents = digits.slice(-2)
    const sign = parts.sign && roundedCents !== 0n ? parts.sign : ''
    return `${sign}${groupedInteger(whole)},${cents} ${currency}`
}

export function financeRatioLabel(value: string | null): string {
    if (value == null) return '—'
    const parts = decimalParts(value)
    if (!parts) return '—'
    const firstTwo = parts.fraction.padEnd(2, '0').slice(0, 2)
    const wholePercent = groupedInteger(`${parts.whole}${firstTwo}`)
    const remainder = parts.fraction.slice(2).replace(/0+$/, '')
    return `${parts.sign}${wholePercent}${remainder ? `,${remainder}` : ''} %`
}

export function financeWarningLabel(code: string): string {
    const labels: Record<string, string> = {
        selling_price_unknown: 'Falta el precio de venta por ración.',
        selling_price_zero: 'El precio de venta es cero; no se calcula porcentaje ni diferencia.',
        budget_unknown: 'Falta el presupuesto por persona.',
        cost_incomplete: 'El coste de ingredientes está incompleto.',
        price_policy_unknown: 'La política de precio no está configurada.',
        currency_unsupported: 'La moneda configurada no admite este cálculo financiero.',
        precio_desconocido: 'Falta el precio de algún ingrediente.',
        needs_conversion: 'Falta una conversión de unidades.',
    }
    return labels[code] || code
}
