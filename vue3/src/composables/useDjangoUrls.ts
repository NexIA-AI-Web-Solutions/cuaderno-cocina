import {djangoBaseUrl, resolveDjangoUrl} from "@/utils/djangoConfig";

/**
 * helper function to use django urls while respecting sub path setups
 * only needed as long as not all pages are integrated into the Vue.js frontend (which might be forever...)
 */
export function useDjangoUrls() {
    const basePath = djangoBaseUrl().pathname.replace(/\/+$/, '')

    /**
     * given a path return the absolute path to that url respecting possible sub path setups
     * @param path
     * @param appendSlash automatically append a slash to the end of the url (default true)
     */
    function getDjangoUrl(path: string, appendSlash = true){
        return resolveDjangoUrl(path, appendSlash)
    }

    /**
     * given a path return the full URL (with origin) for use in external contexts
     * (bookmarklets, clipboard copy, iCal links, etc.)
     * @param path
     * @param appendSlash automatically append a slash to the end of the url (default true)
     */
    function getFullUrl(path: string, appendSlash = true) {
        return new URL(getDjangoUrl(path, appendSlash), djangoBaseUrl()).toString()
    }

    return {basePath, getDjangoUrl, getFullUrl}
}
