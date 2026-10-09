import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {stripTypeScriptTypes} from 'node:module'
import {nativeRecipeMembership, nativeRecipeWriteAccess, nativeRecipeWriteMessage} from '../nativeRecipeWriteUi.ts'
import {prepareIngredientAmounts} from '../../utils/ingredient_amounts.ts'
import {component, deferred, settle} from './functionalHarness.mjs'

const membership = (...names) => ({active: true, groups: names.map(name => ({name}))})

for (const group of ['guest', 'user', 'admin']) test(`active native ${group} membership determines recipe writes`, () => {
    assert.equal(nativeRecipeWriteAccess(true, true, true, membership(group)), group === 'guest' ? 'readonly' : 'allowed')
})
test('pending bootstrap never exposes writes or prematurely labels cached Guest as Consulta', () => {
    for (const role of ['guest', 'user', 'admin']) assert.equal(nativeRecipeWriteAccess(true, false, true, membership(role)), 'loading')
    assert.match(nativeRecipeWriteMessage('loading'), /Comprobando/)
    assert.doesNotMatch(nativeRecipeWriteMessage('loading'), /Consulta/)
})
test('unconfirmed, inactive, missing and unauthenticated memberships fail closed', () => {
    for (const [auth, loaded, member] of [[false, true, membership('admin')], [true, false, membership('admin')],
        [true, true, {...membership('admin'), active: false}], [true, true, null], [true, true, membership()],
        [true, true, {groups: [{name: 'admin'}]}], [true, true, {active: true}], [true, true, membership('superuser')]]) {
        assert.equal(nativeRecipeWriteAccess(auth, true, loaded, member), 'unavailable')
    }
})
test('only one active native membership bound to the current Space grants writes', () => {
    const member = {...membership('admin'), space: 7}
    assert.equal(nativeRecipeMembership([member], 7), member)
    assert.equal(nativeRecipeMembership([{...member, active: false}, member], 7), member)
    for (const list of [[member, {...member}], [member, {...member, space: 8}], [{...member, active: false}], [{...member, active: undefined}]]) {
        assert.equal(nativeRecipeMembership(list, 7), null)
        assert.equal(nativeRecipeWriteAccess(true, true, true, nativeRecipeMembership(list, 7)), 'unavailable')
    }
    assert.equal(nativeRecipeMembership([member], 8), null)
    assert.equal(nativeRecipeMembership([member], undefined), null)
})
test('highest active native group remains usable and a subsequent revocation removes writes', () => {
    const member = membership('guest', 'user')
    assert.equal(nativeRecipeWriteAccess(true, true, true, member), 'allowed')
    member.groups = [{name: 'guest'}]
    assert.equal(nativeRecipeWriteAccess(true, true, true, member), 'readonly')
})

function editorSave(recipe, access) {
    const source = readFileSync(new URL('../../components/model_editors/RecipeEditor.vue', import.meta.url), 'utf8')
    const body = source.match(/async function saveObject\(\): Promise<Recipe \| undefined> \{[\s\S]*?\n\}/)?.[0]
    assert.ok(body, 'the shipped recipe save function must exist')
    const code = stripTypeScriptTypes(body)
    const errors = [], saves = []
    const store = {get nativeRecipeWriteAccess() {return access.value}, get canWriteNativeRecipes() {return access.value === 'allowed'}}
    const save = Function('editingObj', 'prepareIngredientAmounts', 'quantityError', 'showQuantityError',
        'saveObjectUnchecked', 'useUserPreferenceStore', 'useMessageStore', 'MessageType', 'nativeRecipeWriteMessage',
        `${code}; return saveObject`)({value: recipe}, prepareIngredientAmounts, {value: ''}, text => errors.push(text),
        async () => {saves.push(structuredClone(recipe)); return recipe}, () => store,
        () => ({addMessage: (...args) => errors.push(args)}), {WARNING: 'warning'}, nativeRecipeWriteMessage)
    return {save, errors, saves}
}
for (const role of ['guest', 'user', 'admin']) test(`shipped editor save respects ${role} before normalizing or posting`, async () => {
    const recipe = {steps: [{ingredients: [{amount: ' 400,500 ' }]}]}
    const before = structuredClone(recipe)
    const access = {value: nativeRecipeWriteAccess(true, true, true, membership(role))}
    const editor = editorSave(recipe, access)
    const result = await editor.save()
    if (role === 'guest') {
        assert.equal(result, undefined)
        assert.deepEqual(recipe, before)
        assert.equal(editor.saves.length, 0)
        assert.match(JSON.stringify(editor.errors), /Modo Consulta.*Cocina o Responsable/)
    } else {
        assert.equal(result, recipe)
        assert.equal(editor.saves.length, 1)
        assert.equal(recipe.steps[0].ingredients[0].amount, '400.5')
        access.value = 'readonly'
        const savedDraft = structuredClone(recipe)
        assert.equal(await editor.save(), undefined)
        assert.deepEqual(recipe, savedDraft)
        assert.equal(editor.saves.length, 1)
    }
})

