export const ALLERGEN_SAFETY_NOTICE = 'Sin declaraciones registradas no significa que el alimento o la receta estén libres de alérgenos.'

export type AllergenState = 'declared' | 'unknown'

export type AllergenDeclaration = {
    id: number
    name: string
    state: AllergenState
}

export type AllergenFood = {
    id: number
    name: string
    declarations: AllergenDeclaration[]
}

export type AllergenAssessment = {
    scope: {type: 'food' | 'recipe'; id: number; name: string}
    assessment: AllergenState
    undeclared_means_absent: false
    unknown_ingredients: boolean
    foods: AllergenFood[]
}

export type UnknownAllergenAssessment = Omit<AllergenAssessment, 'scope'>

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isSafeAllergenId(value: unknown): value is number {
    return Number.isSafeInteger(value) && Number(value) > 0
}

function isName(value: unknown): value is string {
    return typeof value === 'string' && allergenDeclarationName(value) === value
}

export function allergenDeclarationName(value: unknown): string | null {
    if (typeof value !== 'string') return null
    const normalized = value.trim()
    const codePoints = Array.from(normalized)
    if (!codePoints.length || codePoints.length > 128) return null
    for (const character of codePoints) {
        const codePoint = character.codePointAt(0)
        if (codePoint === undefined
            || codePoint <= 0x1f
            || (codePoint >= 0x7f && codePoint <= 0x9f)
            || (codePoint >= 0xd800 && codePoint <= 0xdfff)) return null
    }
    return normalized
}

function isState(value: unknown): value is AllergenState {
    return value === 'declared' || value === 'unknown'
}

export function allergenAssessmentEnvelope(
    value: unknown,
    expectedType?: 'food' | 'recipe',
    expectedId?: number,
): AllergenAssessment | null {
    if (!isRecord(value) || !isRecord(value.scope)) return null
    const scope = value.scope
    if ((scope.type !== 'food' && scope.type !== 'recipe') || !isSafeAllergenId(scope.id) || !isName(scope.name)) return null
    if (expectedType !== undefined && scope.type !== expectedType) return null
    if (expectedId !== undefined && scope.id !== expectedId) return null
    if (!isState(value.assessment) || value.undeclared_means_absent !== false
        || typeof value.unknown_ingredients !== 'boolean' || !Array.isArray(value.foods)) return null

    const foodIds = new Set<number>()
    let hasDeclared = false
    const foods: AllergenFood[] = []
    for (const candidate of value.foods) {
        if (!isRecord(candidate) || !isSafeAllergenId(candidate.id) || !isName(candidate.name)
            || !Array.isArray(candidate.declarations) || foodIds.has(candidate.id)) return null
        foodIds.add(candidate.id)
        const declarationIds = new Set<number>()
        const declarations: AllergenDeclaration[] = []
        for (const declaration of candidate.declarations) {
            if (!isRecord(declaration) || !isSafeAllergenId(declaration.id) || !isName(declaration.name)
                || !isState(declaration.state) || declarationIds.has(declaration.id)) return null
            declarationIds.add(declaration.id)
            if (declaration.state === 'declared') hasDeclared = true
            declarations.push({id: declaration.id, name: declaration.name, state: declaration.state})
        }
        foods.push({id: candidate.id, name: candidate.name, declarations})
    }
    if (scope.type === 'food' && (foods.length !== 1 || foods[0].id !== scope.id)) return null
    if ((value.assessment === 'declared') !== hasDeclared) return null
    return {
        scope: {type: scope.type, id: scope.id, name: scope.name},
        assessment: value.assessment,
        undeclared_means_absent: false,
        unknown_ingredients: value.unknown_ingredients,
        foods,
    }
}

export function unknownAllergenAssessment(): UnknownAllergenAssessment {
    return {
        assessment: 'unknown',
        undeclared_means_absent: false,
        unknown_ingredients: true,
        foods: [],
    }
}

export function allergenAssessmentLabel(state: unknown): string {
    return state === 'declared' ? 'Alérgenos declarados' : 'Estado de alérgenos desconocido'
}

export function allergenDeclarationResponse(value: unknown, expectedState: AllergenState): boolean {
    return isRecord(value)
        && isSafeAllergenId(value.id)
        && value.state === expectedState
        && value.undeclared_means_absent === false
}
