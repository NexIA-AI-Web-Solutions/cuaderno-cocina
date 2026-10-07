import test from 'node:test'
import assert from 'node:assert/strict'
import {component, deferred, settle, templateEvent} from './functionalHarness.mjs'

function calendar(api) {
    return component('components/dialogs/MealPlanIcalDialog.vue', ['loadOrCreateToken', 'apiToken', 'dialog', 'loading', 'icalUrl', 'tokenError: typeof tokenError === "undefined" ? undefined : tokenError'], {api, globals: {
        useDjangoUrls: () => ({getFullUrl: path => '/cuaderno-cocina' + path}),
        DateTime: {now: () => ({plus: period => {assert.equal(period.year, 100);return {toJSDate: () => new Date('2126-10-07T00:00:00Z')}}})},
    }})
}
test('Calendar token: mounting calendar dialog makes no token GET or POST', async () => {
    let gets = 0, posts = 0
    const h = calendar({apiAccessTokenList: async () => {gets++;return []}, apiAccessTokenCreate: async () => {posts++;return {token: 'synthetic'}}})
    h.hooks.mounted.forEach(fn => fn());await settle()
    assert.equal(gets, 0);assert.equal(posts, 0);assert.equal(h.exposed.icalUrl.value, '')
})
test('Calendar token: opening without an existing token is read-only and offers no empty-token download', async () => {
    let posts = 0;const h = calendar({apiAccessTokenList: async () => [], apiAccessTokenCreate: async () => {posts++;return {token: 'synthetic'}}})
    await h.exposed.loadOrCreateToken(false);await settle()
    assert.equal(posts, 0);assert.equal(h.exposed.icalUrl.value, '');assert.equal(h.exposed.loading.value, false)
})
test('Calendar token: native dialog opening reuses existing mealplan token without creating one', async () => {
    let gets = 0, posts = 0
    const h = calendar({apiAccessTokenList: async () => {gets++;return [{scope: 'bookmarklet', token: 'wrong'}, {scope: 'mealplan', token: 'synthetic-earlier'}, {scope: 'mealplan', token: 'synthetic-calendar'}]}, apiAccessTokenCreate: async () => {posts++;return {token: 'new'}}})
    const watcher = h.hooks.watchers.find(w => w.source === h.exposed.dialog)
    assert.ok(watcher, 'actual dialog-open watcher');await watcher.fn(true, false);await settle()
    assert.equal(gets, 1);assert.equal(posts, 0);assert.equal(h.exposed.apiToken.value, 'synthetic-calendar');assert.equal(h.exposed.icalUrl.value, '/cuaderno-cocina/api/meal-plan/ical/?access_token=synthetic-calendar')
})
test('Calendar token: explicit generation preserves native scope and expiry and becomes downloadable', async () => {
    const requests = [];const h = calendar({apiAccessTokenList: async () => [], apiAccessTokenCreate: async request => {requests.push(request);return {token: 'synthetic-created'}}})
    await h.exposed.loadOrCreateToken(true);await settle()
    assert.equal(requests.length, 1);assert.equal(requests[0].accessToken.scope, 'mealplan');assert.equal(requests[0].accessToken.expires.toISOString(), '2126-10-07T00:00:00.000Z')
    assert.equal(h.exposed.apiToken.value, 'synthetic-created');assert.equal(h.exposed.loading.value, false)
})
test('Calendar token: rejected lookup clears loading, shows retry state, and never writes', async () => {
    let posts = 0;const h = calendar({apiAccessTokenList: () => Promise.reject(new Error('synthetic list failure')), apiAccessTokenCreate: async () => {posts++;return {token: 'wrong'}}})
    await h.exposed.loadOrCreateToken(true);await settle()
    assert.equal(posts, 0);assert.equal(h.exposed.loading.value, false);assert.equal(h.exposed.tokenError?.value, true);assert.equal(h.exposed.icalUrl.value, '')
})
test('Calendar token: failed generation remains handled and explicit retry succeeds once', async () => {
    let attempts = 0;const h = calendar({apiAccessTokenList: async () => [], apiAccessTokenCreate: async () => {if (++attempts === 1) throw new Error('synthetic create failure');return {token: 'synthetic-retry'}}})
    await h.exposed.loadOrCreateToken(true);await settle()
    assert.equal(h.exposed.tokenError?.value, true);assert.equal(h.exposed.loading.value, false)
    await h.exposed.loadOrCreateToken(true);await settle()
    assert.equal(attempts, 2);assert.equal(h.exposed.apiToken.value, 'synthetic-retry');assert.equal(h.exposed.tokenError.value, false)
})
test('Calendar token: repeated generation while pending cannot create two tokens', async () => {
    const pending = deferred();let gets = 0, posts = 0
    const h = calendar({apiAccessTokenList: () => {gets++;return pending.promise}, apiAccessTokenCreate: async () => {posts++;return {token: 'synthetic'}}})
    const first = h.exposed.loadOrCreateToken(true), second = h.exposed.loadOrCreateToken(true)
    assert.equal(h.exposed.loading.value, true);assert.equal(gets, 1)
    pending.resolve([]);await Promise.all([first, second]);await settle()
    assert.equal(posts, 1);assert.equal(h.exposed.loading.value, false)
})
test('Calendar token: actual generate CTA invokes generation after user action', async () => {
    let posts = 0;const h = calendar({apiAccessTokenList: async () => [], apiAccessTokenCreate: async () => {posts++;return {token: 'synthetic'}}})
    await templateEvent('components/dialogs/MealPlanIcalDialog.vue', /<v-btn[^>]*@click="(loadOrCreateToken\(true\))"/, h.exposed);await settle()
    assert.equal(posts, 1);assert.equal(h.exposed.apiToken.value, 'synthetic')
})
