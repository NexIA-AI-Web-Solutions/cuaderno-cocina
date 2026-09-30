import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./operationalRoleUi.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {operationalRoleEnvelope} = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const roles = [
    {code: 'guest', label: 'Consulta', space: 4, can_operate_cuaderno: false, can_manage_edition: false, native_permissions_preserved: true},
    {code: 'user', label: 'Cocina', space: 4, can_operate_cuaderno: true, can_manage_edition: false, native_permissions_preserved: true},
    {code: 'admin', label: 'Responsable', space: 4, can_operate_cuaderno: true, can_manage_edition: true, native_permissions_preserved: true},
]

test('accepts the three exact role contracts', () => {
    for (const role of roles) assert.deepEqual(operationalRoleEnvelope(role), role)
})

test('fails closed on unsafe IDs, unknown roles and contradictory capabilities', () => {
    const invalid = [
        {...roles[0], space: true},
        {...roles[0], space: 9007199254740992},
        {...roles[0], code: 'viewer'},
        {...roles[0], label: 'Invitado'},
        {...roles[0], can_operate_cuaderno: true},
        {...roles[1], can_manage_edition: true},
        {...roles[2], can_operate_cuaderno: false},
        {...roles[2], native_permissions_preserved: false},
        {...roles[2], extra: 'not contracted'},
        null, [], 'admin',
    ]
    for (const value of invalid) assert.equal(operationalRoleEnvelope(value), null)
})
