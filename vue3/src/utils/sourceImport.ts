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
                unit: ingredient.unit?.name.trim() ? ingredient.unit : null,
                order: ingredient.order ?? 0,
            })),
        })),
    }
}
