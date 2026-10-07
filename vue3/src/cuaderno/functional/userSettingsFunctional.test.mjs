import test from 'node:test'
import assert from 'node:assert/strict'
import {component, settle} from './functionalHarness.mjs'

function loadStore() {
    const h = component('stores/UserPreferenceStore.ts', ['useUserPreferenceStore'], {api: {apiUserPreferencePartialUpdate: () => Promise.reject(new Error('synthetic settings'))}, globals: {
        defineStore: (_name, setup) => setup, cuadernoStorageKey: key => key,
        useStorage: (_key, value) => ({value}), localStorage: {}, useTheme: () => ({change() {}}), useRoute: () => ({query: {}}), ShoppingGroupingOptions: {CATEGORY: 'category'},
    }})
    const store = h.exposed.useUserPreferenceStore();store.userSettings.value = {user: {id: 9}}
    return {h, store}
}
test('ERRORFIX-14: explicit strict user settings persist rejects while default callers remain handled', async () => {
    const {store, h} = loadStore()
    await assert.rejects(store.updateUserSettings(true, true));await assert.doesNotReject(store.updateUserSettings(true))
    assert.equal(h.messages.length, 2)
})
test('ERRORFIX-14 integration: actual rejected user settings keep wizard on its step', async () => {
    const {store} = loadStore()
    const h = component('pages/WelcomePage.vue', ['updateSpaceAndUserSettings', 'space', 'stepper', 'loading'], {api: {apiSpacePartialUpdate: async () => ({id: 1})}, globals: {useUserPreferenceStore: () => store}})
    h.exposed.space.value = {id: 1};await h.exposed.updateSpaceAndUserSettings();await settle()
    assert.equal(h.exposed.stepper.value, '1');assert.equal(h.exposed.loading.value, false)
})
