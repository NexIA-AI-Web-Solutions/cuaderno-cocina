import {getCookie} from "@/utils/cookie";

interface DjangoConfig {
    csrfCookieName: string;
    languageCookieName: string;
    languageCookiePath: string;
    languageCookieSecure: boolean;
    mediaUrl: string;
}

/** Django's <base> is authoritative, including on deep frontend routes. */
export function djangoBaseUrl(): URL {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
    const base = new URL(typeof document !== 'undefined' ? document.baseURI : '/', origin);
    // An external <base> must never redirect application credentials elsewhere.
    if (base.origin !== origin) throw new Error('Django application base must use the current origin');
    base.pathname = base.pathname.replace(/\/+$/, '') + '/';
    base.search = '';
    base.hash = '';
    return base;
}

export function getDjangoConfig(): DjangoConfig {
    const base = djangoBaseUrl();
    let config: Partial<DjangoConfig> = {};
    const source = typeof document !== 'undefined' ? document.getElementById('django_config')?.textContent : null;
    if (source) config = JSON.parse(source);
    return {
        csrfCookieName: config.csrfCookieName ?? 'csrftoken',
        languageCookieName: config.languageCookieName ?? 'django_language',
        languageCookiePath: config.languageCookiePath ?? base.pathname,
        languageCookieSecure: config.languageCookieSecure ?? base.protocol === 'https:',
        mediaUrl: config.mediaUrl ?? `${base.pathname}media/`,
    };
}

/** Resolve application paths while preserving explicitly absolute URLs. */
export function resolveDjangoUrl(source: string, appendSlash = false): string {
    if (/^[a-z][a-z\d+.-]*:/i.test(source) || source.startsWith('//')) return source;
    const base = djangoBaseUrl();
    const prefix = base.pathname.replace(/\/+$/, '');
    const alreadyPrefixed = prefix && (source === prefix || source.startsWith(`${prefix}/`) || source.startsWith(`${prefix}?`) || source.startsWith(`${prefix}#`));
    const url = new URL(alreadyPrefixed ? source : source.replace(/^\/+/, ''), base);
    if (appendSlash && !url.pathname.endsWith('/')) url.pathname += '/';
    return `${url.pathname}${url.search}${url.hash}`;
}

/** Only the same origin and the application path may receive cookie tokens. */
export function isDjangoUrl(source: string): boolean {
    const base = djangoBaseUrl();
    try {
        const url = new URL(source, base);
        const prefix = base.pathname.replace(/\/+$/, '');
        return url.origin === base.origin && (!prefix || url.pathname === prefix || url.pathname.startsWith(`${prefix}/`));
    } catch {
        return false;
    }
}

export function csrfHeadersForUrl(url: string): Record<string, string> {
    if (!isDjangoUrl(url)) return {};
    const token = getCookie(getDjangoConfig().csrfCookieName);
    return token ? {'X-CSRFToken': token} : {};
}

export function setDjangoLanguage(language: string, expires: Date): void {
    const config = getDjangoConfig();
    document.cookie = `${config.languageCookieName}=${encodeURIComponent(language)}; expires=${expires.toUTCString()}; path=${config.languageCookiePath}; SameSite=Lax${config.languageCookieSecure ? '; Secure' : ''}`;
}
