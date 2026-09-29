export const RECIPE_SHARE_TOKEN_KEY = 'recipeShareToken'

/** Attach recipe capability only to same-origin protected media. */
export function sharedMediaUrl(source: string | undefined, token: string | undefined, origin: string): string | undefined {
    if (!source || !token) return source

    let mediaUrl: URL
    try {
        mediaUrl = new URL(source, origin)
    } catch {
        return source
    }

    if (mediaUrl.origin !== origin || !mediaUrl.pathname.startsWith('/media/')) return source

    mediaUrl.searchParams.set('share', token)
    return source.startsWith('/') ? `${mediaUrl.pathname}${mediaUrl.search}${mediaUrl.hash}` : mediaUrl.toString()
}
