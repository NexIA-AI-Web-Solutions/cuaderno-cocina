import type {Page, Request, Response} from '@playwright/test'

/** Finish native StartPage loads before a test deliberately leaves the page. */
export async function enterStartPage(
  page: Page,
  homeUrl: string,
  waitForReady: (remaining: () => number) => Promise<void>,
  readyTimeoutMs = 8_000,
): Promise<void> {
  if (!Number.isInteger(readyTimeoutMs) || readyTimeoutMs < 1 || readyTimeoutMs > 8_000) {
    throw new Error('El presupuesto de StartPage debe conservar el límite de 8000 ms.')
  }
  const home = new URL(homeUrl)
  const nativePaths = new Set([
    'api/recipe/', 'api/meal-plan/', 'api/user-preference/', 'api/recipe/flat/',
    'api/server-settings/current/', 'api/space/current/', 'api/space/',
    'api/user-space/all_personal/', 'api/unit/',
  ].map(path => new URL(path, home).pathname))
  const current = new URL(page.url())
  const navigate = current.origin !== home.origin || current.pathname !== home.pathname || current.search !== home.search
  // Authenticated fresh entry mounts GlobalSearchDialog only after preferences
  // load. Its flat GET can start after the dashboard's own count is already ready.
  // Reusing an existing home must not require these requests to start again.
  const authenticatedPaths = new Set(['api/user-preference/', 'api/recipe/flat/'].map(path => new URL(path, home).pathname))
  const required = new Set(navigate ? authenticatedPaths : [])
  let resolveStarted!: () => void
  const started = new Promise<void>(resolve => { resolveStarted = resolve })
  if (!required.size) resolveStarted()
  const observed = new WeakSet<Request>()
  const bodies: Promise<void>[] = []
  let rejectFailure!: (error: unknown) => void
  const failedBody = new Promise<never>((_resolve, reject) => { rejectFailure = reject })
  // A fast response can fail while goto is still pending. Consume it immediately
  // and retain the same failure for the readiness barrier below.
  void failedBody.catch(() => {})
  const matches = (request: Request) => {
    const url = new URL(request.url())
    return request.method() === 'GET' && url.origin === home.origin && nativePaths.has(url.pathname)
  }
  const finish = async (response: Response) => {
    const pathname = new URL(response.url()).pathname
    if (authenticatedPaths.has(pathname) && response.status() !== 200) {
      throw new Error('StartPage no confirmó sus lecturas autenticadas.')
    }
    const error = await response.finished()
    if (error) throw error
  }
  const remember = (request: Request) => {
    required.delete(new URL(request.url()).pathname)
    if (!required.size) resolveStarted()
    observed.add(request)
  }
  const captureRequest = (request: Request) => {
    if (!matches(request) || observed.has(request)) return
    remember(request)
    const body = request.response().then(response => {
      if (!response) throw new Error('StartPage perdió una respuesta nativa antes de completar su carga.')
      return finish(response)
    })
    void body.catch(rejectFailure)
    bodies.push(body)
  }
  const capture = (response: Response) => {
    const request = response.request()
    if (!matches(request) || observed.has(request)) return
    remember(request)
    const body = finish(response)
    void body.catch(rejectFailure)
    bodies.push(body)
  }
  let timer: ReturnType<typeof setTimeout> | undefined
  page.on('request', captureRequest)
  page.on('response', capture)
  try {
    if (navigate) {
      await page.goto(home.href)
    }
    // Keep the existing navigation deadline. DOM assertions and body completion
    // then share the existing 8-second expectation budget instead of stacking it.
    const deadline = performance.now() + readyTimeoutMs
    const remaining = () => Math.max(1, Math.ceil(deadline - performance.now()))
    const timedOut = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => reject(new Error(`StartPage no completó sus cargas en ${readyTimeoutMs} ms.`)), readyTimeoutMs)
    })
    await Promise.race([
      (async () => {
        // Existing home after login can have emitted responses before capture.
        // Its loaded DOM and absent spinners still prove those bodies were read.
        await waitForReady(remaining)
        await started
        let drained = 0
        while (drained < bodies.length) {
          const batch = bodies.slice(drained)
          drained = bodies.length
          await Promise.all(batch)
        }
      })(),
      failedBody,
      timedOut,
    ])
  } finally {
    if (timer !== undefined) clearTimeout(timer)
    page.off('request', captureRequest)
    page.off('response', capture)
  }
}