function importer(access, api = {}, params = {}, updateRecipeImage = async () => ({})) {
    const store = {activeSpace: {}, userSettings: {},
        get nativeRecipeWriteAccess() {return access.value}, get canWriteNativeRecipes() {return access.value === 'allowed'}}
    return component('pages/RecipeImportPage.vue', ['loadRecipeFromUrl', 'loadRecipeFromAiImport', 'appImport',
        'doListImport', 'importFromUrlList', 'createRecipeFromImport', 'loadOrCreateBookmarkletToken', 'aiStepSort',
        'loading', 'importResponse', 'urlListImportedRecipes', 'urlList', 'urlListImportInput', 'selectedAiProvider', 'sourceImportText', 'aiMode'], {
        api, globals: {nativeRecipeWriteMessage, useUserPreferenceStore: () => store,
            useUrlSearchParams: () => params, sourceImportRequest: value => value,
            useFileApi: () => ({updateRecipeImage, doAiImport: async () => api.ai(),
                doAppImport: async () => api.archive(), fileApiLoading: {value: false}}),
            useDjangoUrls: () => ({getFullUrl: path => path}), DateTime: {now: () => ({plus: () => ({toJSDate: () => new Date()})})},
        },
    })
}
test('every shipped native import entry point rejects Guest before requests or draft mutation', async () => {
    let requests = 0
    const request = async () => {requests++; return {}}
    const h = importer({value: 'readonly'}, {apiRecipeFromSourceCreate: request, apiRecipeCreate: request,
        apiAccessTokenList: request, apiAiStepSortCreate: request, ai: request, archive: request}, {url: 'https://example.invalid/shared'})
    const draft = {name: 'Keep draft', steps: [], keywords: []}
    h.exposed.importResponse.value = {recipe: draft}
    h.exposed.urlList.value = ['https://example.invalid/queued']
    h.exposed.urlListImportInput.value = 'https://example.invalid/list'
    h.exposed.selectedAiProvider.value = {id: 7}
    h.exposed.sourceImportText.value = 'Keep source'; h.exposed.aiMode.value = 'text'
    h.hooks.mounted.forEach(fn => fn())
    await h.exposed.loadRecipeFromUrl({url: 'https://example.invalid/source'})
    await h.exposed.loadRecipeFromAiImport(); await h.exposed.appImport(); h.exposed.doListImport()
    await h.exposed.importFromUrlList(); await h.exposed.createRecipeFromImport()
    await h.exposed.loadOrCreateBookmarkletToken(); h.exposed.aiStepSort(7); await settle()
    assert.equal(requests, 0)
    assert.equal(h.exposed.importResponse.value.recipe, draft)
    assert.deepEqual([...h.exposed.urlList.value], ['https://example.invalid/queued'])
    assert.equal(h.exposed.urlListImportInput.value, 'https://example.invalid/list')
    assert.equal(h.exposed.loading.value, false)
    assert.equal(h.messages.length, 8)
    assert(h.messages.every(message => JSON.stringify(message).includes('Modo Consulta')))
})
test('shared import waits for confirmed permissions and runs only once for an operator', async () => {
    const calls = [], access = {value: 'loading'}
    const h = importer(access, {apiRecipeFromSourceCreate: async ({recipeFromSource}) => {calls.push(recipeFromSource); return {}}}, {url: 'https://example.invalid/shared'})
    h.hooks.mounted.forEach(fn => fn()); await settle(); assert.equal(calls.length, 0)
    const permissionWatcher = h.hooks.watchers.find(item => typeof item.source === 'function' && item.source() === false)
    assert.ok(permissionWatcher)
    access.value = 'allowed'; permissionWatcher.fn(true); await settle()
    assert.equal(calls.length, 1); assert.equal(calls[0].url, 'https://example.invalid/shared')
    permissionWatcher.fn(true); h.hooks.mounted.forEach(fn => fn()); await settle(); assert.equal(calls.length, 1)
})

