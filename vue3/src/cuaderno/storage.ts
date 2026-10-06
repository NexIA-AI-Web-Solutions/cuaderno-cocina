/** Never read, migrate or remove another application's keys on a shared origin. */
export function cuadernoStorageKey(key: string, baseURI = typeof document === 'undefined' ? 'http://localhost/' : document.baseURI) {
    const scope = new URL(baseURI).pathname.replace(/\/+$/, '') + '/'
    return `cuaderno:${encodeURIComponent(scope)}:${key}`
}
