import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {loadTestModule} from '../cuaderno/testModuleLoader.mjs'

const {createRecipeWakeLock} = await import(await loadTestModule('../utils/recipeWakeLock.ts'))
const tick = () => new Promise(resolve => setImmediate(resolve))

class ScreenLock extends EventTarget {
    released = false
    releases = 0
    async release() {
        this.releases++
        this.released = true
        this.dispatchEvent(new Event('release'))
    }
}

function fixture(request = async () => new ScreenLock(), visibility = 'visible') {
    const document = new EventTarget()
    document.visibilityState = visibility
    const errors = [], requests = []
    const navigator = {wakeLock: {request: type => { requests.push(type); return request() }}}
    return {document, errors, requests, navigator,
        controller: createRecipeWakeLock(navigator, document, error => errors.push(error)),
        visibility(state) { document.visibilityState = state; document.dispatchEvent(new Event('visibilitychange')) },
    }
}

test('navigator wake-lock permission denial is consumed without breaking recipe entry', async () => {
    const denial = new DOMException('Wake Lock permission request denied', 'NotAllowedError')
    const state = fixture(async () => { throw denial })
    await assert.doesNotReject(state.controller.request())
    assert.deepEqual(state.requests, ['screen'])
    assert.deepEqual(state.errors, [])
    await state.controller.release()
})

test('unsupported and initially hidden documents do not request an optional lock', async () => {
    const errors = []
    await createRecipeWakeLock({}, new EventTarget(), error => errors.push(error)).request()
    const state = fixture(undefined, 'hidden')
    await state.controller.request()
    assert.deepEqual(state.requests, [])
    state.visibility('visible')
    await tick()
    assert.deepEqual(state.requests, ['screen'])
    await state.controller.release()
    assert.deepEqual(errors, [])
})

test('successful native screen locks are released when leaving the recipe', async () => {
    const lock = new ScreenLock()
    const state = fixture(async () => lock)
    await state.controller.request()
    await state.controller.release()
    assert.equal(lock.releases, 1)
    state.visibility('hidden'); state.visibility('visible')
    await tick()
    assert.deepEqual(state.requests, ['screen'])
    assert.deepEqual(state.errors, [])
})

test('visible reacquisition denial is handled after a successful lock', async () => {
    const lock = new ScreenLock()
    let count = 0
    const state = fixture(async () => {
        if (count++) throw new DOMException('Wake Lock permission request denied', 'NotAllowedError')
        return lock
    })
    await state.controller.request()
    state.visibility('hidden')
    await tick()
    state.visibility('visible')
    await tick()
    assert.deepEqual(state.requests, ['screen', 'screen'])
    assert.deepEqual(state.errors, [])
    await state.controller.release()
})

test('visible browser revocation waits for a new visibility transition instead of spinning', async () => {
    const locks = [new ScreenLock(), new ScreenLock()]
    let index = 0
    const state = fixture(async () => locks[index++])
    await state.controller.request()
    await locks[0].release()
    await tick()
    assert.deepEqual(state.requests, ['screen'])
    state.visibility('hidden')
    state.visibility('visible')
    await tick()
    assert.deepEqual(state.requests, ['screen', 'screen'])
    await state.controller.release()
    assert.equal(locks[1].releases, 1)
})

test('a pending native request never retains its lock in a hidden document', async () => {
    for (const states of [['hidden'], ['hidden', 'visible', 'hidden']]) {
        let complete
        const waiting = new Promise(resolve => { complete = resolve })
        const lock = new ScreenLock()
        const replacement = new ScreenLock()
        let index = 0
        const state = fixture(() => index++ === 0 ? waiting : Promise.resolve(replacement))
        const request = state.controller.request()
        await tick()
        for (const visibility of states) state.visibility(visibility)
        complete(lock)
        await request
        assert.equal(lock.releases, 1)
        assert.deepEqual(state.requests, ['screen'])
        state.visibility('visible')
        await tick()
        assert.deepEqual(state.requests, ['screen', 'screen'])
        await state.controller.release()
        assert.equal(replacement.releases, 1)
    }
})

test('a native lock arriving after teardown is immediately released', async () => {
    let complete
    const waiting = new Promise(resolve => { complete = resolve })
    const lock = new ScreenLock()
    const state = fixture(() => waiting)
    const request = state.controller.request()
    await state.controller.release()
    complete(lock)
    await request
    assert.equal(lock.releases, 1)
    assert.deepEqual(state.errors, [])
})

test('unexpected native request and release failures are reported, not discarded', async () => {
    const failure = new Error('wake-lock service crashed')
    const state = fixture(async () => { throw failure })
    await assert.doesNotReject(state.controller.request())
    assert.deepEqual(state.errors, [failure])
    await state.controller.release()
    const lock = new ScreenLock()
    lock.release = async () => { throw failure }
    const releaseState = fixture(async () => lock)
    await releaseState.controller.request()
    await assert.doesNotReject(releaseState.controller.release())
    assert.deepEqual(releaseState.errors, [failure])
})

test('recipe entry and teardown use the handler with an explicit unexpected-error reporter', () => {
    const source = readFileSync(new URL('../components/display/RecipeView.vue', import.meta.url), 'utf8')
    assert.match(source, /import \{createRecipeWakeLock\} from ["']@\/utils\/recipeWakeLock["']/)
    assert.match(source, /onMounted\(\(\) => \{[\s\S]*?wakeLock\.request\(\)/)
    assert.match(source, /onBeforeUnmount\(\(\) => \{[\s\S]*?wakeLock\.release\(\)/)
    assert.match(source, /console\.error\([^\n]*error\)/)
    assert.doesNotMatch(source, /useWakeLock/)
})
