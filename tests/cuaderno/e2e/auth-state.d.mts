import type {BrowserContext} from '@playwright/test'
type Identity = {edition: string; role: string}
type State = Awaited<ReturnType<BrowserContext['storageState']>>
type Target = {origin: string; path: string; username: string}
export function authTarget(baseURL: string, identity: Identity): Target
export function authDirectory(baseURL?: string): string
export function bindAuthState(state: State, baseURL: string, identity: Identity): State & {cuadernoAuth: Target}
export function authStateMatches(state: unknown, baseURL: string, identity: Identity, now?: number): boolean
export function validAuthState(file: string, baseURL: string, identity: Identity): Promise<boolean>
export function saveAuthState(file: string, state: State, baseURL: string, identity: Identity): Promise<void>
export function reserveFreshLogin(baseURL: string, options?: {directory?: string; clock?: () => number; sleep?: (milliseconds: number) => Promise<void>}): Promise<void>
