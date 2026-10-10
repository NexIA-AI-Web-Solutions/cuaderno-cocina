import test from 'node:test'
import assert from 'node:assert/strict'
import {mountFunctional, all, textOf} from './functionalComponentHarness.mjs'
const minimum = {
    recipe_gallery: 0, recipe_favorites: 0, recipe_variants: 0, diet_declarations: 0, menu_five_weeks: 0,
    menu_courses: 1, menu_templates: 1, menu_diet_filter: 1, calendar_events: 1, staff_absences: 1, menu_print: 1,
    customer_reservations: 1, merged_menu_print: 2,
}
const editions = ['esencial', 'profesional', 'integral']
const flagsFor = rank => Object.fromEntries(Object.entries(minimum).map(([key, needed]) => [key, rank >= needed]))
test('anonymous or shared rendering performs no edition request', async () => {
    const mounted = await mountFunctional('./components/PlanFeatures.vue', {}, () => assert.fail('Anonymous request'))
    try {assert.equal(mounted.calls.length, 0); assert.equal(textOf(mounted.root), '')} finally {mounted.close()}
})
for (const [rank, edition] of editions.entries()) test(`comparison retains exact plan boundaries for ${edition}`, async () => {
    const mounted = await mountFunctional('./components/PlanFeatures.vue', {authenticated: true}, (path, method) => {
        assert.equal(path, 'edition/'); assert.equal(method, 'GET'); return {edition, features: flagsFor(rank)}
    })
    try {
        assert.equal(mounted.calls.length, 1)
        for (const [key, needed] of Object.entries(minimum)) {
            const row = all(mounted.root, node => node.props?.['data-feature'] === key)[0]
            assert.ok(row, key)
            for (const [column, plan] of editions.entries()) {
                const cell = all(row, node => node.props?.['data-plan'] === plan)[0]
                assert.equal(textOf(cell), column >= needed ? 'Incluido' : column === rank ? 'No habilitado' : '—', `${key}/${plan}`)
            }
        }
        const headers = all(mounted.root, node => node.type === 'th' && node.props.scope === 'col')
        for (const [index, price] of ['500 € + 17 €/mes', '1000 € + 20 €/mes', '1500 € + 30 €/mes'].entries()) assert.ok(textOf(headers[index + 1]).includes(price))
        assert.match(textOf(mounted.root), /no realiza contrataciones ni cobros/)
        assert.equal(all(mounted.root, node => node.type === 'button' || node.type === 'input').length, 0)
    } finally {mounted.close()}
})
test('server flags are authoritative for the current edition even when metadata suggests inclusion', async () => {
    const mounted = await mountFunctional('./components/PlanFeatures.vue', {authenticated: true}, () => ({edition: 'integral', features: {...flagsFor(2), merged_menu_print: false}}))
    try {
        const row = all(mounted.root, node => node.props?.['data-feature'] === 'merged_menu_print')[0]
        const cell = all(row, node => node.props?.['data-plan'] === 'integral')[0]
        assert.equal(textOf(cell), 'No habilitado')
    } finally {mounted.close()}
})
test('missing server flags cannot certify an active edition', async () => {
    const mounted = await mountFunctional('./components/PlanFeatures.vue', {authenticated: true}, () => ({edition: 'integral', features: {}}))
    try {assert.match(textOf(mounted.root), /No se pudo confirmar la edición/); assert.doesNotMatch(textOf(mounted.root), /Tu edición/)} finally {mounted.close()}
})
