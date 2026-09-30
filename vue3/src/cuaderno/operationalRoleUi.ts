export type OperationalRole = {
    code: 'guest' | 'user' | 'admin'
    label: 'Consulta' | 'Cocina' | 'Responsable'
    space: number
    can_operate_cuaderno: boolean
    can_manage_edition: boolean
    native_permissions_preserved: true
}

const contracts = {
    guest: {label: 'Consulta', can_operate_cuaderno: false, can_manage_edition: false},
    user: {label: 'Cocina', can_operate_cuaderno: true, can_manage_edition: false},
    admin: {label: 'Responsable', can_operate_cuaderno: true, can_manage_edition: true},
} as const

function record(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function operationalRoleEnvelope(value: unknown): OperationalRole | null {
    if (!record(value)) return null
    const expectedKeys = [
        'can_manage_edition', 'can_operate_cuaderno', 'code', 'label',
        'native_permissions_preserved', 'space',
    ]
    const actualKeys = Object.keys(value).sort()
    if (actualKeys.length !== expectedKeys.length
        || expectedKeys.some((key, index) => key !== actualKeys[index])) return null
    if (typeof value.code !== 'string' || !(value.code in contracts)) return null
    const code = value.code as keyof typeof contracts
    const contract = contracts[code]
    if (value.label !== contract.label
        || value.can_operate_cuaderno !== contract.can_operate_cuaderno
        || value.can_manage_edition !== contract.can_manage_edition
        || value.native_permissions_preserved !== true
        || typeof value.space !== 'number' || !Number.isSafeInteger(value.space) || value.space <= 0) return null
    return value as OperationalRole
}

export function editionOperationalRole(value: unknown): OperationalRole | null {
    return record(value) ? operationalRoleEnvelope(value.operational_role) : null
}
