import test from 'node:test'
import assert from 'node:assert/strict'
import {component, deferred, settle, templateEvent} from './functionalHarness.mjs'

const load = (api, props = {}) => {
    const harness = component('components/inputs/VModelSelect.vue', ['searchItems', 'search', 'items', 'loading', 'modelClass', 'autoselectValue', 'updateAutoselectValue', 'handleModelEditorUpdate', 'updateModelValue', 'handleModelEditorCreate: typeof handleModelEditorCreate === "undefined" ? undefined : handleModelEditorCreate'], {api, props: {model: 'Food', ...props}})
    harness.hooks.beforeMount.forEach(fn => fn())
    return harness
}
test('BUGFIX-01: latest selector search survives reversed responses', async () => {
    const a = deferred(), b = deferred();const h = load({list: ({query}) => query === 'a' ? a.promise : b.promise});const s = h.exposed
    s.search.value = 'a';s.searchItems();s.search.value = 'b';s.searchItems()
    b.resolve({results: [{id: 2}], next: null});await settle();a.resolve({results: [{id: 1}], next: null});await settle()
    assert.equal(s.items.value[0].id, 2)
})
test('BUGFIX-02: pending selector ID cannot restore a cleared value', async () => {
    const request = deferred();const h = load({retrieve: () => request.promise});const s = h.exposed
    s.updateAutoselectValue(1);s.updateAutoselectValue(null);request.resolve({id: 1});await settle()
    assert.equal(s.autoselectValue.value, null)
})
test('BUGFIX-03: removed multi selection stays removed after lookup', async () => {
    const request = deferred();const h = load({retrieve: () => request.promise}, {multiple: true});const s = h.exposed
    s.updateAutoselectValue([1]);s.updateAutoselectValue([]);request.resolve({id: 1});await settle()
    assert.equal(s.autoselectValue.value.length, 0)
})
test('BUGFIX-04: editing an absent ID does not replace another selection', () => {
    const s = load({}, {multiple: true}).exposed;s.autoselectValue.value = [{id: 1}, {id: 2}]
    s.handleModelEditorUpdate({id: 3});assert.equal(s.autoselectValue.value[1].id, 2)
})
test('ERRORFIX-10: unavailable selected ID reports failure without rejection', async () => {
    const h = load({retrieve: () => Promise.reject(new Error('synthetic missing'))})
    await h.exposed.updateAutoselectValue(42);await settle()
    assert.equal(h.messages[0]?.[0], 'fetch')
})
test('Creating through the dialog still selects the new object once', () => {
    const h = load({}, {multiple: true});h.exposed.autoselectValue.value = [{id: 1}]
    for (let i = 0; i < 2; i++) templateEvent('components/inputs/VModelSelect.vue', /<model-edit-dialog[^>]*@create="([^"]+)"/, {...h.exposed, $event: {id: 2}})
    assert.equal(h.exposed.autoselectValue.value.length, 2)
    assert.equal(h.exposed.autoselectValue.value[1].id, 2)
})

test('Supplementary selector clear: clearing ID-returning selection informs parent without pending request', () => {
    const h = load({}, {returnObject: false});h.exposed.autoselectValue.value = {id: 42}
    h.exposed.updateModelValue(null)
    assert.equal(h.messages.at(-1)?.[0], 'emit');assert.equal(h.messages.at(-1)?.[1], 'update:modelValue');assert.equal(h.messages.at(-1)?.[2], null)
})
