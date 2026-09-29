export function readExchangeFile(text: string): Record<string, any> {
    // File boundary only; all recipe/catalog/domain validation remains on the server.
    if (new TextEncoder().encode(text).length > 2_000_000) throw new Error('El archivo supera 2 MB.')
    let document: any
    try { document = JSON.parse(text) } catch { throw new Error('El archivo no es JSON válido.') }
    if (!document || Array.isArray(document) || !Array.isArray(document.recipes)
        || !['cuaderno-recipes-v1', 'cuaderno-recipes-v2'].includes(document.format)) {
        throw new Error('Selecciona una exportación JSON de Cuaderno. Para otros formatos utiliza el importador nativo.')
    }
    if (document.recipes.length > 1000) throw new Error('El archivo supera 1000 recetas.')
    return document
}

export function exchangeBody(document: Record<string, any>, mapping: Record<string, any>, previewHash?: string) {
    const body = structuredClone(document)
    delete body.preview_sha256
    // UI choices must be explicit; file provenance is not permission to auto-reuse native IDs.
    delete body.source_space
    body.mapping = structuredClone(mapping)
    if (previewHash) body.preview_sha256 = previewHash
    return body
}
