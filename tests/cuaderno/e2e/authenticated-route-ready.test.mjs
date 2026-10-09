import test from 'node:test'
import assert from 'node:assert/strict'
import {EventEmitter} from 'node:events'
import {readFileSync} from 'node:fs'
import {createRequire, stripTypeScriptTypes} from 'node:module'
import {pathToFileURL} from 'node:url'

const require = createRequire(import.meta.url)
let source = stripTypeScriptTypes(readFileSync(new URL('./native-read-barrier.ts', import.meta.url), 'utf8'))
source = source.replace(/import \{expect,[^}]*\} from '@playwright\/test'/,
  `import playwright from ${JSON.stringify(pathToFileURL(require.resolve('@playwright/test')).href)}; const {expect} = playwright`)
source = source.replace("import {appPath} from './contracts.js'", "const appPath = suffix => '/cuaderno-cocina' + suffix")
const {withAuthenticatedReadBarrier, withNativeReadBarrier} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
const origin = 'https://127.0.0.1:18443'
const base = origin + '/cuaderno-cocina'
const deferred = () => {let resolve; const promise = new Promise(done => {resolve = done}); return {promise, resolve}}
const flush = async () => {for (let i = 0; i < 30; i++) await Promise.resolve()}
const turn = () => new Promise(resolve => setImmediate(resolve))
class Page extends EventEmitter {
  frame = {}
  mainFrame() {return this.frame}
}
function documentRequest(page, url = base + '/recipe/6', frame = page.frame, method = 'GET') {
  page.emit('request', {method: () => method, url: () => url, isNavigationRequest: () => true, frame: () => frame})
}
function nativeRequest(page, path, response = Promise.resolve({status: () => 200, finished: async () => null}), method = 'GET') {
  page.emit('request', {method: () => method, url: () => base + path, isNavigationRequest: () => false,
    frame: () => page.frame, response: () => response})
}
function bootstrap(page) {
  nativeRequest(page, '/api/user-preference/')
  nativeRequest(page, '/api/recipe/flat/')
}
function observed(promise) {
  let settled = false
  const done = promise.then(value => {settled = true; return value}, error => {settled = true; throw error})
  void done.catch(() => {})
  return {done, settled: () => settled}
}
test.beforeEach(() => {process.env.BASE_URL = base + '/'})

test('fresh authenticated document waits for late flat headers and its body after the visible UI', async () => {
  const page = new Page(), headers = deferred(), body = deferred()
  const barrier = observed(withAuthenticatedReadBarrier(page, async () => {documentRequest(page); nativeRequest(page, '/api/user-preference/'); return 'UI ready'}))
  try {
    await flush(); assert.equal(barrier.settled(), false)
    nativeRequest(page, '/api/recipe/flat/', headers.promise); await flush(); assert.equal(barrier.settled(), false)
    headers.resolve({status: () => 200, finished: () => body.promise}); await flush(); assert.equal(barrier.settled(), false)
    body.resolve(null); assert.equal(await barrier.done, 'UI ready')
    assert.equal(page.listenerCount('request'), 0)
  } finally {headers.resolve({status: () => 200, finished: () => body.promise}); body.resolve(null); await barrier.done}
})

test('a second editor document requires its own bootstrap after the first document already completed', async () => {
  const page = new Page(), secondFlat = deferred()
  const barrier = observed(withAuthenticatedReadBarrier(page, async () => {
    documentRequest(page, base + '/edit/recipe/'); bootstrap(page); await flush()
    documentRequest(page, base + '/edit/recipe/53'); nativeRequest(page, '/api/user-preference/'); return 'created editor ready'
  }))
  try {
    await turn(); assert.equal(barrier.settled(), false, 'the first document cannot satisfy the second flat GET')
    nativeRequest(page, '/api/recipe/flat/', Promise.resolve({status: () => 200, finished: () => secondFlat.promise}))
    await flush(); assert.equal(barrier.settled(), false)
    secondFlat.resolve(null); assert.equal(await barrier.done, 'created editor ready')
  } finally {secondFlat.resolve(null); await barrier.done}
})

