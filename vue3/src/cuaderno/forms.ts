export function decimalInput(value: string, zero = false): string | null {
    const normalized = value.trim().replace(',', '.')
    if (!/^\d+(\.\d+)?$/.test(normalized)) return null
    if (!zero && !/[1-9]/.test(normalized)) return null
    return normalized
}
export function apiError(status: number, data: unknown): string {
    if (status === 403) return 'No tienes permiso para esta operación o no está incluida en la edición del espacio.'
    if (status === 409) return 'La operación entra en conflicto con un cambio anterior. Actualiza antes de volver a intentarlo.'
    function messages(value: unknown): string[] {
        if (typeof value === 'string') return [value]
        if (Array.isArray(value)) return value.flatMap(messages)
        if (value && typeof value === 'object') return Object.values(value).flatMap(messages)
        return []
    }
    return messages(data).join(' ') || 'No se ha podido completar la operación. Conservamos los datos para que puedas reintentar.'
}
export function shoppingCheckBody(checked: boolean) { return {checked} }

export function productionUsage(component: string, value: string) {
    const quantity = decimalInput(value)
    if (!component.trim() || !quantity) return null
    return {component: component.trim(), quantity}
}

export function serviceCovers(base: string, extra: string, cancelled: string) {
    const values = [base, extra, cancelled].map(value => value.trim())
    if (values.some(value => !/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)))) return null
    const [baseCovers = '', extraCovers = '', cancelledCovers = ''] = values
    if (BigInt(cancelledCovers) > BigInt(baseCovers) + BigInt(extraCovers)) return null
    return {base_covers: baseCovers, extra: extraCovers, cancelled: cancelledCovers}
}

export function serviceBody(title: string, value: string, serviceDate: string, recipe?: number) {
    const covers = value.trim()
    if (!title.trim() || title.trim().length > 128 || !/^\d+$/.test(covers) || BigInt(covers) < 1n || BigInt(covers) > 9999n) return null
    if (!/^\d{4}-\d{2}-\d{2}$/.test(serviceDate)) return null
    const day = new Date(`${serviceDate}T12:00:00Z`)
    if (!Number.isFinite(day.getTime()) || day.toISOString().slice(0, 10) !== serviceDate) return null
    if (recipe !== undefined && (!Number.isSafeInteger(recipe) || recipe < 1)) return null
    return {title: title.trim(), covers, service_date: serviceDate, ...(recipe === undefined ? {} : {recipe})}
}

export function confirmedCostLabel(cost: {status: string; display: string | null}): string {
    return cost.status === 'complete' && cost.display !== null ? `${cost.display} €` : 'incompleto'
}

export function yieldBody(value: string, unit: number | undefined) {
    const quantity = decimalInput(value)
    if (!quantity || !unit || !Number.isSafeInteger(unit) || unit < 0) return null
    return {quantity, unit}
}

export function productionWarning(warning: unknown): string {
    const item = typeof warning === 'object' && warning !== null ? warning as Record<string, unknown> : {code: warning}
    if (String(item.code).startsWith('yield_missing')) {
        const recipe = item.recipe_id ?? item.recipe
        return `Ficha incompleta: falta declarar el rendimiento de salida${recipe ? ` de la receta ${recipe}` : ' de una subreceta'}.`
    }
    if (item.code === 'ingredient_incomplete') return 'Ficha incompleta: un ingrediente no tiene alimento o cantidad válida. Revisa la receta.'
    return String(item.message ?? item.code ?? 'No se han podido calcular todas las necesidades.')
}
