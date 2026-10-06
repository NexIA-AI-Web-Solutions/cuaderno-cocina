import test from 'node:test'
import assert from 'node:assert/strict'
import {EventEmitter} from 'node:events'
import {readFileSync} from 'node:fs'

let transform
try {
  const {default: ts} = await import('typescript')
  transform = source => ts.transpileModule(source, {compilerOptions: {
    module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
  }}).outputText
} catch {
  const {stripTypeScriptTypes} = await import('node:module')
  transform = source => stripTypeScriptTypes(source, {mode: 'transform'})
}
const helperCode = transform(readFileSync(new URL('./start-page-ready.ts', import.meta.url), 'utf8'))
const helperUrl = `data:text/javascript;base64,${Buffer.from(helperCode).toString('base64')}`
const {enterStartPage} = await import(helperUrl)
const home = 'https://127.0.0.1:18443/cuaderno-cocina/'
const turn = () => new Promise(resolve => setImmediate(resolve))

function deferred() {
  let resolve, reject
  const promise = new Promise((accept, decline) => { resolve = accept; reject = decline })
  return {promise, resolve, reject}
}

class Page extends EventEmitter {
  current = 'about:blank'
  navigations = []
  onGoto = async () => {}
  marker = deferred()
  spinners = deferred()
  url() { return this.current }
  async goto(url) {
    this.navigations.push(url)
    this.current = url
    await this.onGoto()
  }
  locator(selector) {
    return {page: this, selector, first() { return this }, locator(nested) { return this.page.locator(`${this.selector} ${nested}`) }}
  }
}

function response(path = 'api/recipe/?page_size=1', method = 'GET', body = deferred()) {
  let calls = 0
  return {body, get finishedCalls() { return calls },
    url: () => new URL(path, home).href,
    request: () => ({method: () => method}),
    finished: () => { calls++; return body.promise },
  }
}

function observe(promise) {
  let settled = false
  const done = promise.then(value => { settled = true; return value }, error => { settled = true; throw error })
  return {done, settled: () => settled}
}

test('response headers do not permit navigation before the body finishes', async () => {
  const page = new Page()
  const count = response()
  page.onGoto = async () => { page.emit('response', count) }
  const entry = observe(enterStartPage(page, home, async () => {}))
  await turn()
  const premature = entry.settled()
  count.body.resolve(null)
  await entry.done
  assert.equal(premature, false)
  assert.equal(count.finishedCalls, 1)
  assert.equal(page.listenerCount('response'), 0)
})

test('count completion still waits for an observed optional meal-plan body', async () => {
  const page = new Page()
  const count = response()
  const meal = response('api/meal-plan/?from_date=2026-10-06&page=1&page_size=100&to_date=2026-10-13')
  page.onGoto = async () => { page.emit('response', count); page.emit('response', meal) }
  const entry = observe(enterStartPage(page, home, async () => {}))
  count.body.resolve(null)
  await turn()
  const premature = entry.settled()
  meal.body.resolve(null)
  await entry.done
  assert.equal(premature, false)
  assert.equal(meal.finishedCalls, 1)
})

test('a completed cached response emitted before goto resolves is retained', async () => {
  const page = new Page()
  const count = response()
  count.body.resolve(null)
  page.onGoto = async () => { page.emit('response', count); await turn() }
  await enterStartPage(page, home, async () => {})
  assert.equal(count.finishedCalls, 1)
})

test('absence of an optional meal-plan request never creates a required response', async () => {
  const page = new Page()
  const count = response()
  count.body.resolve(null)
  page.onGoto = async () => { page.emit('response', count) }
  await enterStartPage(page, home, async () => {})
  assert.equal(count.finishedCalls, 1)
})

test('only native recipe and meal-plan GETs on the application origin and prefix are observed', async () => {
  const page = new Page()
  const ignored = [response('/api/recipe/?page_size=1'), response('https://foreign.test/cuaderno-cocina/api/recipe/?page_size=1'),
    response('api/recipe/?page_size=1', 'POST'), response('api/cuaderno/edition/'), response('api/recipe/42/')]
  page.onGoto = async () => { for (const item of ignored) page.emit('response', item) }
  await enterStartPage(page, home, async () => {})
  assert.deepEqual(ignored.map(item => item.finishedCalls), [0, 0, 0, 0, 0])
})

test('the same barrier captures native root deployment responses', async () => {
  const page = new Page()
  const rootHome = 'http://127.0.0.1:18081/'
  const count = response(rootHome + 'api/recipe/?page_size=1')
  count.body.resolve(null)
  page.onGoto = async () => { page.emit('response', count) }
  await enterStartPage(page, rootHome, async () => {})
  assert.equal(count.finishedCalls, 1)
  assert.deepEqual(page.navigations, [rootHome])
})

test('new matching responses arriving while earlier bodies finish are drained too', async () => {
  const page = new Page()
  const count = response()
  const scroller = response('api/recipe/?page_size=16&random=true')
  page.onGoto = async () => { page.emit('response', count) }
  const entry = observe(enterStartPage(page, home, async () => {}))
  await turn()
  page.emit('response', scroller)
  count.body.resolve(null)
  await turn()
  const premature = entry.settled()
  scroller.body.resolve(null)
  await entry.done
  assert.equal(premature, false)
  assert.equal(scroller.finishedCalls, 1)
})

test('native finished errors are propagated and listeners are removed', async () => {
  const page = new Page()
  const count = response()
  const error = new Error('Load request cancelled')
  count.body.resolve(error)
  page.onGoto = async () => { page.emit('response', count) }
  await assert.rejects(enterStartPage(page, home, async () => {}), failure => failure === error)
  assert.equal(page.listenerCount('response'), 0)
})

