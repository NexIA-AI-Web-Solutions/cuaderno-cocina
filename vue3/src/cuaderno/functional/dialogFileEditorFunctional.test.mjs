import test from 'node:test'
import assert from 'node:assert/strict'
import {component, deferred, settle, templateEvent} from './functionalHarness.mjs'

const failure = new Error('synthetic request failure')
test('BUGFIX-08: route book change reloads entries rather than keeping old book', async () => {
    const calls = []
    const h = component('pages/BookViewPage.vue', ['props', 'book', 'recipes', 'page'], {props: {bookId: '1'}, api: {apiRecipeBookRetrieve: async ({id}) => {calls.push(id);return {id}}, apiRecipeBookEntryList: async ({book}) => ({results: [{recipeContent: {id: book}}], count: 1, next: null})}})
    h.hooks.mounted.forEach(fn => fn());for (const w of h.hooks.watchers.filter(w => w.options?.immediate)) w.fn(w.source())
    await settle();assert.equal(h.exposed.recipes.value[0].id, 1)
    h.exposed.page.value = 3;h.exposed.props.bookId = '2'
    for (const w of h.hooks.watchers.filter(w => typeof w.source === 'function')) if (w.source() === '2') await w.fn('2', '1')
    await settle();assert.deepEqual(calls, [1, 2]);assert.equal(h.exposed.book.value.id, 2);assert.equal(h.exposed.recipes.value.length, 1);assert.equal(h.exposed.recipes.value[0].id, 2);assert.equal(h.exposed.page.value, 0)
})
test('BUGFIX-09: actual book arrow events stay within populated page boundaries', () => {
    const h = component('pages/BookViewPage.vue', ['page', 'manualItems', 'recipes', 'mdAndUp', 'movePage: typeof movePage === "undefined" ? undefined : movePage'])
    const s = h.exposed;s.manualItems.value = 3;s.recipes.value = [{id: 1}, {id: 2}, {id: 3}]
    const prev = /<v-btn icon="fa-solid fa-chevron-left"[^>]*@click="([^"]+)"/
    const next = /<v-btn icon="fa-solid fa-chevron-right"[^>]*@click="([^"]+)"/
    templateEvent('pages/BookViewPage.vue', prev, s);assert.equal(s.page.value, 0)
    templateEvent('pages/BookViewPage.vue', next, s);assert.equal(s.page.value, 2)
    templateEvent('pages/BookViewPage.vue', next, s);assert.equal(s.page.value, 2)
})
test('BUGFIX-14: retry batch deletion only retries failed items', async () => {
    const calls = [];let fail = true
    const h = component('components/dialogs/BatchDeleteDialog.vue', ['deleteAll', 'itemsToDelete', 'updatedItems', 'failedItems'], {props: {model: 'Food', items: []}, api: {destroy: async id => {calls.push(id);if (id === 2 && fail) throw failure}}})
    h.exposed.itemsToDelete.value = [{id: 1}, {id: 2}];await h.exposed.deleteAll();await settle();fail = false;await h.exposed.deleteAll();await settle()
    assert.deepEqual(calls, [1, 2, 2]);assert.equal(h.exposed.updatedItems.value.length, 2);assert.equal(h.exposed.failedItems.value.length, 0)
})
test('BUGFIX-15: merge waits for its nested automation before completion', async () => {
    const automation = deferred();const h = component('components/dialogs/ModelMergeDialog.vue', ['mergeModel', 'sourceItems', 'target', 'automate', 'loading'], {props: {model: 'Food', source: []}, api: {merge: async () => undefined, apiAutomationCreate: () => automation.promise, model: {mergeAutomation: 'FOOD_REPLACE'}}})
    h.exposed.sourceItems.value = [{id: 1, name: 'source'}];h.exposed.target.value = {id: 2, name: 'target'};h.exposed.automate.value = true;h.exposed.mergeModel();await settle()
    assert.equal(h.exposed.loading.value, true);assert.equal(h.messages.filter(x => x[0] === 'emit').length, 0)
    automation.resolve({id: 4});await settle();assert.equal(h.exposed.loading.value, false);assert.equal(h.messages.filter(x => x[0] === 'emit').length, 1)
})
test('BUGFIX-16: reopening merge clears previous target and result markers', () => {
    const h = component('components/dialogs/ModelMergeDialog.vue', ['dialog', 'sourceItems', 'target', 'updatedItems', 'failedItems'], {props: {model: 'Food', source: [{id: 3}]}})
    h.exposed.target.value = {id: 2};h.exposed.updatedItems.value = [{id: 1}];h.exposed.failedItems.value = [{id: 2}]
    const watcher = h.hooks.watchers.find(w => w.source === h.exposed.dialog);watcher.fn(true, false)
    assert.equal(h.exposed.target.value, null);assert.equal(h.exposed.updatedItems.value.length, 0);assert.equal(h.exposed.failedItems.value.length, 0);assert.equal(h.exposed.sourceItems.value[0].id, 3)
})
test('ERRORFIX-18: failed merge is failed rather than falsely updated', async () => {
    const h = component('components/dialogs/ModelMergeDialog.vue', ['mergeModel', 'sourceItems', 'target', 'updatedItems', 'failedItems', 'loading'], {props: {model: 'Food', source: []}, api: {merge: () => Promise.reject(failure)}})
    h.exposed.sourceItems.value = [{id: 1}];h.exposed.target.value = {id: 2};await h.exposed.mergeModel();await settle()
    assert.equal(h.exposed.updatedItems.value.length, 0);assert.equal(h.exposed.failedItems.value[0].id, 1);assert.equal(h.exposed.loading.value, false)
})
function fileApi(response) {
    const h = component('composables/useFileApi.ts', ['useFileApi'], {globals: {useDjangoUrls: () => ({getDjangoUrl: path => '/cuaderno-cocina/' + path}), csrfHeadersForUrl: () => ({}), fetch: async () => response,
        ResponseError: class extends Error {}, RecipeImageFromJSON: value => value, RecipeFromSourceResponseFromJSON: value => value, UserFileFromJSON: value => value}})
    return h.exposed.useFileApi()
}
test('ERRORFIX-08: rejected image HTTP cannot become a successful image result', async () => {
    const api = fileApi({ok: false, json: async () => ({detail: 'synthetic validation'})})
    await assert.rejects(api.updateRecipeImage(1, null));assert.equal(api.fileApiLoading.value, false)
})
test('ERRORFIX-09: failed or invalid archive HTTP cannot produce a pollable import ID', async () => {
    for (const response of [{ok: false, json: async () => ({import_id: 1})}, {ok: true, json: async () => ({})}, {ok: true, json: async () => ({import_id: '1'})}]) {
        const api = fileApi(response);await assert.rejects(api.doAppImport([], 'DEFAULT', false));assert.equal(api.fileApiLoading.value, false)
    }
})
function editor(api, options = {}) {
    const h = component('composables/useModelEditorFunctions.ts', ['useModelEditorFunctions'], {api, globals: {getNestedProperty: (obj, key) => obj[key], ResponseError: class extends Error {}}})
    const s = h.exposed.useModelEditorFunctions('Recipe', () => {});h.hooks.beforeMount.forEach(fn => fn());return {h, s, setup: item => s.setupState(item, undefined, options)}
}
test('ERRORFIX-16: failed create and update retain dirty edits and return no saved model', async () => {
    for (const item of [{name: 'new'}, {id: 1, name: 'changed'}]) {
        const {s, setup} = editor({create: () => Promise.reject(failure), update: () => Promise.reject(failure), getLabel: item => item.name})
        await setup(item);s.editingObjChanged.value = true;const result = await s.saveObject()
        assert.equal(result, undefined);assert.equal(s.editingObj.value.name, item.name);assert.equal(s.editingObjChanged.value, true);assert.equal(s.loading.value, false)
    }
})
test('ERRORFIX-16 integration: actual mobile save-and-view event stays on failed recipe edits', async () => {
    const {s, setup} = editor({update: () => Promise.reject(failure), getLabel: item => item.name});await setup({id: 1, name: 'changed'});s.editingObjChanged.value = true
    const h = component('pages/ModelEditPage.vue', ['modelEditorFunctions', 'saveAndView: typeof saveAndView === "undefined" ? undefined : saveAndView', 'router', 'props'], {props: {model: 'Recipe', id: '1'}})
    h.exposed.modelEditorFunctions.value = s
    await templateEvent('pages/ModelEditPage.vue', /<v-btn key="1" color="info"[^>]*@click="([^"]+)"/, h.exposed);await settle()
    assert.equal(h.navigations.length, 0);assert.equal(s.editingObjChanged.value, true)
})
test('ERRORFIX-17: rejected and synchronously thrown pre-save hook clear loading without discarding changes', async () => {
    for (const callback of [() => Promise.reject(failure), () => {throw failure}]) {
        let writes = 0;const {s, setup, h} = editor({update: async () => {writes++;return {id: 1}}, getLabel: item => item.name}, {onBeforeSave: callback})
        await setup({id: 1, name: 'changed'});s.editingObjChanged.value = true
        await assert.doesNotReject(s.saveObject());assert.equal(writes, 0);assert.equal(s.loading.value, false);assert.equal(s.editingObjChanged.value, true);assert.equal(h.messages.length, 1)
    }
})
