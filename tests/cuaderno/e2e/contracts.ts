import path from 'node:path'

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
  return path.join(import.meta.dirname, '.auth', `${edition}-${role}.json`)
}

export const featureMatrix = {
  prices: new Set<Edition>(editions),
  production: new Set<Edition>(['profesional', 'integral']),
  warehouse: new Set<Edition>(['integral']),
} as const

export const fixturePrefix = process.env.CUADERNO_E2E_FIXTURE_PREFIX || 'CUADERNO-E2E'
