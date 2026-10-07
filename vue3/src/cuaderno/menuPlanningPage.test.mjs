import test from 'node:test'
import assert from 'node:assert/strict'
import {mountFunctional, button, field, textOf, flush, all} from './functionalComponentHarness.mjs'
const data = {courses: [], meal_plans: [], events: [], can_edit: false, can_manage_absences: false, can_merge_print: false}
test('Esencial direct navigation keeps native calendar access and makes no professional request', async () => {
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, path => {assert.equal(path, 'edition/'); return {edition: 'esencial'}})
    try {assert.equal(mounted.calls.length, 1); assert.match(textOf(mounted.root), /calendario de comidas sigue disponible/); assert.equal(button(mounted.root, 'Guardar nueva plantilla'), undefined)} finally {mounted.close()}
})
test('Consulta cannot submit new templates, courses or events even through a direct click', async () => {
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method) => {
        assert.equal(method, 'GET')
        if (path === 'edition/') return {edition: 'profesional'}
        if (path === 'planning/templates/?offset=0&limit=50') return {count: 0, results: []}
        assert.match(path, /^planning\/\?from_date=/); return data
    })
    try {
        for (const label of ['Guardar nueva plantilla', 'Añadir tipo de plato', 'Guardar anotación']) {
            const control = button(mounted.root, label); assert.equal(control.props.disabled, true); await control.props.onClick()
        }
        assert.equal(mounted.calls.filter(row => row.method !== 'GET').length, 0)
        assert.deepEqual(field(mounted.root, 'Tipo').props.items, [{value: 'event', label: 'Evento'}])
    } finally {mounted.close()}
})
test('a denied server print never creates a printable document', async () => {
    const meal = {id: 7, title: 'Sopa', recipe: null, meal_type: {id: 1, name: 'Comida'}, course: null, servings: '4.00', from_date: '2026-10-07T12:00:00Z', to_date: null, note: '', diet_status: 'unknown'}
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method, body) => {
        if (path === 'edition/') return {edition: 'profesional'}
        if (path === 'planning/templates/?offset=0&limit=50') return {count: 0, results: []}
        if (path.startsWith('planning/?')) return {...data, meal_plans: [meal]}
        assert.equal(path, 'planning/print/'); assert.equal(method, 'POST'); assert.deepEqual(body.menus, [{name: 'Menú', meal_plan_ids: [7]}]); throw new Error('Acceso revocado')
    })
    try {
        field(mounted.root, 'Platos del periodo').props['onUpdate:modelValue']([7]); await flush()
        button(mounted.root, 'Añadir menú a la impresión').props.onClick(); await flush()
        await button(mounted.root, 'Preparar documento').props.onClick(); await flush()
        assert.match(textOf(mounted.root), /Acceso revocado/)
        assert.equal(button(mounted.root, 'Imprimir en'), undefined)
    } finally {mounted.close()}
})

for (const diet of [null, 'celiacos']) test(`print uses the server document and optional diet ${diet || 'none'}`, async () => {
    const meal = {id: 7, title: 'Sopa', recipe: null, meal_type: {id: 1, name: 'Comida'}, course: 3, servings: '4.00', from_date: '2026-10-07T12:00:00Z', to_date: null, note: '', diet_status: 'unknown'}
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method, body) => {
        if (path === 'edition/') return {edition: 'profesional'}
        if (path === 'planning/templates/?offset=0&limit=50') return {count: 0, results: []}
        if (path.startsWith('planning/?')) return {...data, courses: [{id: 3, name: 'Nombre mutable', meal_type: 1, position: 0}], meal_plans: [meal]}
        assert.equal(path, 'planning/print/'); assert.equal(method, 'POST')
        assert.equal(body.diet, diet || undefined)
        return {orientation: 'portrait', merged: false, diet, diet_label: diet ? 'Celíacos' : null, declaration: 'Declaración manual', menus: [{name: 'Menú autorizado', entries: [{...meal, course_name: 'Primero autorizado'}]}]}
    })
    try {
        field(mounted.root, 'Platos del periodo').props['onUpdate:modelValue']([7])
        if (diet) field(mounted.root, 'Declaración dietética en el documento (opcional)').props['onUpdate:modelValue'](diet)
        await flush(); button(mounted.root, 'Añadir menú a la impresión').props.onClick(); await flush()
        await button(mounted.root, 'Preparar documento').props.onClick(); await flush()
        const document = all(mounted.root, node => node.type === 'section' && node.props['aria-label'] === 'Documento de menús')[0]
        assert.ok(document); assert.match(textOf(document), /Primero autorizado/)
        assert.doesNotMatch(textOf(document), /Nombre mutable/)
        assert.equal(all(document, node => node.type === 'th').length, diet ? 4 : 3)
        if (diet) {assert.match(textOf(document), /Celíacos/); assert.match(textOf(document), /No declarado/)}
        else assert.doesNotMatch(textOf(document), /No declarado/)
    } finally {mounted.close()}
})

