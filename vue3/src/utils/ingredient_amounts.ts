/** Native ingredient amounts stay decimal strings through editing and saving. */
type AmountResult = {value: string | null; error: string}
type AmountChange<T> = {ingredient: T; amount: string}
type AmountPlan<T> = {changes: AmountChange<T>[] | null; error: string}

export function normalizeIngredientAmount(input: unknown): AmountResult {
    if (typeof input !== 'string') return {value: null, error: 'Introduce una cantidad numérica válida.'}
    const text = input.trim()
    if (!text) return {value: null, error: 'Indica una cantidad.'}
    if (text.length > 1000) return {value: null, error: 'La cantidad es demasiado larga.'}
    const match = /^([+-]?)(\d+)(?:[.,](\d*))?$/.exec(text)
    if (!match) return {value: null, error: 'Introduce una cantidad numérica válida; puedes usar coma o punto decimal.'}
    const whole = (match[2] || '0').replace(/^0+(?=\d)/, '')
    const fraction = (match[3] || '').replace(/0+$/, '')
    if (whole.length > 16) return {value: null, error: 'La cantidad admite como máximo 16 dígitos enteros.'}
    if (fraction.length > 16) return {value: null, error: 'La cantidad admite como máximo 16 decimales.'}
    if (whole.length + fraction.length > 32) return {value: null, error: 'La cantidad admite como máximo 32 dígitos en total.'}
    const sign = match[1] === '-' && (whole !== '0' || fraction) ? '-' : ''
    return {value: `${sign}${whole}${fraction ? `.${fraction}` : ''}`, error: ''}
}

export function ingredientAmountRule(input: unknown): true | string {
    return normalizeIngredientAmount(input).error || true
}

export function autocorrectIngredientAmount(ingredient: {amount: unknown}): void {
    const result = normalizeIngredientAmount(ingredient.amount)
    if (result.value !== null) ingredient.amount = result.value
}

export function ingredientAmountLabel(input: unknown): string {
    const result = normalizeIngredientAmount(input)
    return result.value === null ? 'Cantidad no válida' : result.value.replace('.', ',')
}

/** Overview sums can be wider than one stored ingredient; this never validates edits. */
export function ingredientAmountDisplayLabel(input: unknown): string {
    if (typeof input !== 'string' || input.length > 1000) return 'Cantidad no válida'
    const match = /^(-?)(\d+)(?:\.(\d{1,16}))?$/.exec(input)
    if (!match) return 'Cantidad no válida'
    const whole = match[2]!.replace(/^0+(?=\d)/, '')
    const fraction = (match[3] || '').replace(/0+$/, '')
    const sign = match[1] === '-' && (whole !== '0' || fraction) ? '-' : ''
    return `${sign}${whole}${fraction ? `,${fraction}` : ''}`
}

export function isZeroIngredientAmount(input: unknown): boolean {
    return normalizeIngredientAmount(input).value === '0'
}

export function prepareIngredientAmounts<T extends {amount: unknown}>(ingredients: readonly T[]): AmountPlan<T> {
    const changes: AmountChange<T>[] = []
    for (const [index, ingredient] of ingredients.entries()) {
        const result = normalizeIngredientAmount(ingredient.amount)
        if (result.value === null) return {changes: null, error: `Revisa la cantidad del ingrediente ${index + 1}: ${result.error}`}
        changes.push({ingredient, amount: result.value})
    }
    return {changes, error: ''}
}

function decimalUnits(value: string): bigint {
    const [whole = '0', fraction = ''] = value.split('.')
    const negative = whole.startsWith('-')
    const unsigned = BigInt(`${negative ? whole.slice(1) : whole}${fraction.padEnd(16, '0')}`)
    return negative ? -unsigned : unsigned
}

function decimalText(units: bigint): string {
    const negative = units < 0n
    const digits = (negative ? -units : units).toString().padStart(17, '0')
    const whole = digits.slice(0, -16)
    const fraction = digits.slice(-16).replace(/0+$/, '')
    return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`
}

/** Build the complete plan before the editor changes amounts or servings. */
export function prepareScaledIngredientAmounts<T extends {amount: unknown}>(
    ingredients: readonly T[], oldServings: number, newServings: number,
): AmountPlan<T> {
    if (![oldServings, newServings].every(value => Number.isSafeInteger(value) && value > 0 && value <= 2147483647)) {
        return {changes: null, error: 'Para escalar, indica raciones enteras entre 1 y 2147483647. La receta conserva sus cantidades.'}
    }
    const plan = prepareIngredientAmounts(ingredients)
    if (plan.changes === null) return plan
    const changes: AmountChange<T>[] = []
    const denominator = BigInt(oldServings)
    for (const [index, change] of plan.changes.entries()) {
        const numerator = decimalUnits(change.amount) * BigInt(newServings)
        if (numerator % denominator !== 0n) {
            return {changes: null, error: `El ingrediente ${index + 1} necesitaría más de 16 decimales. Usa otro número de raciones; la receta conserva sus cantidades.`}
        }
        const amount = decimalText(numerator / denominator)
        const result = normalizeIngredientAmount(amount)
        if (result.value === null) {
            return {changes: null, error: `No se puede escalar el ingrediente ${index + 1}: ${result.error} La receta conserva sus cantidades.`}
        }
        changes.push({ingredient: change.ingredient, amount: result.value})
    }
    return {changes, error: ''}
}

/** Aggregated overview rows are copies; their sum may exceed one ingredient's limit. */
export function sumIngredientAmounts(left: string, right: string): string {
    // A previously aggregated row can have more than sixteen integer digits.
    const valid = /^-?\d+(?:\.\d{1,16})?$/
    if (!valid.test(left) || !valid.test(right)) return 'Cantidad no válida'
    return decimalText(decimalUnits(left) + decimalUnits(right))
}