test('a second document started while the first body drains still cannot reuse its resolved startup signal', async () => {
  const page = new Page(), firstBody = deferred(), secondBody = deferred()
  const barrier = observed(withAuthenticatedReadBarrier(page, async () => {
    documentRequest(page); nativeRequest(page, '/api/user-preference/')
    nativeRequest(page, '/api/recipe/flat/', Promise.resolve({status: () => 200, finished: () => firstBody.promise}))
  }))
  try {
    await flush(); documentRequest(page, base + '/recipe/53'); nativeRequest(page, '/api/user-preference/')
    firstBody.resolve(null); await flush(); assert.equal(barrier.settled(), false)
    nativeRequest(page, '/api/recipe/flat/', Promise.resolve({status: () => 200, finished: () => secondBody.promise}))
    await flush(); assert.equal(barrier.settled(), false)
    secondBody.resolve(null); await barrier.done
  } finally {firstBody.resolve(null); secondBody.resolve(null); await barrier.done}
})

test('SaveAndView SPA needs no new bootstrap but drains its native route bodies', async () => {
  const page = new Page(), body = deferred()
  const barrier = observed(withAuthenticatedReadBarrier(page, async () => {
    nativeRequest(page, '/api/recipe/53/', Promise.resolve({finished: () => body.promise})); return 'SPA recipe'
  }))
  await flush(); assert.equal(barrier.settled(), false)
  body.resolve(null); assert.equal(await barrier.done, 'SPA recipe')
  assert.equal(page.listenerCount('request'), 0)
})

test('iframe and foreign main documents cannot demand a new own authenticated bootstrap', async () => {
  for (const [url, frame] of [[base + '/recipe/6', {}], ['https://other.invalid/recipe/6', undefined]]) {
    const page = new Page()
    assert.equal(await withAuthenticatedReadBarrier(page, async () => {
      documentRequest(page, url, frame === undefined ? page.frame : frame); return 'ready'
    }), 'ready')
  }
})

test('print opt-out preserves native reads without demanding absent GlobalSearch', async () => {
  const page = new Page()
  assert.equal(await withNativeReadBarrier(page, async () => {
    documentRequest(page, base + '/recipe/6?print=true'); nativeRequest(page, '/api/recipe/6/'); return 'print ready'
  }, ['/api/recipe/6/']), 'print ready')
})

test('missing flat fails inside the existing eight-second budget and removes the listener', async t => {
  t.mock.timers.enable({apis: ['setTimeout']})
  const page = new Page()
  const barrier = withAuthenticatedReadBarrier(page, async () => {documentRequest(page); nativeRequest(page, '/api/user-preference/')})
  const rejection = assert.rejects(barrier, /eight-second/)
  await flush(); t.mock.timers.tick(8_000); await rejection
  assert.equal(page.listenerCount('request'), 0)
})

test('a second main document cannot restart the eight-second native startup deadline', async t => {
  t.mock.timers.enable({apis: ['setTimeout']})
  const page = new Page(), first = deferred()
  const barrier = withAuthenticatedReadBarrier(page, async () => {
    documentRequest(page); nativeRequest(page, '/api/user-preference/')
    nativeRequest(page, '/api/recipe/flat/', Promise.resolve({status: () => 200, finished: () => first.promise}))
  })
  const rejection = assert.rejects(barrier, /eight-second/)
  await flush(); t.mock.timers.tick(7_999)
  documentRequest(page, base + '/edit/recipe/53'); nativeRequest(page, '/api/user-preference/')
  first.resolve(null); await flush(); t.mock.timers.tick(1); await rejection
  assert.equal(page.listenerCount('request'), 0)
})

