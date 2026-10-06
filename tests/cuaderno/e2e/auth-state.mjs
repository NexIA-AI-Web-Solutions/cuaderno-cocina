import {createHash} from 'node:crypto'
import {lstat, mkdir, readFile, writeFile} from 'node:fs/promises'
import path from 'node:path'

export function authTarget(baseURL, identity) {
  const url = new URL(baseURL)
  return {origin: url.origin, path: url.pathname.replace(/\/+$/, '') + '/',
    username: `demo-${identity.edition}-${identity.role}`}
}

export function authDirectory(baseURL = process.env.BASE_URL || 'http://127.0.0.1:18081') {
  const url = new URL(baseURL)
  const target = url.origin + url.pathname.replace(/\/+$/, '') + '/'
  const key = createHash('sha256').update(target).digest('hex').slice(0, 20)
  return path.join(import.meta.dirname, '.auth', key)
}

export function bindAuthState(state, baseURL, identity) {
  return {...state, cuadernoAuth: authTarget(baseURL, identity)}
}

export function authStateMatches(state, baseURL, identity, now = Date.now() / 1000) {
  if (!state || !Array.isArray(state.cookies) || !Array.isArray(state.origins)) return false
  const target = authTarget(baseURL, identity), url = new URL(baseURL)
  if (!state.cuadernoAuth || Object.entries(target).some(([key, value]) => state.cuadernoAuth[key] !== value)) return false
  if (state.origins.some(entry => entry.origin !== target.origin)) return false
  const prefix = target.path !== '/'
  const sessionName = prefix ? 'cuaderno_sessionid' : 'sessionid'
  const csrfName = prefix ? 'cuaderno_csrftoken' : 'csrftoken'
  return [sessionName, csrfName].every(name => {
    const cookies = state.cookies.filter(cookie => cookie.name === name)
    if (cookies.length !== 1) return false
    const cookie = cookies[0]
    return typeof cookie.value === 'string' && cookie.value.length > 0 && cookie.domain === url.hostname &&
      cookie.path === target.path && cookie.secure === (url.protocol === 'https:') &&
      cookie.httpOnly === (name === sessionName) && Number.isFinite(cookie.expires) &&
      (cookie.expires === -1 || cookie.expires > now)
  })
}

export async function validAuthState(file, baseURL, identity) {
  try {
    const stat = await lstat(file)
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size === 0) return false
    return authStateMatches(JSON.parse(await readFile(file, 'utf8')), baseURL, identity)
  } catch {
    return false
  }
}

export async function saveAuthState(file, state, baseURL, identity) {
  if (!authStateMatches(bindAuthState(state, baseURL, identity), baseURL, identity)) {
    throw new Error('La sesión creada no cumple el contrato de cookies del destino.')
  }
  await writeFile(file, JSON.stringify(bindAuthState(state, baseURL, identity)), {mode: 0o600})
}

/** The one-worker harness spaces additional login submissions to <=4/minute. */
export async function reserveFreshLogin(baseURL, {directory = authDirectory(baseURL), clock = Date.now,
  sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))} = {}) {
  await mkdir(directory, {recursive: true, mode: 0o700})
  const file = path.join(directory, 'fresh-login.json')
  let last = 0
  try { last = JSON.parse(await readFile(file, 'utf8')).last } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  if (!Number.isFinite(last) || last > clock()) throw new Error('El registro del límite de login tiene una fecha inválida.')
  const delay = Math.max(0, last + 16_000 - clock())
  if (delay) await sleep(delay)
  await writeFile(file, JSON.stringify({last: clock()}), {mode: 0o600})
}
