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
    return fetch(url, {...options, credentials: "same-origin", headers})
}

export async function readJson(response: Response) {
    const data = await response.json().catch(() => ({}))
    return {ok: response.ok, status: response.status, data}
}
