import test from 'node:test'
import assert from 'node:assert/strict'
import {component, deferred, settle} from './functionalHarness.mjs'

function view(api) {
    return component('pages/RecipeViewPage.vue', ['recipe', 'refreshData', 'loadingRecipe', 'recipeLoadError'], {
        props: {id: '9'}, api, globals: {provide() {}, RECIPE_SHARE_TOKEN_KEY: Symbol('share')},
    })
}
test('missing recipe becomes an explicit unavailable state and retry can recover', async () => {
    let missing = true
    const h = view({apiRecipeRetrieve: async () => {if (missing) throw {response: {status: 404}};return {id: 9, name: 'Receta recuperada'}}})
    h.exposed.refreshData('9');assert.equal(h.exposed.loadingRecipe.value, true);await settle()
    assert.equal(h.exposed.loadingRecipe.value, false);assert.equal(h.exposed.recipeLoadError.value, 'unavailable')
    assert.equal(h.messages.length, 0, 'unavailable recipe uses its contextual message rather than a technical error toast')
    missing = false;h.exposed.refreshData('9');await settle()
    assert.equal(h.exposed.recipeLoadError.value, null);assert.equal(h.exposed.recipe.value.name, 'Receta recuperada')
})
test('invalid recipe identity never sends an API request or remains loading', async () => {
    const h = view({apiRecipeRetrieve: () => assert.fail('Invalid id must not request')})
    for (const id of ['missing', '0', '-2', '1.5']) {
        h.exposed.refreshData(id);await settle()
        assert.equal(h.exposed.loadingRecipe.value, false);assert.equal(h.exposed.recipeLoadError.value, 'unavailable')
    }
})
test('obsolete failure cannot erase the newer recipe or its settled state', async () => {
    const first = deferred(), next = deferred()
    const h = view({apiRecipeRetrieve: ({id}) => id === 9 ? first.promise : next.promise})
    h.exposed.refreshData('9');h.exposed.refreshData('10');next.resolve({id: 10, name: 'Actual'});await settle()
    first.reject({response: {status: 404}});await settle()
    assert.equal(h.exposed.recipe.value.id, 10);assert.equal(h.exposed.recipeLoadError.value, null);assert.equal(h.exposed.loadingRecipe.value, false)
})
test('network failure reports a recoverable load error', async () => {
    const h = view({apiRecipeRetrieve: async () => {throw Error('Offline')}})
    h.exposed.refreshData('9');await settle()
    assert.equal(h.exposed.recipeLoadError.value, 'failed');assert.equal(h.exposed.loadingRecipe.value, false)
})
