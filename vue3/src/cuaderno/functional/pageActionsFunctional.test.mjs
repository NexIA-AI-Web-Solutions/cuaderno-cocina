import test from 'node:test'
import assert from 'node:assert/strict'
import {component, deferred, settle, templateEvent} from './functionalHarness.mjs'
import {normalizeIngredientAmount} from '../../utils/ingredient_amounts.ts'

const error = new Error('synthetic request failure')
test('BUGFIX-05: saved filters replace omitted fields and query', () => {
    const {exposed: s} = component('pages/SearchPage.vue', ['loadSelectedCustomFilter', 'filters', 'query', 'selectedCustomFilter'])
    s.query.value = 'old';s.filters.value = {foods: {id: 'foods', default: [], modelValue: [1], enabled: true}, rating: {id: 'rating', default: null, modelValue: 2, enabled: true}}
    s.selectedCustomFilter.value = {search: '{"version":"2","rating":4}'};s.loadSelectedCustomFilter()
    assert.equal(s.query.value, '');assert.equal(s.filters.value.foods.modelValue.length, 0);assert.equal(s.filters.value.foods.enabled, false);assert.equal(s.filters.value.rating.modelValue, 4)
})
test('ERRORFIX-11: malformed saved filters report an error and retain active state', () => {
    const h = component('pages/SearchPage.vue', ['loadSelectedCustomFilter', 'filters', 'query', 'selectedCustomFilter']);const s = h.exposed
    s.query.value = 'keep';s.filters.value = {foods: {id: 'foods', default: [], modelValue: [1], enabled: true}}
    for (const search of ['{invalid', 'null', '[]']) {s.selectedCustomFilter.value = {search};assert.doesNotThrow(() => s.loadSelectedCustomFilter())}
    assert.equal(s.query.value, 'keep');assert.equal(s.filters.value.foods.modelValue[0], 1);assert.equal(h.messages.length, 3)
})
test('BUGFIX-19: obsolete search cannot clear current loading or scroll', async () => {
    const a = deferred(), b = deferred();let n = 0, scrolls = 0
    const h = component('pages/SearchPage.vue', ['searchRecipes', 'filters', 'loading', 'recipes'], {api: {apiRecipeList: () => ++n === 1 ? a.promise : b.promise}, globals: {window: {scrollTo() {scrolls++}}}})
    h.exposed.filters.value = {};h.exposed.searchRecipes({page: 1});h.exposed.searchRecipes({page: 2})
    a.reject(Object.assign(new Error('cancelled'), {name: 'AbortError'}));await settle()
    assert.equal(h.exposed.loading.value, true);assert.equal(scrolls, 0)
    b.resolve({results: [{id: 2}], count: 1});await settle();assert.equal(h.exposed.loading.value, false)
})
test('BUGFIX-06: entering a book name narrows displayed books', async () => {
    const h = component('pages/BooksPage.vue', ['loadBooks', 'books', 'bookQuery: typeof bookQuery === "undefined" ? undefined : bookQuery', 'visibleBooks: typeof visibleBooks === "undefined" ? undefined : visibleBooks'], {api: {apiRecipeBookList: async () => ({results: [{id: 1, name: 'Sopas'}, {id: 2, name: 'Postres'}], next: null})}})
    h.exposed.loadBooks();await settle();if (h.exposed.bookQuery) h.exposed.bookQuery.value = 'post'
    assert.equal((h.exposed.visibleBooks ?? h.exposed.books).value.length, 1)
    assert.equal((h.exposed.visibleBooks ?? h.exposed.books).value[0].id, 2)
})
test('BUGFIX-07: books after the first API page remain reachable', async () => {
    const h = component('pages/BooksPage.vue', ['loadBooks', 'books'], {api: {apiRecipeBookList: async ({page} = {}) => ({results: [{id: page === 2 ? 2 : 1}], next: page === 2 ? null : '/next/'})}})
    await h.exposed.loadBooks();await settle();assert.equal(h.exposed.books.value.length, 2)
})
test('BUGFIX-13: latest ingredient filter survives reversed responses', async () => {
    const a = deferred(), b = deferred();let n = 0
    const {exposed: s} = component('pages/IngredientEditorPage.vue', ['loadItems', 'selectedFood', 'items'], {api: {apiIngredientList: () => ++n === 1 ? a.promise : b.promise}})
    s.selectedFood.value = {id: 1};s.loadItems({page: 1, itemsPerPage: 25});s.selectedFood.value = {id: 2};s.loadItems({page: 1, itemsPerPage: 25})
    b.resolve({results: [{id: 2}], count: 1});await settle();a.resolve({results: [{id: 1}], count: 1});await settle();assert.equal(s.items.value[0].id, 2)
})
test('ERRORFIX-12: failed ingredient save retains edits and dirty state', async () => {
    const {exposed: s} = component('pages/IngredientEditorPage.vue', ['updateIngredient', 'items'], {
        api: {apiIngredientUpdate: () => Promise.reject(error)}, globals: {normalizeIngredientAmount},
    })
    const item = {id: 1, amount: '3.5', changed: true, loading: false};s.items.value = [item];await s.updateIngredient(item)
    assert.equal(item.changed, true);assert.equal(item.amount, '3.5');assert.equal(item.loading, false)
})
test('BUGFIX-10: property deletion clears its persisted ID', async () => {
    const {exposed: s} = component('pages/PropertyEditorPage.vue', ['deleteFoodProperty'], {api: {apiPropertyDestroy: async () => undefined}})
    const p = {id: 7, propertyAmount: 1}, i = {loading: false};s.deleteFoodProperty(p, i);await settle()
    assert.equal(p.id, undefined);assert.equal(p.propertyAmount, null)
})
test('BUGFIX-11: saving properties preserves server-assigned IDs', async () => {
    const {exposed: s} = component('pages/PropertyEditorPage.vue', ['updateFood', 'propertyTypes'], {api: {apiFoodPartialUpdate: async () => ({id: 1, properties: [{id: 8, propertyAmount: 3, propertyType: {id: 2}}]})}})
    s.propertyTypes.value = [{id: 1}, {id: 2}]
    const i = {food: {id: 1, properties: [{propertyAmount: 3, propertyType: {id: 2}}]}};s.updateFood(i);await settle()
    assert.equal(i.food.properties.length, 2);assert.equal(i.food.properties[0].propertyType.id, 1);assert.equal(i.food.properties[0].propertyAmount, null);assert.equal(i.food.properties[1].id, 8)
})
test('BUGFIX-12: every property type page is editable', async () => {
    const {exposed: s} = component('pages/PropertyEditorPage.vue', ['loadPropertyTypes', 'propertyTypes'], {api: {apiPropertyTypeList: async ({page} = {}) => ({results: [{id: page === 2 ? 2 : 1}], next: page === 2 ? null : '/next/'})}})
    await s.loadPropertyTypes();await settle();assert.equal(s.propertyTypes.value.length, 2)
})
test('ERRORFIX-13: failed welcome completion stays put with unpersisted flags', async () => {
    const h = component('pages/WelcomePage.vue', ['finishWelcome', 'space', 'loading'], {api: {apiSpacePartialUpdate: () => Promise.reject(error)}})
    h.exposed.space.value = {id: 1, spaceSetupCompleted: false, householdSetupCompleted: false};await h.exposed.finishWelcome();await settle()
    assert.equal(h.navigations.length, 0);assert.equal(h.exposed.space.value.spaceSetupCompleted, false);assert.equal(h.exposed.loading.value, false)
})
test('ERRORFIX-14: failed user settings do not advance welcome', async () => {
    const h = component('pages/WelcomePage.vue', ['updateSpaceAndUserSettings', 'space', 'stepper', 'loading'], {api: {apiSpacePartialUpdate: async () => ({id: 1})}})
    h.store.updateUserSettings = () => Promise.reject(error);h.exposed.space.value = {id: 1};await h.exposed.updateSpaceAndUserSettings();await settle()
    assert.equal(h.exposed.stepper.value, '1');assert.equal(h.exposed.loading.value, false)
})
test('ERRORFIX-15: failed household skip does not navigate or mark completed', async () => {
    const h = component('pages/HouseholdPage.vue', ['skipHouseholdSetup', 'loading'], {api: {apiSpacePartialUpdate: () => Promise.reject(error)}})
    h.store.activeSpace = {id: 1, householdSetupCompleted: false};await h.exposed.skipHouseholdSetup();await settle()
    assert.equal(h.navigations.length, 0);assert.equal(h.store.activeSpace.householdSetupCompleted, false);assert.equal(h.exposed.loading.value, false)
})
test('ERRORFIX-20: missing household context does not leave an endless spinner', async () => {
    const h = component('pages/HouseholdPage.vue', ['createAndJoinHousehold', 'loading'])
    await h.exposed.createAndJoinHousehold();assert.equal(h.exposed.loading.value, false);assert.equal(h.messages.length, 1)
})

test('Supplementary PropertyType creation: native dialog create adds editable cell without losing unsaved values', () => {
    const h = component('pages/PropertyEditorPage.vue', ['propertyTypes', 'ingredients', 'appendPropertyType: typeof appendPropertyType === "undefined" ? undefined : appendPropertyType'])
    h.exposed.propertyTypes.value = [{id: 1}]
    h.exposed.ingredients.value = new Map([[1, {food: {id: 7, properties: [{id: 9, propertyType: {id: 1}, propertyAmount: 3.5}]}}]])
    templateEvent('pages/PropertyEditorPage.vue', /<model-edit-dialog model="PropertyType"[^>]*@create="([^"]+)"/, {...h.exposed, $event: {id: 2}})
    const properties = h.exposed.ingredients.value.get(1).food.properties
    assert.equal(properties.length, 2);assert.equal(properties[0].id, 9);assert.equal(properties[0].propertyAmount, 3.5);assert.equal(properties[1].propertyType.id, 2);assert.equal(properties[1].propertyAmount, null)
})