test('templates beyond the first fifty use bounded pages without reloading the calendar period', async () => {
    const requests = []
    const template = id => ({id, name: `Plantilla ${id}`, weeks: 1, revision: 'a'.repeat(64), entries: []})
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, path => {
        requests.push(path)
        if (path === 'edition/') return {edition: 'profesional'}
        if (path.startsWith('planning/?')) return data
        if (path === 'planning/templates/?offset=0&limit=50') return {count: 51, results: Array.from({length: 50}, (_, index) => template(index + 1))}
        assert.equal(path, 'planning/templates/?offset=50&limit=50'); return {count: 51, results: [template(51)]}
    })
    try {
        assert.equal(requests.filter(path => path.startsWith('planning/templates/')).length, 1)
        assert.doesNotMatch(textOf(mounted.root), /Plantilla 51/)
        await button(mounted.root, 'Más plantillas').props.onClick(); await flush()
        assert.match(textOf(mounted.root), /Plantilla 51/)
        assert.equal(button(mounted.root, 'Más plantillas').props.disabled, true)
        assert.equal(requests.filter(path => path.startsWith('planning/?')).length, 1)
        await button(mounted.root, 'Plantillas anteriores').props.onClick(); await flush()
        assert.equal(button(mounted.root, 'Plantillas anteriores').props.disabled, true)
    } finally {mounted.close()}
})

test('course and event edits retain their read revision and preserve drafts after a conflict', async () => {
    const revision = 'd'.repeat(64)
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method, body) => {
        if (path === 'edition/') return {edition: 'profesional'}
        if (path.startsWith('planning/templates/')) return {count: 0, results: []}
        if (path.startsWith('planning/?')) return {...data, can_edit: true,
            courses: [{id: 3, revision, name: 'Primero', meal_type: 1, position: 0}],
            events: [{id: 4, revision, kind: 'event', title: 'Servicio especial', member_name: '', start_date: '2026-10-07', end_date: '2026-10-07', note: ''}]}
        assert.equal(method, 'PUT'); assert.equal(body.revision, revision)
        assert.ok(['planning/courses/3/', 'planning/events/4/'].includes(path)); throw new Error('Conflicto de revisión')
    })
    try {
        const editButtons = () => {
            // Vue slot fragments add empty text anchors in this virtual renderer.
            const controls = all(mounted.root, node => node.type === 'button' && textOf(node).trim() === 'Editar')
            assert.equal(controls.length, 2, 'the actual course and event edit controls are rendered')
            return controls
        }
        editButtons()[0].props.onClick(); await flush()
        field(mounted.root, 'Nombre').props['onUpdate:modelValue']('Mi primero'); await flush()
        await button(mounted.root, 'Guardar tipo de plato').props.onClick(); await flush()
        assert.equal(field(mounted.root, 'Nombre').props.modelValue, 'Mi primero')
        editButtons()[1].props.onClick(); await flush()
        field(mounted.root, 'Título').props['onUpdate:modelValue']('Mi anotación'); await flush()
        await button(mounted.root, 'Guardar anotación').props.onClick(); await flush()
        assert.equal(field(mounted.root, 'Título').props.modelValue, 'Mi anotación')
        assert.match(textOf(mounted.root), /Conflicto de revisión/)
        assert.deepEqual(mounted.calls.filter(row => row.method === 'PUT').map(row => row.path), ['planning/courses/3/', 'planning/events/4/'])
    } finally {mounted.close()}
})
