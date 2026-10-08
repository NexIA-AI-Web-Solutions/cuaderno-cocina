import type {RecipeRequest, SourceImportRecipe} from '@/openapi'

/** Convert a scraper preview to the native nested-write contract. */
export function sourceImportRequest(source: SourceImportRecipe): RecipeRequest {
    return {
        ...source,
        keywords: (source.keywords ?? []).map(keyword => ({
            name: keyword.name,
            ...(keyword.id == null ? {} : {id: keyword.id}),
        })),
        steps: source.steps.map(step => ({
            ...step,
            ingredients: step.ingredients.map(ingredient => ({
                ...ingredient,
                amount: String(ingredient.amount),
                unit: ingredient.unit?.name.trim() ? ingredient.unit : null,
                order: ingredient.order ?? 0,
            })),
        })),
    }
}

export class SourceImportPrecisionError extends Error {
    constructor() {
        super('No se puede abrir esta receta en el importador numérico sin perder precisión. Conserva la receta original y edita sus cantidades desde el editor de recetas.')
        this.name = 'SourceImportPrecisionError'
    }
}

/** The legacy scraper preview has numeric amounts; its JSON roundtrip must preserve every digit. */
export function sourcePreviewIngredientAmount(amount: unknown): number {
    if (typeof amount !== 'string' || amount.length > 1000) throw new SourceImportPrecisionError()
    const source = /^(-?)(\d+)(?:\.(\d{1,16}))?$/.exec(amount)
    if (!source) throw new SourceImportPrecisionError()
    const whole = source[2]!.replace(/^0+(?=\d)/, '')
    const fraction = (source[3] || '').replace(/0+$/, '')
    if (whole.length > 16) throw new SourceImportPrecisionError()
    const sign = source[1] === '-' && (whole !== '0' || fraction) ? '-' : ''
    const original = `${sign}${whole}${fraction ? `.${fraction}` : ''}`
    const value = Number(amount)
    if (!Number.isFinite(value)) throw new SourceImportPrecisionError()
    const wire = /^(-?)(\d+)(?:\.(\d+))?(?:e([+-]?\d+))?$/.exec(String(value))
    if (!wire) throw new SourceImportPrecisionError()
    const digits = wire[2]! + (wire[3] || '')
    const point = wire[2]!.length + Number(wire[4] || 0)
    const expanded = point <= 0 ? `0.${'0'.repeat(-point)}${digits}`
        : point >= digits.length ? digits + '0'.repeat(point - digits.length)
            : `${digits.slice(0, point)}.${digits.slice(point)}`
    const [wireWhole = '0', wireFraction = ''] = expanded.split('.')
    const trimmedFraction = wireFraction.replace(/0+$/, '')
    const roundtrip = `${wire[1]}${wireWhole.replace(/^0+(?=\d)/, '')}${trimmedFraction ? `.${trimmedFraction}` : ''}`
    if (roundtrip !== original) throw new SourceImportPrecisionError()
    return value === 0 ? 0 : value
}
