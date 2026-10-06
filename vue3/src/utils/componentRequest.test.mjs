import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./componentRequest.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, {compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
}}).outputText
const {settleComponentRequest} = await import(
    `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
)

function deferred() {
    let resolve
    let reject
    const promise = new Promise((accept, decline) => {
        resolve = accept
        reject = decline
    })
    return {promise, resolve, reject}
}

test('a request rejected after component teardown is consumed without reporting an error', async () => {
    const pending = deferred()
    const controller = new AbortController()
    const successes = []
    const errors = []
    const settled = settleComponentRequest(
        pending.promise, controller.signal,
        value => successes.push(value),
        error => errors.push(error),
    )

    controller.abort()
    pending.reject(new Error('WebKit cancelled the document request'))
    await settled

    assert.deepEqual(successes, [])
    assert.deepEqual(errors, [])
})

test('a response arriving after component teardown cannot update component state', async () => {
    const pending = deferred()
    const controller = new AbortController()
    const successes = []
    const errors = []
    const settled = settleComponentRequest(
        pending.promise, controller.signal,
        value => successes.push(value),
        error => errors.push(error),
    )

    controller.abort()
    pending.resolve({count: 99})
    await settled

    assert.deepEqual(successes, [])
    assert.deepEqual(errors, [])
})

test('a live component still receives successful responses and reports real failures', async () => {
    const controller = new AbortController()
    const successes = []
    const errors = []

    await settleComponentRequest(
        Promise.resolve({count: 4}), controller.signal,
        value => successes.push(value),
        error => errors.push(error),
    )
    const failure = new Error('connection refused')
    await settleComponentRequest(
        Promise.reject(failure), controller.signal,
        value => successes.push(value),
        error => errors.push(error),
    )

    assert.deepEqual(successes, [{count: 4}])
    assert.deepEqual(errors, [failure])
})
