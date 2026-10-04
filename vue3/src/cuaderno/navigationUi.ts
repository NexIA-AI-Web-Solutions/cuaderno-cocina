export type CuadernoEdition = 'esencial' | 'profesional' | 'integral'

export type CuadernoNavigationCapabilities = {
    edition: CuadernoEdition | null
    prices: boolean
    production: boolean
    warehouse: boolean
}

export function cuadernoNavigationCapabilities(value: unknown): CuadernoNavigationCapabilities {
    const edition = typeof value === 'object' && value !== null && 'edition' in value
        && (value.edition === 'esencial' || value.edition === 'profesional' || value.edition === 'integral')
        ? value.edition
        : null
    return {
        edition,
        prices: edition !== null,
        production: edition === 'profesional' || edition === 'integral',
        warehouse: edition === 'integral',
    }
}