test('bookmarklet creation rechecks membership after its pending token list', async () => {
    const pending = deferred(), access = {value: 'allowed'}; let writes = 0
    const h = importer(access, {apiAccessTokenList: () => pending.promise, apiAccessTokenCreate: async () => {writes++; return {token: 'synthetic'}}})
    const request = h.exposed.loadOrCreateBookmarkletToken(); access.value = 'readonly'; pending.resolve([])
    await request; assert.equal(writes, 0); assert.match(JSON.stringify(h.messages), /Modo Consulta/)
})
test('saved import retains the recipe and opens its read view if access changes before the optional image', async () => {
    const pending = deferred(), access = {value: 'allowed'}; let images = 0
    // Replace the synthetic image dependency with an observable function, using the shipped component.
    const store = {activeSpace: {}, userSettings: {}, get nativeRecipeWriteAccess() {return access.value}, get canWriteNativeRecipes() {return access.value === 'allowed'}}
    const actual = component('pages/RecipeImportPage.vue', ['createRecipeFromImport', 'importResponse', 'editAfterImport', 'loading'], {
        api: {apiRecipeCreate: () => pending.promise}, globals: {nativeRecipeWriteMessage, useUserPreferenceStore: () => store,
            sourceImportRequest: value => value, useFileApi: () => ({updateRecipeImage: async () => {images++}, fileApiLoading: {value: false}}),
            useDjangoUrls: () => ({getFullUrl: path => path})},
    })
    actual.exposed.importResponse.value = {recipe: {keywords: [], imageUrl: 'https://example.invalid/image'}}
    actual.exposed.editAfterImport.value = true
    const request = actual.exposed.createRecipeFromImport(); access.value = 'readonly'; pending.resolve({id: 42})
    await request; assert.equal(images, 0); assert.equal(actual.navigations[0].name, 'RecipeViewPage')
    assert.equal(actual.navigations[0].params.id, 42); assert.equal(actual.exposed.loading.value, false)
    assert.match(JSON.stringify(actual.messages), /Modo Consulta/)
})
function contextMenu(access, api = {}, planningRequest = async () => ({}), updateRecipeImage = async () => ({})) {
    const store = {get nativeRecipeWriteAccess() {return access.value}, get canWriteNativeRecipes() {return access.value === 'allowed'}}
    return component('components/inputs/RecipeContextMenu.vue', ['duplicateRecipe', 'linkVariant', 'duplicateLoading', 'variantCopy'], {
        api, props: {recipe: {id: 1}, canCreateVariant: true}, globals: {useUserPreferenceStore: () => store,
            nativeRecipeWriteMessage, planningRequest, useFileApi: () => ({updateRecipeImage})},
    })
}
test('duplicate creation cannot follow a pending recipe read after access is revoked', async () => {
    const pending = deferred(), access = {value: 'allowed'}; let writes = 0
    const h = contextMenu(access, {apiRecipeRetrieve: () => pending.promise, apiRecipeCreate: async () => {writes++; return {id: 2}}})
    h.exposed.duplicateRecipe(); access.value = 'readonly'; pending.resolve({id: 1, name: 'Original', steps: []}); await settle()
    assert.equal(writes, 0); assert.equal(h.exposed.duplicateLoading.value, false); assert.match(JSON.stringify(h.messages), /Modo Consulta/)
})
test('linked variant cannot PUT after access is revoked during its extras read', async () => {
    const pending = deferred(), access = {value: 'allowed'}, calls = []
    const h = contextMenu(access, {}, (path, method) => {calls.push(method ?? 'GET'); return pending.promise})
    const request = h.exposed.linkVariant(2, 1); access.value = 'readonly'; pending.resolve({revision: 1})
    await assert.rejects(request, /Modo Consulta/); assert.deepEqual(calls, ['GET'])
})
test('created copy remains navigable when later variant/image writes are no longer authorized', async () => {
    const pending = deferred(), access = {value: 'allowed'}; let secondary = 0
    const h = contextMenu(access, {apiRecipeRetrieve: async () => ({id: 1, name: 'Original', steps: [], image: 'synthetic'}), apiRecipeCreate: () => pending.promise},
        async () => {secondary++;return {}}, async () => {secondary++})
    h.exposed.duplicateRecipe(true); await settle(); access.value = 'readonly'; pending.resolve({id: 2}); await settle()
    assert.equal(secondary, 0); assert.equal(h.navigations[0]?.params.id, 2); assert.equal(h.exposed.duplicateLoading.value, false)
    assert.match(JSON.stringify(h.messages), /Modo Consulta/)
})

test('pending batch image completes without a stuck loader or another source request after revocation', async () => {
    const pending = deferred(), access = {value: 'allowed'}; let sources = 0
    const h = importer(access, {apiRecipeFromSourceCreate: async () => {sources++; return {recipe: {name: 'Saved', keywords: []}}}, apiRecipeCreate: async () => ({id: 42})}, {}, () => pending.promise)
    h.exposed.urlList.value = ['second', 'first']
    const request = h.exposed.importFromUrlList(); await settle(); access.value = 'readonly'; pending.resolve({})
    await request; for (const callback of h.timers.values()) await callback()
    assert.equal(sources, 1); assert.equal(h.exposed.loading.value, false)
    assert.equal(h.exposed.urlListImportedRecipes.value[0].id, 42)
    assert.deepEqual([...h.exposed.urlList.value], ['second'])
})
