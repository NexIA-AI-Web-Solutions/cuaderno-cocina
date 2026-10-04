export type ShoppingListSummary = {id: number; name: string}
export type ShoppingEntry = {
    id: number
    amount: string | number
    checked: boolean
    updated_at: string
    food: {id: number; name: string}
    unit: null | {id?: number; name: string}
    shopping_lists: Array<number | {id: number}>
    list_recipe_data?: unknown
}

function record(value: unknown): Record<string, unknown> | null {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
        ? value as Record<string, unknown> : null
}
function id(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}
function timestamp(value: unknown): value is string {
    return typeof value === 'string' && value.length > 0 && Number.isFinite(Date.parse(value))
}
function pageItems(value: unknown): unknown[] | null {
    if (Array.isArray(value)) return value
    const envelope = record(value)
    return envelope && Array.isArray(envelope.results) ? envelope.results : null
}

export function shoppingLists(value: unknown): ShoppingListSummary[] | null {
    const items = pageItems(value)
    if (items === null) return null
    const parsed: ShoppingListSummary[] = []
    for (const item of items) {
        const row = record(item)
        if (!row || !id(row.id) || typeof row.name !== 'string' || !row.name.trim()) return null
        parsed.push({id: row.id, name: row.name})
    }
    return new Set(parsed.map(item => item.id)).size === parsed.length ? parsed : null
}

export function shoppingEntries(value: unknown): ShoppingEntry[] | null {
    const items = pageItems(value)
    if (items === null) return null
    const parsed: ShoppingEntry[] = []
    for (const item of items) {
        const row = record(item)
        const food = record(row?.food)
        const unit = row?.unit === null ? null : record(row?.unit)
        if (!row || !id(row.id) || typeof row.checked !== 'boolean' || !timestamp(row.updated_at)
            || (typeof row.amount !== 'string' && (typeof row.amount !== 'number' || !Number.isFinite(row.amount)))
            || !food || !id(food.id) || typeof food.name !== 'string' || !food.name.trim()
            || (unit !== null && (typeof unit.name !== 'string' || (unit.id !== undefined && !id(unit.id))))
            || !Array.isArray(row.shopping_lists)) return null
        const relations: ShoppingEntry['shopping_lists'] = []
        for (const relation of row.shopping_lists) {
            if (id(relation)) relations.push(relation)
            else {
                const relationRow = record(relation)
                if (!relationRow || !id(relationRow.id)) return null
                relations.push({id: relationRow.id})
            }
        }
        parsed.push({
            id: row.id, amount: row.amount, checked: row.checked, updated_at: row.updated_at,
            food: {id: food.id, name: food.name},
            unit: unit === null ? null : {id: id(unit.id) ? unit.id : undefined, name: unit.name as string},
            shopping_lists: relations, list_recipe_data: row.list_recipe_data,
        })
    }
    return new Set(parsed.map(item => item.id)).size === parsed.length ? parsed : null
}

export function shoppingEntryResponse(value: unknown, entryId: number, checked: boolean): ShoppingEntry | null {
    const parsed = shoppingEntries([value])
    return parsed?.length === 1 && parsed[0]?.id === entryId && parsed[0].checked === checked ? parsed[0] : null
}

export function ifMatchRevision(updatedAt: string): string | null {
    return timestamp(updatedAt) && !/["\r\n]/.test(updatedAt) ? `"${updatedAt}"` : null
}

export function shoppingSourceLabel(value: unknown): string {
    const data = record(value)
    const recipe = record(data?.recipe)
    if (recipe && typeof recipe.name === 'string' && recipe.name.trim()) return `Receta: ${recipe.name}`
    return value == null ? 'Añadido manualmente' : 'Origen de receta'
}
