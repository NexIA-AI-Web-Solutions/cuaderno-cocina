import {csrfHeadersForUrl, resolveDjangoUrl} from "@/utils/djangoConfig"

export async function cuadernoFetch(url: string, options: RequestInit = {}) {
    url = resolveDjangoUrl(url)
    const headers = new Headers(options.headers)
    if (options.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json")
    }
    headers.delete('X-CSRFToken')
    for (const [name, value] of Object.entries(csrfHeadersForUrl(url))) {
        headers.set(name, value)
    }
    try {
        return await fetch(url, {...options, credentials: "same-origin", redirect: "error", headers})
    } catch {
        return new Response(JSON.stringify({detail: 'No hay conexión con el servidor. Los datos siguen en el formulario; comprueba la conexión y reintenta.'}), {status: 503, headers: {'Content-Type': 'application/json'}})
    }
}

export async function readJson(response: Response) {
    const data = await response.json().catch(() => ({}))
    return {ok: response.ok, status: response.status, data}
}
