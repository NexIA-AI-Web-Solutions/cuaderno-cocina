import test from 'node:test'
import assert from 'node:assert/strict'
import {mountFunctional, button, field, textOf, flush} from './functionalComponentHarness.mjs'

const slugs = ['celiacos','colesterol','diabetes','hiposodica','gastrica','fibra','sinfructosa','sinlactosa']
const extras = (canEdit = false) => ({recipe_id: 9, revision: 'a'.repeat(64), can_edit: canEdit, is_favorite: false, gallery: [], variant_of: null, variants: [], diets: slugs.map(slug => ({slug, label: slug, status: 'unknown', note: ''}))})
test('Consulta can change only their personal favorite and sees all unknown declarations', async () => {
    const mounted = await mountFunctional('./components/RecipeExtrasPanel.vue', {recipeId: 9}, (path, method, body) => {
        if (path === 'recipes/9/extras/' && method === 'GET') return extras()
        assert.equal(path, 'recipes/9/favorite/'); assert.equal(method, 'PUT'); assert.deepEqual(body, {favorite: true}); return {recipe_id: 9, is_favorite: true}
    })
    try {
        assert.equal(button(mounted.root, 'Guardar declaraciones'), undefined)
        assert.equal(field(mounted.root, 'Añadir foto (hasta 5 MiB)'), undefined)
        assert.equal((textOf(mounted.root).match(/No declarado/g) || []).length, 9)
        await button(mounted.root, 'Guardar en favoritas').props.onClick(); await flush()
        assert.ok(button(mounted.root, 'En mis favoritas'))
        assert.deepEqual(mounted.calls.map(row => row.method), ['GET', 'PUT'])
    } finally {mounted.close()}
})
test('a rejected save preserves manual diet edits and the exact revision submitted', async () => {
    const mounted = await mountFunctional('./components/RecipeExtrasPanel.vue', {recipeId: 9}, (path, method, body) => {
        if (method === 'GET') return extras(true)
        assert.equal(body.revision, 'a'.repeat(64)); assert.equal(body.diets.length, 8); assert.equal(body.diets[0].status, 'unsuitable'); assert.equal(body.diets[0].note, 'Revisar proveedor'); throw new Error('Conflicto: actualiza antes de guardar')
    })
    try {
        field(mounted.root, 'Declaración: celiacos').props['onUpdate:modelValue']('unsuitable')
        field(mounted.root, 'Nota: celiacos').props['onUpdate:modelValue']('Revisar proveedor'); await flush()
        await button(mounted.root, 'Guardar declaraciones').props.onClick(); await flush()
        assert.match(textOf(mounted.root), /Conflicto/)
        assert.equal(field(mounted.root, 'Nota: celiacos').props.modelValue, 'Revisar proveedor')
        assert.equal(field(mounted.root, 'Declaración: celiacos').props.modelValue, 'unsuitable')
    } finally {mounted.close()}
})
test('gallery response updates revision without discarding unsaved diet notes', async () => {
    const mounted = await mountFunctional('./components/RecipeExtrasPanel.vue', {recipeId: 9}, (_path, method, body) => {
        if (method === 'GET') return extras(true)
        assert.equal(body.revision, 'b'.repeat(64)); assert.equal(body.diets[0].note, 'Borrador sin guardar')
        return {...extras(true), revision: 'c'.repeat(64), diets: body.diets.map(diet => ({...diet, label: diet.slug}))}
    }, async (id, file, caption) => {
        assert.equal(id, 9); assert.equal(file.name, 'foto.png'); assert.equal(caption, 'Presentación'); return {...extras(true), revision: 'b'.repeat(64)}
    })
    try {
        field(mounted.root, 'Nota: celiacos').props['onUpdate:modelValue']('Borrador sin guardar')
        field(mounted.root, 'Añadir foto (hasta 5 MiB)').props['onUpdate:modelValue']({name: 'foto.png'})
        field(mounted.root, 'Descripción de la foto').props['onUpdate:modelValue']('Presentación'); await flush()
        await button(mounted.root, 'Añadir foto').props.onClick(); await flush()
        assert.equal(field(mounted.root, 'Nota: celiacos').props.modelValue, 'Borrador sin guardar')
        assert.equal(field(mounted.root, 'Añadir foto (hasta 5 MiB)').props.modelValue, null)
        await button(mounted.root, 'Guardar declaraciones').props.onClick(); await flush()
        assert.equal(mounted.calls.filter(row => row.method === 'PUT').length, 1)
    } finally {mounted.close()}
})

test('a concurrent remote diet change returned by gallery cannot silently rebase unsaved declarations', async () => {
    let readCount = 0
    const remote = extras(true); remote.revision = 'b'.repeat(64); remote.diets[0].status = 'unsuitable'; remote.diets[0].note = 'Cambio de otra persona'
    const mounted = await mountFunctional('./components/RecipeExtrasPanel.vue', {recipeId: 9}, (_path, method) => {
        assert.equal(method, 'GET'); return ++readCount === 1 ? extras(true) : remote
    }, async () => remote)
    try {
        field(mounted.root, 'Nota: celiacos').props['onUpdate:modelValue']('Mi borrador')
        field(mounted.root, 'Añadir foto (hasta 5 MiB)').props['onUpdate:modelValue']({name: 'foto.png'}); await flush()
        await button(mounted.root, 'Añadir foto').props.onClick(); await flush()
        assert.equal(field(mounted.root, 'Nota: celiacos').props.modelValue, 'Mi borrador')
        assert.match(textOf(mounted.root), /Otra persona ha cambiado las declaraciones/)
        const save = button(mounted.root, 'Guardar declaraciones'); assert.equal(save.props.disabled, true)
        await save.props.onClick(); await flush()
        assert.equal(mounted.calls.filter(row => row.method !== 'GET').length, 0)
        await button(mounted.root, 'Descartar cambios y actualizar').props.onClick(); await flush()
        assert.equal(field(mounted.root, 'Nota: celiacos').props.modelValue, 'Cambio de otra persona')
        assert.equal(field(mounted.root, 'Declaración: celiacos').props.modelValue, 'unsuitable')
        assert.equal(button(mounted.root, 'Guardar declaraciones').props.disabled, false)
    } finally {mounted.close()}
})
