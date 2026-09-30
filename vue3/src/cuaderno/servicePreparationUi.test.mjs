import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./servicePreparationUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {
    servicePreparationEnvelope,
    servicePreparationWrite,
    servicePreparationSaveEnvelope,
    servicePreparationConflictMessage,
} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

const unchecked = {
    id: 41,
    source_step_id: 5,
    position: 0,
    recipe_id: 9,
    name: 'Preparar <arroz>',
    instruction: 'Lavar {{ arroz }} sin interpretar HTML.',
    checked: false,
    checked_at: null,
    updated_by: null,
}
const checked = {
    id: 42,
    source_step_id: null,
    position: 1,
    recipe_id: 10,
    name: 'Preparar salsa',
    instruction: 'Triturar y reservar.',
    checked: true,
    checked_at: '2026-09-30T10:15:30.123456+02:00',
    updated_by: 7,
}

function envelope(overrides = {}) {
    return {
        service_id: 12,
        state: 'confirmed',
        can_edit: true,
        revision: 'a'.repeat(64),
        items: [unchecked, checked],
        ...overrides,
    }
}

test('accepts the exact preparation envelope and preserves frozen text', () => {
    const data = envelope()
    assert.deepEqual(servicePreparationEnvelope(data, 12), data)
})

test('an empty frozen checklist is explicitly read-only', () => {
    const data = envelope()
    assert.equal(servicePreparationEnvelope({...data, can_edit: false, items: []}, 12)?.items.length, 0)
    assert.equal(servicePreparationEnvelope({...data, items: []}, 12), null)
})

test('requires exact envelope keys, safe ids, states and lowercase revision', () => {
    const valid = envelope()
    for (const data of [
        {...valid, extra: true},
        {...valid, service_id: true},
        {...valid, service_id: Number.MAX_SAFE_INTEGER + 1},
        {...valid, state: 'ordered'},
        {...valid, can_edit: 1},
        {...valid, revision: 'A'.repeat(64)},
        {...valid, revision: 'a'.repeat(63)},
        {...valid, items: {}},
    ]) assert.equal(servicePreparationEnvelope(data, 12), null)
    assert.equal(servicePreparationEnvelope(valid, 13), null)
})

test('only confirmed services may be editable', () => {
    assert.notEqual(servicePreparationEnvelope(envelope({state: 'confirmed', can_edit: false}), 12), null)
    for (const state of ['draft', 'produced', 'cancelled']) {
        assert.notEqual(servicePreparationEnvelope(envelope({state, can_edit: false}), 12), null)
        assert.equal(servicePreparationEnvelope(envelope({state, can_edit: true}), 12), null)
    }
})

test('items require complete fields, unique ids and contiguous ordered positions', () => {
    const valid = envelope()
    for (const item of [
        {...unchecked, id: true},
        {...unchecked, source_step_id: 0},
        {...unchecked, position: -1},
        {...unchecked, recipe_id: '9'},
        {...unchecked, name: null},
        {...unchecked, instruction: 4},
        {...unchecked, checked: 0},
        {...unchecked, extra: 'field'},
    ]) assert.equal(servicePreparationEnvelope({...valid, items: [item]}, 12), null)
    assert.equal(servicePreparationEnvelope({...valid, items: [{...unchecked, position: 1}]}, 12), null)
    assert.equal(servicePreparationEnvelope({...valid, items: [unchecked, {...checked, id: unchecked.id}]}, 12), null)
})

test('checked timestamps are timezone-aware and consistent with author state', () => {
    const valid = envelope()
    for (const item of [
        {...unchecked, checked_at: '2026-09-30T10:15:30'},
        {...unchecked, checked_at: 'not-a-date'},
        {...unchecked, checked_at: '2026-09-30T10:15:30Z'},
        {...checked, checked_at: null},
        {...checked, updated_by: null},
        {...checked, updated_by: true},
    ]) assert.equal(servicePreparationEnvelope({...valid, items: [item]}, 12), null)
    assert.notEqual(servicePreparationEnvelope({
        ...valid, items: [{...unchecked, updated_by: 8}],
    }, 12), null)
})

test('write body requires a positive item, strict boolean and server revision', () => {
    assert.deepEqual(servicePreparationWrite(41, true, 'b'.repeat(64)), {
        body: {item: 41, checked: true, revision: 'b'.repeat(64)}, error: '',
    })
    for (const [item, value, revision] of [
        [true, true, 'b'.repeat(64)], [0, true, 'b'.repeat(64)],
        [41, 1, 'b'.repeat(64)], [41, 'true', 'b'.repeat(64)],
        [41, true, 'B'.repeat(64)], [41, true, null],
    ]) {
        const parsed = servicePreparationWrite(item, value, revision)
        assert.equal(parsed.body, null)
        assert.match(parsed.error, /preparación|versión|tarea/i)
    }
})

test('save response must confirm the same service and requested item exactly once', () => {
    const data = envelope()
    const before = envelope({
        revision: '9'.repeat(64),
        items: [unchecked, {...checked, checked: false, checked_at: null, updated_by: null}],
    })
    assert.deepEqual(servicePreparationSaveEnvelope(data, 12, 42, true, before), data)
    for (const response of [
        {...data, items: [unchecked]},
        {...data, service_id: 13},
        {...data, items: [unchecked, {...checked, checked: false, checked_at: null}]},
        {...data, items: [checked, checked]},
        {...data, state: 'produced', can_edit: false},
        {...data, can_edit: false},
        {...data, revision: before.revision},
        {...data, items: [{...unchecked, name: 'Texto sustituido'}, checked]},
        {...data, items: [{...unchecked, position: 1}, {...checked, position: 0}]},
        {...data, items: [unchecked, {...checked, recipe_id: 99}]},
        {...data, items: [{...unchecked, source_step_id: 6}, checked]},
        {...data, items: [unchecked, {...checked, source_step_id: 7}]},
        {...data, items: [{
            ...unchecked,
            checked: true,
            checked_at: '2026-09-30T11:00:00+02:00',
            updated_by: 8,
        }, checked]},
    ]) assert.equal(servicePreparationSaveEnvelope(response, 12, 42, true, before), null)
})

test('save may reflect native step deletion without changing frozen text or membership', () => {
    const before = envelope({
        revision: '8'.repeat(64),
        items: [unchecked, {...checked, checked: false, checked_at: null, updated_by: null}],
    })
    const response = envelope({items: [{...unchecked, source_step_id: null}, checked]})
    const parsed = servicePreparationSaveEnvelope(response, 12, 42, true, before)
    assert.equal(parsed?.items[0]?.source_step_id, null)
    assert.equal(parsed?.items[0]?.instruction, unchecked.instruction)
})

test('conflict message promises preservation and explicit reload, never retry', () => {
    const message = servicePreparationConflictMessage(409)
    assert.match(message, /conservamos/i)
    assert.match(message, /recargar/i)
    assert.doesNotMatch(message, /reintent/i)
    assert.equal(servicePreparationConflictMessage(400), '')
})
