import assert from 'node:assert/strict'
import test from 'node:test'

import {argumentsFrom} from './prepare-auth.mjs'

test('auth setup accepts only explicit loopback candidate targets', () => {
  assert.deepEqual(argumentsFrom(['--base-url', 'http://127.0.0.1:18081', '--reuse']), {
    baseURL: 'http://127.0.0.1:18081', reuse: true,
  })
  assert.equal(argumentsFrom(['--base-url', 'https://localhost:8443']).baseURL, 'https://localhost:8443')
  assert.throws(() => argumentsFrom(['--base-url', 'https://candidate.example']), /loopback/)
  assert.throws(() => argumentsFrom(['--unknown']), /desconocido/)
})
