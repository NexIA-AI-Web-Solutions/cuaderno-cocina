import {getCookie} from "@/utils/cookie"

export async function cuadernoFetch(url: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers)
    if (options.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json")
    }
    const token = getCookie("csrftoken")
    if (token) {
        headers.set("X-CSRFToken", token)
    }
    try {
        return await fetch(url, {...options, credentials: "same-origin", headers})
    } catch {
        return new Response(JSON.stringify({detail: 'No hay conexión con el servidor. Los datos siguen en el formulario; comprueba la conexión y reintenta.'}), {status: 503, headers: {'Content-Type': 'application/json'}})
    }
}

export async function readJson(response: Response) {
    const data = await response.json().catch(() => ({}))
    return {ok: response.ok, status: response.status, data}
}