for (const [name, response] of [
  ['HTTP failure', Promise.resolve({status: () => 403, finished: async () => null})],
  ['canceled response', Promise.resolve(null)],
  ['canceled body', Promise.resolve({status: () => 200, finished: async () => 'NS_BINDING_ABORTED'})],
]) test('fresh authenticated bootstrap rejects ' + name, async () => {
  const page = new Page()
  const barrier = withAuthenticatedReadBarrier(page, async () => {
    documentRequest(page); nativeRequest(page, '/api/user-preference/')
    nativeRequest(page, '/api/recipe/flat/', response)
  })
  await assert.rejects(barrier)
  assert.equal(page.listenerCount('request'), 0)
})

test('native view-log keeps the original exact 201 assertion, including on SPA transitions', async () => {
  for (const status of [200, 201]) {
    const page = new Page()
    const barrier = withAuthenticatedReadBarrier(page, async () => {
      nativeRequest(page, '/api/view-log/', Promise.resolve({status: () => status, finished: async () => null}), 'POST')
    }, [], ['/api/view-log/'])
    if (status === 201) await barrier
    else await assert.rejects(barrier, /native recipe view is logged/)
    assert.equal(page.listenerCount('request'), 0)
  }
})

test('actual favorite reload and aria assertion cannot navigate until its late flat body finishes', async () => {
  const spec = stripTypeScriptTypes(readFileSync(new URL('./functional-extensions-acceptance.spec.ts', import.meta.url), 'utf8'))
  const startMarker = "await observe(page, `/api/cuaderno/recipes/${recipe.id}/favorite/`, 'PUT'"
  const begin = spec.indexOf('\n', spec.indexOf(startMarker))
  const end = spec.indexOf('expect((await peerRead()).is_favorite)', begin)
  assert.ok(begin >= 0 && end > begin)
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
  const fragment = new AsyncFunction('page','panel','recipe','expect','appPath','withAuthenticatedReadBarrier',spec.slice(begin,end))
  const page = new Page(), preference = deferred(), flatHeaders = deferred(), flatBody = deferred()
  const navigations = [], favoriteButton = {}, panel = {getByRole: () => favoriteButton}
  page.reload = async () => {
    documentRequest(page)
    nativeRequest(page, '/api/user-preference/', Promise.resolve({status: () => 200, finished: () => preference.promise}))
    nativeRequest(page, '/api/recipe/6/')
    nativeRequest(page, '/api/cuaderno/recipes/6/extras/')
    nativeRequest(page, '/api/cuaderno/recipes/6/ingredient-yields/')
    nativeRequest(page, '/api/view-log/', Promise.resolve({status: () => 201, finished: async () => null}), 'POST')
  }
  page.goto = async url => {navigations.push(url); documentRequest(page, origin + url); bootstrap(page)}
  page.getByRole = () => ({heading: true})
  page.locator = () => ({filter: () => ({link: true})})
  const expect = value => ({async toHaveAttribute(name, expected) {assert.equal(value,favoriteButton); assert.equal(name,'aria-pressed'); assert.equal(expected,'true')}, async toBeVisible() {}})
  const run = fragment(page,panel,{id:6,name:'CUADERNO-E2E receta pública'},expect,suffix=>'/cuaderno-cocina'+suffix,withAuthenticatedReadBarrier)
  void run.catch(() => {})
  try {
    await turn(); assert.deepEqual(navigations, [], 'visible favorite alone cannot permit leaving the reloaded document')
    preference.resolve(null); await turn(); assert.deepEqual(navigations, [], 'flat can mount after preference completion')
    nativeRequest(page, '/api/recipe/flat/', flatHeaders.promise)
    flatHeaders.resolve({status: () => 200, finished: () => flatBody.promise})
    await turn(); assert.deepEqual(navigations, [], 'flat response headers cannot permit navigation before the body')
    flatBody.resolve(null); await run
    assert.deepEqual(navigations, ['/cuaderno-cocina/cuaderno/favoritas'])
    assert.equal(page.listenerCount('request'), 0)
  } finally {
    preference.resolve(null); flatHeaders.resolve({status: () => 200, finished: () => flatBody.promise}); flatBody.resolve(null)
    nativeRequest(page, '/api/recipe/flat/', Promise.resolve({status: () => 200, finished: async () => null}))
    await run
  }
})
