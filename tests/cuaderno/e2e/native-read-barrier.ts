import {expect, type Page, type Request} from '@playwright/test'
import {appPath} from './contracts.js'

// A heading can appear before its route's native API bodies finish. Preserve
// every collector error and finish observed reads before a deliberate reload.
export async function withNativeReadBarrier<T>(page: Page, action: () => Promise<T>, requiredPaths: string[] = []): Promise<T> {
  const base = new URL(process.env.BASE_URL || 'http://127.0.0.1:18081')
  const reads = new Set<Promise<void>>()
  const required = new Set(requiredPaths.map(path => appPath(path)))
  for (const path of required) if (!path.startsWith(appPath('/api/'))) throw new Error('Required route reads must be native API paths')
  let requiredStarted!: () => void
  const started = new Promise<void>(resolve => {requiredStarted = resolve})
  if (!required.size) requiredStarted()
  const listen = (request: Request) => {
    const url = new URL(request.url())
    if (request.method() !== 'GET' || url.origin !== base.origin || !url.pathname.startsWith(appPath('/api/'))) return
    const pending = request.response().then(async response => {
      expect(response, 'native GET receives a response before leaving its route').not.toBeNull()
      expect(await response!.finished(), 'native GET body finishes before leaving its route').toBeNull()
    })
    void pending.catch(() => {})
    reads.add(pending)
    required.delete(url.pathname)
    if (!required.size) requiredStarted()
  }
  page.on('request', listen)
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    // Navigation and UI assertions retain their own configured budgets. The
    // unchanged read budget starts only once that action has completed.
    const result = await action()
    return await Promise.race([
      (async () => {
        // Selectors can mount after the heading: an empty observed set alone
        // must not allow a reload before their required requests even start.
        await started
        while (reads.size) {
          const snapshot = [...reads]
          await Promise.all(snapshot)
          for (const item of snapshot) reads.delete(item)
        }
        return result
      })(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('Native route reads exceeded the existing eight-second readiness budget')), 8_000)
      }),
    ])
  } finally {
    if (timer) clearTimeout(timer)
    page.off('request', listen)
  }
}
