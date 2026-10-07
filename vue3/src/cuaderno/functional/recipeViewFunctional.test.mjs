import test from 'node:test'
import assert from 'node:assert/strict'
import {component, deferred, settle} from './functionalHarness.mjs'

function view(api, authenticated = false) {
    const store = {isAuthenticated: authenticated, isPrintMode: false}
    const h = component('pages/RecipeViewPage.vue', ['recipe', 'refreshData'], {props: {id: '9'}, api,
        globals: {provide() {}, RECIPE_SHARE_TOKEN_KEY: Symbol('share'), useUserPreferenceStore: () => store}})
    return {...h, preferences: store}
}
function authenticationChanged(h) {
    const watcher = h.hooks.watchers.find(row => typeof row.source === 'function' && Array.isArray(row.source()))
    assert.ok(watcher, 'recipe and authentication must both trigger view logging')
    watcher.fn()
}

test('a deep link logs once when authentication finishes after the recipe', async () => {
    const logs = []
    const h = view({apiRecipeRetrieve: async () => ({id: 9, name: 'Receta'}), apiViewLogCreate: async body => logs.push(body)})
    h.exposed.refreshData('9'); await settle()
    assert.equal(logs.length, 0)
    h.preferences.isAuthenticated = true; authenticationChanged(h); await settle()
    assert.equal(logs.length, 1); assert.equal(logs[0].viewLog.recipe, 9)
    authenticationChanged(h); await settle(); assert.equal(logs.length, 1)
})

test('a view-log error is handled without losing the loaded recipe', async () => {
    const h = view({apiRecipeRetrieve: async () => ({id: 9, name: 'Receta'}), apiViewLogCreate: async () => {throw new Error('Sin conexión')}}, true)
    h.exposed.refreshData('9'); await settle(); authenticationChanged(h); await settle()
    assert.equal(h.exposed.recipe.value.name, 'Receta')
    assert.equal(h.messages.length, 1)
})

test('a slow response from the previous route cannot replace the current recipe', async () => {
    const first = deferred(), second = deferred()
    const h = view({apiRecipeRetrieve: ({id}) => id === 9 ? first.promise : second.promise})
    h.exposed.refreshData('9'); h.exposed.refreshData('10')
    second.resolve({id: 10, name: 'Actual'}); await settle()
    first.resolve({id: 9, name: 'Anterior'}); await settle()
    assert.equal(h.exposed.recipe.value.id, 10)
})

test('a network error without an HTTP response reaches the user error handler', async () => {
    const h = view({apiRecipeRetrieve: async () => {throw new Error('Sin conexión')}})
    h.exposed.refreshData('9'); await settle()
    assert.equal(h.messages.length, 1)
})

test('leaving a recipe invalidates its unfinished load', async () => {
    const pending = deferred()
    const h = view({apiRecipeRetrieve: () => pending.promise})
    h.exposed.refreshData('9')
    for (const hook of h.hooks.unmounted) hook()
    pending.resolve({id: 9, name: 'Página anterior'}); await settle()
    assert.equal(h.exposed.recipe.value.id, undefined)
})
