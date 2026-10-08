import test from 'node:test'
import assert from 'node:assert/strict'
import {mountFunctional, button, field, textOf, flush, all} from './functionalComponentHarness.mjs'
const data = {courses: [], meal_plans: [], events: [], can_edit: false, can_manage_absences: false, can_merge_print: false}
const courseMeal = {id: 7, title: 'Sopa', recipe: null, meal_type: {id: 1, name: 'Comida'}, course: null, servings: '4.00', from_date: '2026-10-07T12:00:00Z', to_date: null, note: '', diet_status: 'unknown'}

for (const edition of ['profesional', 'integral']) test(`${edition} Consulta never mounts the native meal-type search`, async () => {
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, path => {
        if (path === 'edition/') return {edition}
        if (path.startsWith('planning/templates/')) return {count: 0, results: []}
        return data
    })
    try {
        assert.equal(all(mounted.root, node => node.type === 'model-select').length, 0, 'disabled native selectors still search on mount and must not be mounted for Consulta')
        assert.equal(field(mounted.root, 'Comida').props.disabled, true)
    } finally {mounted.close()}
})

test('course assignment updates from the authorized server row without background reloads', async () => {
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method, body) => {
        if (path === 'edition/') return {edition: 'profesional'}
        if (path.startsWith('planning/templates/')) return {count: 0, results: []}
        if (path.startsWith('planning/?')) return {...data, can_edit: true, meal_plans: [courseMeal], courses: [{id: 3, name: 'Primero', meal_type: 1, position: 0}]}
        assert.equal(path, 'planning/meal-plans/7/'); assert.equal(method, 'PUT'); assert.deepEqual(body, {course: 3})
        return {...courseMeal, course: 3}
    })
    try {
        assert.equal(all(mounted.root, node => node.type === 'model-select').length, 1)
        await field(mounted.root, 'Tipo de plato').props['onUpdate:modelValue'](3); await flush()
        assert.equal(field(mounted.root, 'Tipo de plato').props.modelValue, 3)
        assert.equal(mounted.calls.filter(row => row.path.startsWith('planning/?')).length, 1, 'a committed assignment must not start requests that a following navigation cancels')
        assert.equal(mounted.calls.filter(row => row.path.startsWith('planning/templates/')).length, 1)
        assert.match(textOf(mounted.root), /Tipo de plato asignado/)
    } finally {mounted.close()}
})

test('applying a template preserves a rejected draft and removes its fields after success', async () => {
    const template = {id: 2, name: 'Semana', weeks: 1, revision: 'a'.repeat(64), entries: []}
    let rejected = true
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method, body) => {
        if (path === 'edition/') return {edition: 'profesional'}
        if (path.startsWith('planning/templates/?')) return {count: 1, results: [template]}
        if (path.startsWith('planning/?')) return {...data, can_edit: true}
        assert.equal(path, 'planning/templates/2/apply/'); assert.equal(method, 'POST'); assert.equal(body.start_date, '2041-06-01')
        if (rejected) throw new Error('Conflicto de revisión')
        return {created_ids: [10], replaced_ids: []}
    })
    try {
        button(mounted.root, 'Aplicar al calendario').props.onClick(); await flush()
        const dialog = all(mounted.root, node => node.type === 'v-dialog')[0]
        assert.equal(all(mounted.root, node => node.props?.label === 'Primer día').length, 1, 'period and application fields must have distinct labels even while the dialog is open')
        const applicationDate = field(dialog, 'Primer día de la plantilla'); assert.ok(applicationDate)
        applicationDate.props['onUpdate:modelValue']('2041-06-01'); await flush()
        await button(dialog, 'Aplicar plantilla').props.onClick(); await flush()
        assert.equal(field(dialog, 'Primer día de la plantilla').props.modelValue, '2041-06-01')
        assert.match(textOf(mounted.root), /Conflicto de revisión/)
        rejected = false
        await button(dialog, 'Aplicar plantilla').props.onClick(); await flush()
        assert.equal(all(mounted.root, node => node.props?.label === 'Primer día').length, 1)
        assert.equal(all(mounted.root, node => node.type === 'v-dialog').length, 0)
    } finally {mounted.close()}
})

test('a pending course assignment blocks another submission and a denial preserves the saved selection', async () => {
    let deny
    const pending = new Promise((_resolve, reject) => {deny = reject})
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method) => {
        if (path === 'edition/') return {edition: 'integral'}
        if (path.startsWith('planning/templates/')) return {count: 0, results: []}
        if (path.startsWith('planning/?')) return {...data, can_edit: true, meal_plans: [courseMeal]}
        assert.equal(path, 'planning/meal-plans/7/'); assert.equal(method, 'PUT'); return pending
    })
    try {
        const assignment = field(mounted.root, 'Tipo de plato').props['onUpdate:modelValue'](3); await flush()
        assert.equal(field(mounted.root, 'Tipo de plato').props.disabled, true)
        await field(mounted.root, 'Tipo de plato').props['onUpdate:modelValue'](4)
        assert.equal(mounted.calls.filter(row => row.method === 'PUT').length, 1)
        deny(new Error('Acceso revocado')); await assignment; await flush()
        assert.equal(field(mounted.root, 'Tipo de plato').props.modelValue, null)
        assert.equal(field(mounted.root, 'Tipo de plato').props.disabled, false)
        assert.match(textOf(mounted.root), /Acceso revocado/)
        assert.equal(mounted.calls.filter(row => row.method === 'GET').length, 3)
    } finally {mounted.close()}
})
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


test('event success is announced only after the updated period finishes loading', async () => {
    let finishPeriod, initial = true
    const pendingPeriod = new Promise(resolve => {finishPeriod = resolve})
    const saved = {id: 9, kind: 'event', title: 'Anotación sintética', member_name: '', start_date: '2026-10-08', end_date: '2026-10-08', note: '', revision: 'a'.repeat(64)}
    const writable = {...data, can_edit: true, can_manage_absences: true}
    const mounted = await mountFunctional('./pages/MenuPlanningPage.vue', {}, (path, method) => {
        if (path === 'edition/') return {edition: 'integral'}
        if (path.startsWith('planning/templates/')) return {count: 0, results: []}
        if (path.startsWith('planning/?')) {if (initial) {initial = false; return writable} return pendingPeriod}
        assert.equal(path, 'planning/events/'); assert.equal(method, 'POST'); return saved
    })
    try {
        field(mounted.root, 'Título').props['onUpdate:modelValue'](saved.title); await flush()
        const saving = button(mounted.root, 'Guardar anotación').props.onClick(); await flush()
        assert.equal(button(mounted.root, 'Guardar anotación').props.disabled, true)
        assert.doesNotMatch(textOf(mounted.root), /Anotación guardada\./)
        finishPeriod({...writable, events: [saved]}); await saving; await flush()
        assert.equal(field(mounted.root, 'Título').props.disabled, false)
        assert.match(textOf(mounted.root), /Anotación guardada\./)
        assert.match(textOf(mounted.root), /Anotación sintética/)
    } finally {mounted.close()}
})
