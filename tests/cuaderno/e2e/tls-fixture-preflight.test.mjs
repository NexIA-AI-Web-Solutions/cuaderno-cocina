import assert from 'node:assert/strict'
import test from 'node:test'
import {assertWorkerProof} from './tls-fixture-preflight.mjs'

const baseURL = 'https://127.0.0.1:18443/cuaderno-cocina/'
const ownName = 'cuaderno-%2Fcuaderno-cocina%2F-precache-v1'
const proof = {secure: true, controller: baseURL + 'service-worker.js', state: 'activated', scopes: [baseURL],
  caches: {[ownName]: [baseURL + 'static/vue3/assets/index.js']}}

test('preflight requires actual same-scope worker control and nonempty public assets', () => {
  assert.deepEqual(assertWorkerProof(proof, baseURL), {cache_count: 1, public_asset_count: 1})
  assert.throws(() => assertWorkerProof({...proof, caches: {[ownName]: []}}, baseURL), /assets públicos reales/)
})

test('preflight rejects untrusted contexts, missing controller and foreign scopes', () => {
  for (const changes of [{secure: false}, {controller: ''}, {state: 'activating'}, {scopes: ['https://127.0.0.1:18443/']}]) {
    assert.throws(() => assertWorkerProof({...proof, ...changes}, baseURL))
  }
})

test('preflight rejects foreign cache namespaces and private or foreign entries', () => {
  assert.throws(() => assertWorkerProof({...proof, caches: {images: proof.caches[ownName]}}, baseURL), /namespace/)
  for (const source of [baseURL + 'media/private.jpg', baseURL + 'api/recipe/',
    'https://foreign.invalid/static/index.js', baseURL + 'static/shared.jpg?share=synthetic']) {
    assert.throws(() => assertWorkerProof({...proof, caches: {[ownName]: [source]}}, baseURL))
  }
})
