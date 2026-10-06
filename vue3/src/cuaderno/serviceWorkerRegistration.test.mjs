import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'

function registration(baseURI, workerPath = '/cuaderno-cocina/service-worker.js') {
    const template = readFileSync(new URL('../../../cookbook/templates/frontend/tandoor.html', import.meta.url), 'utf8')
    const script = template.match(/<script type="application\/javascript">([\s\S]*?)<\/script>/)[1]
        .replace("{% url 'service_worker' %}", workerPath)
    const calls = [], warnings = []
    const context = {
        URL, document: {baseURI},
        window: {location: {origin: 'https://cocina.example'}, addEventListener: (_event, callback) => callback()},
        navigator: {serviceWorker: {register: (url, options) => { calls.push({url: String(url), scope: String(options.scope)}); return Promise.resolve({}) }}},
        console: {warn: (...args) => warnings.push(args)},
    }
    vm.runInNewContext(script, context)
    return {calls, warnings}
}

test('worker registration uses exactly the prefixed base and endpoint', () => {
    assert.deepEqual(registration('https://cocina.example/cuaderno-cocina/').calls, [{
        url: 'https://cocina.example/cuaderno-cocina/service-worker.js',
        scope: 'https://cocina.example/cuaderno-cocina/',
    }])
    assert.deepEqual(registration('https://cocina.example/kitchen/', '/kitchen/service-worker.js').calls, [{
        url: 'https://cocina.example/kitchen/service-worker.js', scope: 'https://cocina.example/kitchen/',
    }])
})

test('no worker is registered for the root, a foreign origin or a mismatched endpoint', () => {
    for (const [base, endpoint] of [
        ['https://cocina.example/', '/service-worker.js'],
        ['https://other.example/cuaderno-cocina/', '/cuaderno-cocina/service-worker.js'],
        ['https://cocina.example/cuaderno-cocina/', '/service-worker.js'],
        ['https://cocina.example/cuaderno-cocina/', '/other/service-worker.js'],
        ['https://cocina.example/cuaderno-cocina', '/cuaderno-cocina/service-worker.js'],
    ]) assert.deepEqual(registration(base, endpoint).calls, [], base)
})
