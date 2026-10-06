import type {Page, Response} from '@playwright/test'

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
  const nativePaths = new Set(['api/recipe/', 'api/meal-plan/'].map(path => new URL(path, home).pathname))
  const bodies: Promise<void>[] = []
  let rejectFailure!: (error: unknown) => void
  const failedBody = new Promise<never>((_resolve, reject) => { rejectFailure = reject })
  // A fast response can fail while goto is still pending. Consume it immediately
  // and retain the same failure for the readiness barrier below.
  void failedBody.catch(() => {})
  const capture = (response: Response) => {
    const url = new URL(response.url())
    if (url.origin !== home.origin || !nativePaths.has(url.pathname) || response.request().method() !== 'GET') return
    try {
      bodies.push(response.finished().then(error => {
        if (error) rejectFailure(error)
      }, rejectFailure))
    } catch (error) {
      rejectFailure(error)
    }
  }
  let timer: ReturnType<typeof setTimeout> | undefined
  page.on('response', capture)
  try {
    const current = new URL(page.url())
    if (current.origin !== home.origin || current.pathname !== home.pathname || current.search !== home.search) {
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
    page.off('response', capture)
  }
}
