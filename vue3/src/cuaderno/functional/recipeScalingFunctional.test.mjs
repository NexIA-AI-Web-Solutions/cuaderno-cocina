import test from 'node:test'
import assert from 'node:assert/strict'
import {component} from './functionalHarness.mjs'

function scaling(number = 4, recipe = {servings: 4, diameter: 20}) {
    const unit = component('components/dialogs/RecipeScalingDialog.vue',
        ['dialog', 'mutableNumber', 'diameter', 'validServings', 'confirmServings', 'updateNumber', 'changeDiameter'],
        {props: {number, recipe}})
    unit.hooks.mounted.forEach(fn => fn())
    const open = () => {
        unit.exposed.dialog.value = true
        const watcher = unit.hooks.watchers.find(row => row.source === unit.exposed.dialog)
        assert.ok(watcher, 'opening the shipped dialog must restore the currently applied servings')
        watcher.fn(true)
    }
    return {...unit, open, recipe}
}

test('zero, negative, missing and non-finite serving drafts never confirm or close', () => {
    const unit = scaling()
    for (const value of [0, -1, null, undefined, NaN, Infinity, -Infinity]) {
        unit.exposed.dialog.value = true
        unit.exposed.mutableNumber.value = value
        assert.equal(unit.exposed.validServings.value, false)
        unit.exposed.confirmServings()
        assert.equal(unit.exposed.dialog.value, true)
    }
    assert.equal(unit.messages.filter(row => row[1] === 'confirm').length, 0)
})

test('a positive fractional serving count applies once without mutating the saved recipe', () => {
    const unit = scaling()
    const baseline = JSON.stringify(unit.recipe)
    unit.exposed.dialog.value = true
    unit.exposed.mutableNumber.value = 2.5
    unit.exposed.confirmServings()
    assert.equal(unit.exposed.dialog.value, false)
    assert.deepEqual(unit.messages.at(-1), ['emit', 'confirm', 2.5])
    assert.equal(JSON.stringify(unit.recipe), baseline)
})

test('cancel and reopen discards unconfirmed servings and diameter drafts', () => {
    const unit = scaling(6)
    unit.open()
    unit.exposed.mutableNumber.value = 12
    unit.exposed.diameter.value = 40
    unit.exposed.dialog.value = false
    assert.equal(unit.messages.filter(row => row[1] === 'confirm').length, 0)
    unit.open()
    assert.equal(unit.exposed.mutableNumber.value, 6)
    assert.equal(unit.exposed.diameter.value, 20)
})

test('halve/double and diameter still produce valid scaled servings', () => {
    const unit = scaling()
    unit.exposed.updateNumber('half')
    assert.equal(unit.exposed.mutableNumber.value, 2)
    unit.exposed.updateNumber('double')
    assert.equal(unit.exposed.mutableNumber.value, 4)
    unit.exposed.changeDiameter(30)
    assert.equal(unit.exposed.mutableNumber.value, 9)
    unit.exposed.confirmServings()
    assert.deepEqual(unit.messages.at(-1), ['emit', 'confirm', 9])
})

test('print/shared view query preserves positive fractional servings and rejects invalid counts', () => {
    for (const [value, expected] of [['2.5', 2.5], ['0.25', 0.25], ['4', 4], ['0', undefined],
        ['-2', undefined], ['Infinity', undefined], ['NaN', undefined], ['', undefined], ['2.5junk', undefined]]) {
        const unit = component('pages/RecipeViewPage.vue', ['servings'], {
            props: {id: '9'}, globals: {provide() {}, RECIPE_SHARE_TOKEN_KEY: Symbol(),
                useUrlSearchParams: () => ({servings: value})},
        })
        assert.equal(unit.exposed.servings.value, expected, `servings=${value}`)
    }
})