test('a rejected finished promise is consumed immediately and then fails entry', async () => {
  const page = new Page()
  const count = response()
  const ready = deferred()
  const error = new Error('connection closed')
  page.onGoto = async () => { page.emit('response', count) }
  const entry = enterStartPage(page, home, () => ready.promise)
  const rejected = assert.rejects(entry, failure => failure === error)
  count.body.reject(error)
  await turn()
  ready.resolve()
  await rejected
  assert.equal(page.listenerCount('response'), 0)
})

test('already-current home is reused and DOM readiness covers responses emitted before entry', async () => {
  const page = new Page()
  page.current = home
  const count = response()
  count.body.resolve(null)
  page.emit('response', count)
  let checked = false
  await enterStartPage(page, home, async () => { checked = true })
  assert.equal(checked, true)
  assert.deepEqual(page.navigations, [])
  assert.equal(page.listenerCount('response'), 0)
})

test('navigation and readiness failures still remove the entry listener', async () => {
  for (const phase of ['navigation', 'readiness']) {
    const page = new Page()
    const error = new Error(phase)
    if (phase === 'navigation') page.onGoto = async () => { throw error }
    await assert.rejects(enterStartPage(page, home, async () => { if (phase === 'readiness') throw error }), failure => failure === error)
    assert.equal(page.listenerCount('response'), 0)
  }
})

test('a body that never finishes fails within the same readiness deadline', async () => {
  const page = new Page()
  const count = response()
  page.onGoto = async () => { page.emit('response', count) }
  await assert.rejects(enterStartPage(page, home, async () => {}, 25), /StartPage.*25.*ms/)
  assert.equal(page.listenerCount('response'), 0)
})

test('readiness and body completion share one decreasing budget', async () => {
  const page = new Page()
  const count = response()
  page.onGoto = async () => { page.emit('response', count) }
  let first, last
  const entry = enterStartPage(page, home, async remaining => {
    first = remaining()
    await new Promise(resolve => setTimeout(resolve, 10))
    last = remaining()
    count.body.resolve(null)
  }, 100)
  await entry
  assert.ok(first <= 100 && first > 0)
  assert.ok(last < first)
})

// Execute the real fixture entry function with fake Playwright assertions. This
// covers its DOM readiness contract without installing or opening a browser.
const fixtures = readFileSync(new URL('./fixtures.ts', import.meta.url), 'utf8')
const entrySource = fixtures.slice(fixtures.indexOf('export async function enterApp('), fixtures.indexOf('export async function assertNoHorizontalOverflow('))
const fixtureCode = transform(`import {enterStartPage} from ${JSON.stringify(helperUrl)};
const appPath = path => '/cuaderno-cocina' + path;
const process = {env: {BASE_URL: ${JSON.stringify(home)}}};
const expect = globalThis.__cuadernoStartPageReadyExpect;
${entrySource}`)

globalThis.__cuadernoStartPageReadyExpect = subject => ({
  not: {async toHaveURL(pattern) { assert.equal(pattern.test(subject.url()), false) }},
  async toBeVisible({timeout} = {}) {
    if (subject.selector === '#app') return
    assert.ok(timeout > 0 && timeout <= 8_000)
    assert.match(subject.selector, /advanced-search/)
    assert.match(subject.selector, /fa-eye-slash/)
    await subject.page.marker.promise
  },
  async toHaveCount(count, {timeout} = {}) {
    assert.equal(count, 0)
    assert.ok(timeout > 0 && timeout <= 8_000)
    assert.match(subject.selector, /v-skeleton-loader/)
    assert.match(subject.selector, /v-progress-linear/)
    await subject.page.spinners.promise
  },
})
const {enterApp} = await import(`data:text/javascript;base64,${Buffer.from(fixtureCode).toString('base64')}`)
delete globalThis.__cuadernoStartPageReadyExpect

test('real enterApp waits for delayed lazy StartPage after the visible shell', async () => {
  const page = new Page()
  const entry = observe(enterApp(page))
  await turn()
  const beforeMount = entry.settled()
  const count = response()
  count.body.resolve(null)
  page.emit('response', count)
  page.marker.resolve('view recipes')
  page.spinners.resolve()
  await entry.done
  assert.equal(beforeMount, false)
  assert.equal(count.finishedCalls, 1)
})

test('real enterApp waits for count-triggered child skeletons and optional meal-plan progress', async () => {
  const page = new Page()
  const count = response()
  count.body.resolve(null)
  page.onGoto = async () => { page.emit('response', count) }
  page.marker.resolve('view recipes')
  const entry = observe(enterApp(page))
  await turn()
  const beforeChildren = entry.settled()
  page.spinners.resolve()
  await entry.done
  assert.equal(beforeChildren, false)
})

test('real enterApp accepts the completed empty card when no recipe exists', async () => {
  const page = new Page()
  const count = response()
  count.body.resolve(null)
  page.onGoto = async () => { page.emit('response', count) }
  page.marker.resolve('empty card')
  page.spinners.resolve()
  await enterApp(page)
  assert.equal(count.finishedCalls, 1)
})

test('real enterApp reuses fresh-login home while old response headers are already emitted', async () => {
  const page = new Page()
  page.current = home
  const count = response()
  page.emit('response', count)
  const entry = observe(enterApp(page))
  await turn()
  const beforeBody = entry.settled()
  count.body.resolve(null)
  page.marker.resolve('view recipes')
  page.spinners.resolve()
  await entry.done
  assert.equal(beforeBody, false)
  assert.equal(count.finishedCalls, 0)
  assert.deepEqual(page.navigations, [])
})
