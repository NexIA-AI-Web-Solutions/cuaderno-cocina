import test from 'node:test'
import assert from 'node:assert/strict'
import {dietPresentation, templateEntriesFromPlans, planningEndDate} from './planningUi.mjs'

test('unknown or missing declarations never become suitable', () => {
    for (const value of [undefined, null, 'unknown', 'unexpected']) {
        assert.deepEqual(dietPresentation(value), {label: 'No declarado', color: 'warning'})
    }
    assert.deepEqual(dietPresentation('unsuitable'), {label: 'No apto · declaración manual', color: 'error'})
    assert.deepEqual(dietPresentation('suitable'), {label: 'Apto · declaración manual', color: 'success'})
})

test('one to five calendar weeks include exactly seven to thirty-five dates', () => {
    assert.equal(planningEndDate('2026-12-28', 1), '2027-01-03')
    assert.equal(planningEndDate('2026-12-28', 5), '2027-01-31')
    for (const weeks of [0, 6, 1.5, NaN]) assert.throws(() => planningEndDate('2026-10-07', weeks))
    assert.throws(() => planningEndDate('2026-02-30', 1))
})

test('template capture preserves native recipe, meal type, course and decimal servings', () => {
    const plan = {id: 9, from_date: '2026-10-08T12:00:00+02:00', recipe: {id: 4, name: 'Sopa'}, meal_type: {id: 3, name: 'Comida'}, course: 7, servings: '2.50', title: 'Sopa', source_url: ''}
    assert.deepEqual(templateEntriesFromPlans([plan], '2026-10-07', 1), [{day_index: 1, meal_type: 3, course: 7, recipe: 4, title: 'Sopa', source_url: '', servings: '2.50'}])
    assert.throws(() => templateEntriesFromPlans([plan], '2026-10-09', 1))
    assert.throws(() => templateEntriesFromPlans([{...plan, to_date: '2026-10-10T12:00:00+02:00'}], '2026-10-07', 1))
})
