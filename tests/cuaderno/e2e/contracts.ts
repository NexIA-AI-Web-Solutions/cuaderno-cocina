import path from 'node:path'
import {authDirectory} from './auth-state.mjs'

export const editions = ['esencial', 'profesional', 'integral'] as const
export const roles = ['consulta', 'cocina', 'responsable'] as const
export const widths = [390, 768, 1440] as const

export type Edition = typeof editions[number]
export type Role = typeof roles[number]
export type Width = typeof widths[number]
export type BrowserEngine = 'chromium' | 'firefox' | 'webkit'

export type Identity = {edition: Edition; role: Role; width: Width; browser: BrowserEngine; username: string}

export function projectName(edition: Edition, role: Role, width: Width, browser?: BrowserEngine): string {
  return `${edition}-${role}-${width}${browser && browser !== 'chromium' ? `-${browser}` : ''}`
}

export function parseProject(name: string): Identity {
  const match = /^(esencial|profesional|integral)-(consulta|cocina|responsable)-(390|768|1440)(?:-(firefox|webkit))?$/.exec(name)
  if (!match) throw new Error(`Proyecto E2E desconocido: ${name}`)
  const edition = match[1] as Edition
  const role = match[2] as Role
  const width = Number(match[3]) as Width
  const browser = (match[4] || 'chromium') as BrowserEngine
  return {edition, role, width, browser, username: `demo-${edition}-${role}`}
}

export function authFile(edition: Edition, role: Role): string {
  return path.join(authDirectory(), `${edition}-${role}.json`)
}

export const featureMatrix = {
  prices: new Set<Edition>(editions),
  production: new Set<Edition>(['profesional', 'integral']),
  warehouse: new Set<Edition>(['integral']),
} as const

export const fixturePrefix = process.env.CUADERNO_E2E_FIXTURE_PREFIX || 'CUADERNO-E2E'

// Browser and API paths share the deployment prefix; root remains a valid baseline.
export function appPath(value: string, baseURL = process.env.BASE_URL || 'http://127.0.0.1:18081'): string {
  const base = new URL(baseURL)
  const prefix = base.pathname.replace(/\/+$/, '')
  if (!value.startsWith('/') || value.startsWith('//')) throw new Error('Ruta de aceptación inválida.')
  const input = new URL(value, base.origin)
  const alreadyPrefixed = prefix && (input.pathname === prefix || input.pathname.startsWith(prefix + '/'))
  const resolved = new URL(alreadyPrefixed ? value : prefix + value, base.origin)
  if (resolved.origin !== base.origin || (prefix && resolved.pathname !== prefix && !resolved.pathname.startsWith(prefix + '/'))) {
    throw new Error('La ruta de aceptación escapa del prefijo.')
  }
  return resolved.pathname + resolved.search + resolved.hash
}
