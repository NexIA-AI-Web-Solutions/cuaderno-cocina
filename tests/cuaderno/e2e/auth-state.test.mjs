import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtemp, rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {authDirectory, bindAuthState, authStateMatches, reserveFreshLogin} from './auth-state.mjs'

const baseURL = 'https://127.0.0.1:18443/cuaderno-cocina/'
const identity = {edition: 'integral', role: 'responsable'}
const cookie = name => ({name, value: 'synthetic', domain: '127.0.0.1', path: '/cuaderno-cocina/',
  secure: true, httpOnly: name === 'cuaderno_sessionid', expires: 2_000_000_000, sameSite: 'Lax'})
const state = () => bindAuthState({cookies: [cookie('cuaderno_sessionid'), cookie('cuaderno_csrftoken')],
  origins: [{origin: new URL(baseURL).origin, localStorage: []}]}, baseURL, identity)

test('reusable auth binds origin, prefix and identity instead of accepting an empty shape', () => {
  assert.equal(authStateMatches(state(), baseURL, identity, 1_900_000_000), true)
  assert.equal(authStateMatches({cookies: [], origins: []}, baseURL, identity), false)
  for (const target of ['https://127.0.0.1:18444/cuaderno-cocina/', 'http://127.0.0.1:18443/cuaderno-cocina/', 'https://127.0.0.1:18443/']) {
    assert.equal(authStateMatches(state(), target, identity, 1_900_000_000), false)
  }
  assert.equal(authStateMatches(state(), baseURL, {...identity, role: 'consulta'}, 1_900_000_000), false)
  assert.notEqual(authDirectory(baseURL), authDirectory('http://127.0.0.1:18081/'))
})

test('auth rejects expired, foreign-name, broad-path and insecure cookies', () => {
  for (const update of [{expires: 1}, {expires: NaN}, {name: 'sessionid'}, {path: '/'}, {secure: false}, {domain: 'other.test'}, {httpOnly: false}]) {
    const invalid = state()
    Object.assign(invalid.cookies[0], update)
    assert.equal(authStateMatches(invalid, baseURL, identity, 1_900_000_000), false)
  }
  const invalidCsrf = state()
  invalidCsrf.cookies[1].name = 'csrftoken'
  assert.equal(authStateMatches(invalidCsrf, baseURL, identity), false)
})

test('fresh logout sessions share a conservative login budget across worker module lifetimes', async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'cuaderno-login-budget-'))
  let now = 100_000
  const waits = [], submissions = []
  try {
    for (let index = 0; index < 5; index += 1) {
      await reserveFreshLogin(baseURL, {directory, clock: () => now, sleep: async delay => { waits.push(delay); now += delay }})
      submissions.push(now)
    }
    assert.deepEqual(waits, [16_000, 16_000, 16_000, 16_000])
    assert.equal(submissions[4] - submissions[0], 64_000)
  } finally {
    await rm(directory, {recursive: true})
  }
})
