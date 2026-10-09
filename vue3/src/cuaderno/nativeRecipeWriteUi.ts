export type NativeRecipeWriteAccess = 'loading' | 'allowed' | 'readonly' | 'unavailable'

type Membership = {space?: number; active?: boolean; groups?: Array<{name?: string}>} | null | undefined

// Match the native backend's single active membership, including its Space binding.
export function nativeRecipeMembership(memberships: Exclude<Membership, null | undefined>[], spaceId: number | undefined): Membership {
    const active = memberships.filter(membership => membership.active === true)
    return active.length === 1 && active[0].space === spaceId && spaceId !== undefined ? active[0] : null
}

// Native recipe/import writes require the active space's user/admin group.
// Global staff/superuser flags do not replace this membership permission.
export function nativeRecipeWriteAccess(authenticated: boolean, initialized: boolean,
                                       membershipLoaded: boolean, membership: Membership): NativeRecipeWriteAccess {
    if (!initialized) return 'loading'
    if (!authenticated || !membershipLoaded || !membership || membership.active !== true
        || !Array.isArray(membership.groups)) return 'unavailable'
    if (membership.groups.some(group => group.name === 'user' || group.name === 'admin')) return 'allowed'
    return membership.groups.some(group => group.name === 'guest') ? 'readonly' : 'unavailable'
}

export function nativeRecipeWriteMessage(access: NativeRecipeWriteAccess): string {
    if (access === 'loading') return 'Comprobando permisos de recetas…'
    if (access === 'readonly') return 'Modo Consulta: puedes revisar recetas, pero crear, editar o importar requiere el rol Cocina o Responsable. Pide a un Responsable que revise tu acceso.'
    return 'No se han podido confirmar tus permisos para crear, editar o importar recetas. Vuelve a recetas y recarga la página; si continúa, pide a un Responsable que revise tu acceso.'
}
