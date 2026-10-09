import test from 'node:test'
import assert from 'node:assert/strict'
import {component, deferred, settle} from './functionalHarness.mjs'

function load(api = {}, extra = {}) {
    const h = component('pages/RecipeImportPage.vue', ['loadRecipeFromUrl', 'loadRecipeFromAiImport', 'appImport', 'recLoadImportLog', 'createRecipeFromImport', 'importFromUrlList', 'loadOrCreateBookmarkletToken', 'loading', 'importResponse', 'stepper', 'urlList', 'urlListImportInput', 'urlListImportedRecipes', 'selectedAiProvider', 'sourceImportText', 'aiMode', 'importUrl', 'importType'], {
        api, globals: {
            sourceImportRequest: value => value,
            useFileApi: () => ({updateRecipeImage: async () => ({}), doAiImport: async () => ({}), doAppImport: async () => 1, fileApiLoading: {value: false}}),
            useDjangoUrls: () => ({getFullUrl: path => path}), DateTime: {now: () => ({plus: () => ({toJSDate: () => new Date()})})},
            ...extra,
        },
    })
    h.store.canWriteNativeRecipes = true
    h.store.nativeRecipeWriteAccess = 'allowed'
    return h
}
test('BUGFIX-17: unmount cancels import log polling', async () => {
    let calls = 0;const h = load({apiImportLogRetrieve: async () => {calls++;return {running: true}}})
    h.exposed.recLoadImportLog(1);await settle();assert.equal(calls, 1)
    h.hooks.unmounted.forEach(fn => fn());for (const callback of [...h.timers.values()]) callback()
    await settle();assert.equal(calls, 1);assert.equal(h.timers.size, 0)
})
test('BUGFIX-18: shared url and text choose one preview request', async () => {
    const calls = [];const h = load({apiAccessTokenList: async () => [{scope: 'bookmarklet', token: 'synthetic'}], apiRecipeFromSourceCreate: async ({recipeFromSource}) => {calls.push(recipeFromSource);return {}}}, {useUrlSearchParams: () => ({url: 'https://example.invalid/recipe', text: 'shared text'})})
    h.hooks.mounted.forEach(fn => fn());await settle();assert.equal(calls.length, 1);assert.equal(calls[0].url, 'https://example.invalid/recipe')
})
test('BUGFIX-20: latest import preview survives reversed requests', async () => {
    const a = deferred(), b = deferred();let n = 0;const h = load({apiRecipeFromSourceCreate: () => ++n === 1 ? a.promise : b.promise})
    h.exposed.loadRecipeFromUrl({url: 'a'});h.exposed.loadRecipeFromUrl({url: 'b'})
    b.resolve({recipe: {name: 'B'}});await settle();a.resolve({recipe: {name: 'A'}});await settle()
    assert.equal(h.exposed.importResponse.value.recipe.name, 'B')
})
test('ERRORFIX-01: network and non-JSON preview errors remain recoverable', async () => {
    for (const error of [new TypeError('synthetic offline'), {response: {json: () => Promise.reject(new SyntaxError('synthetic html'))}}]) {
        const h = load({apiRecipeFromSourceCreate: () => Promise.reject(error)});await h.exposed.loadRecipeFromUrl({url: 'synthetic'});await settle()
        assert.equal(h.exposed.loading.value, false);assert.equal(h.messages.length, 1)
    }
})
test('ERRORFIX-02: rejected AI import clears loading and retains input', async () => {
    const h = load({}, {useFileApi: () => ({doAiImport: () => Promise.reject(new Error('synthetic'))})})
    h.exposed.aiMode.value = 'text';h.exposed.sourceImportText.value = 'ingredients';h.exposed.selectedAiProvider.value = {id: 1}
    await h.exposed.loadRecipeFromAiImport();await settle();assert.equal(h.exposed.loading.value, false);assert.equal(h.exposed.sourceImportText.value, 'ingredients')
})
test('ERRORFIX-03: failed image after saved recipe still opens the saved recipe', async () => {
    let created = 0;const h = load({apiRecipeCreate: async () => {created++;return {id: 42}}}, {useFileApi: () => ({updateRecipeImage: () => Promise.reject(new Error('synthetic image'))})})
    h.exposed.importResponse.value = {recipe: {keywords: []}};await h.exposed.createRecipeFromImport();await settle()
    assert.equal(created, 1);assert.equal(h.navigations[0]?.params.id, 42);assert.equal(h.messages.length, 1);assert.equal(h.exposed.loading.value, false)
})
test('ERRORFIX-04: batch image failure preserves saved recipe and actually imports next URL', async () => {
    const sources = [], created = [];const h = load({apiRecipeFromSourceCreate: async ({recipeFromSource}) => {sources.push(recipeFromSource.url);return {recipe: {name: recipeFromSource.url}}}, apiRecipeCreate: async ({recipe}) => {created.push(recipe.name);return {id: created.length}}}, {useFileApi: () => ({updateRecipeImage: () => Promise.reject(new Error('synthetic image'))})})
    h.exposed.urlList.value = ['second', 'first'];await h.exposed.importFromUrlList();await settle()
    assert.equal(h.exposed.urlListImportedRecipes.value.length, 1);assert.equal(h.timers.size, 1)
    const [id, callback] = h.timers.entries().next().value;h.timers.delete(id);await callback();await settle()
    assert.deepEqual(sources, ['first', 'second']);assert.deepEqual(created, ['first', 'second']);assert.equal(h.exposed.urlListImportedRecipes.value.length, 2)
})
test('ERRORFIX-05: batch network failure keeps failed URL and clears loading', async () => {
    const h = load({apiRecipeFromSourceCreate: () => Promise.reject(new TypeError('synthetic offline'))})
    h.exposed.urlList.value = ['second', 'first'];h.exposed.loading.value = true;await h.exposed.importFromUrlList();await settle()
    assert.equal(h.exposed.urlListImportInput.value, 'first\nsecond');assert.equal(h.exposed.stepper.value, 'url_list_input');assert.equal(h.exposed.loading.value, false);assert.equal(h.messages.length, 1)
})
test('ERRORFIX-06: batch empty source cannot stall the queue', async () => {
    const h = load({apiRecipeFromSourceCreate: async () => ({})});h.exposed.urlList.value = ['first'];h.exposed.loading.value = true
    await h.exposed.importFromUrlList();await settle();assert.equal(h.exposed.loading.value, false);assert.equal(h.exposed.stepper.value, 'url_list_input');assert.equal(h.messages.length, 1)
})
test('ERRORFIX-07: archive rejection keeps files and avoids polling', async () => {
    let polls = 0;const h = load({apiImportLogRetrieve: () => {polls++;return Promise.resolve({})}}, {useFileApi: () => ({doAppImport: () => Promise.reject(new Error('synthetic archive'))})})
    await h.exposed.appImport();await settle();assert.equal(polls, 0);assert.equal(h.messages.length, 1);assert.equal(h.exposed.stepper.value, 'type')
})
test('ERRORFIX-19: bookmarklet list/create rejection is caught', async () => {
    for (const api of [{apiAccessTokenList: () => Promise.reject(new Error('synthetic list'))}, {apiAccessTokenList: async () => [], apiAccessTokenCreate: () => Promise.reject(new Error('synthetic create'))}]) {
        const h = load(api);await h.exposed.loadOrCreateBookmarkletToken();await settle();assert.equal(h.messages.length, 1)
    }
})

test('BUGFIX-22: mounting importer performs no access-token write; explicit bookmarklet selection initializes it', async () => {
    let lists = 0, creates = 0
    const h = load({apiAccessTokenList: async () => {lists++;return []}, apiAccessTokenCreate: async () => {creates++;return {token: 'synthetic'}}})
    h.hooks.mounted.forEach(fn => fn());await settle();assert.equal(lists, 0);assert.equal(creates, 0)
    h.exposed.importType.value = 'bookmarklet'
    const watcher = h.hooks.watchers.find(w => w.source === h.exposed.importType)
    assert.ok(watcher, 'native watcher for explicit type choice');await watcher.fn('bookmarklet', 'url');await settle();assert.equal(lists, 1);assert.equal(creates, 1)
})
