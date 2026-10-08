import test from 'node:test'
import assert from 'node:assert/strict'
import {DateTime} from 'luxon'
import {planningEndDate} from '../planningUi.mjs'
import {component, deferred, settle} from './functionalHarness.mjs'

function calendar(request) {
    const native = {loading: false, planList: [], plans: new Map(), refreshFromAPI() {this.loading = true}}
    const h = component('components/display/MealPlanView.vue', [
        'loadPlanning', 'calendarDate', 'professional', 'planning', 'planningError', 'editionLoading',
        'calendarBusy: typeof calendarBusy === "undefined" ? undefined : calendarBusy',
    ], {globals: {DateTime, planningEndDate, planningRequest: request,
        useMealPlanStore: () => native}})
    Object.assign(h.store.deviceSettings, {mealplan_displayPeriod: 'week', mealplan_displayPeriodCount: 3,
        mealplan_startingDayOfWeek: 1})
    h.exposed.calendarDate.value = new Date('2026-10-08T12:00:00Z')
    const nativeWatcher = h.hooks.watchers.find(w => typeof w.source === 'function' && w.source() === native.loading)
    assert.ok(nativeWatcher, 'the native loading-completion watcher must exist')
    return {...h, native,
        enableProfessional() {h.exposed.professional.value = true; h.exposed.editionLoading.value = false},
        completeNative() {native.loading = false; nativeWatcher.fn(false, true)}}
}

const data = () => ({courses: [], meal_plans: [], events: [], can_edit: true})

test('changing calendar period defers annotations until native loading completes, then reads once', async () => {
    const reads = []
    const h = calendar(async path => {reads.push(path); return data()})
    h.enableProfessional()
    const dateWatcher = h.hooks.watchers.find(w => w.source === h.exposed.calendarDate)
    dateWatcher.fn()
    await settle()
    assert.equal(h.native.loading, true)
    assert.deepEqual(reads, [], 'no annotations request may race the native period request')
    h.completeNative()
    await settle()
    assert.deepEqual(reads, ['planning/?from_date=2026-10-05&to_date=2026-10-25'])
    assert.equal(h.exposed.calendarBusy.value, false)
})

test('mount waits for edition and native reads before marking calendar ready or loading annotations', async () => {
    const edition = deferred(), annotations = deferred(), reads = []
    const h = calendar(path => {reads.push(path); return path === 'edition/' ? edition.promise : annotations.promise})
    h.hooks.mounted.forEach(fn => fn())
    assert.equal(h.exposed.calendarBusy?.value, true)
    edition.resolve({edition: 'integral', operational_role: {can_operate_cuaderno: true}})
    await settle()
    assert.deepEqual(reads, ['edition/'])
    assert.equal(h.exposed.calendarBusy.value, true)
    h.completeNative()
    await settle()
    assert.equal(reads.length, 2)
    assert.equal(h.exposed.calendarBusy.value, true)
    annotations.resolve(data())
    await settle()
    assert.equal(h.exposed.calendarBusy.value, false)
})

test('new native period invalidates pending annotations and stale completion cannot clear readiness', async () => {
    const old = deferred(), current = deferred(), reads = []
    const h = calendar(path => {reads.push(path); return reads.length === 1 ? old.promise : current.promise})
    h.enableProfessional()
    const oldLoad = h.exposed.loadPlanning()
    h.native.loading = true
    void h.exposed.loadPlanning()
    await settle()
    assert.equal(reads.length, 1)
    old.resolve({...data(), events: [{id: 99}]})
    await oldLoad
    assert.equal(h.exposed.planning.value, null)
    assert.equal(h.exposed.calendarBusy.value, true)
    h.completeNative()
    await settle()
    assert.equal(reads.length, 2)
    assert.equal(h.exposed.calendarBusy.value, true)
    current.resolve(data())
    await settle()
    assert.equal(h.exposed.calendarBusy.value, false)
    assert.equal(h.exposed.planning.value.events.length, 0)
})

test('reloading an unchanged period after a native edit reads current annotations again', async () => {
    let reads = 0
    const h = calendar(async () => {reads++; return data()})
    h.enableProfessional()
    await h.exposed.loadPlanning()
    h.native.loading = true
    await h.exposed.loadPlanning()
    h.completeNative()
    await settle()
    assert.equal(reads, 2, 'same-period annotations cannot remain permanently cached')
    await h.exposed.loadPlanning()
    assert.equal(reads, 3, 'the explicit reload action must always remain usable')
})

test('annotation failure ends pending state and preserves an actionable Spanish retry message', async () => {
    let fail = true
    const h = calendar(async () => {if (fail) throw new Error('Sin conexión'); return data()})
    h.enableProfessional()
    await h.exposed.loadPlanning()
    assert.match(h.exposed.planningError.value, /No se pudieron cargar tipos, dietas y eventos.*calendario nativo sigue disponible.*Sin conexión/)
    // The actual reload button calls the same shipped function; no automatic retry occurs.
    fail = false
    await h.exposed.loadPlanning()
    assert.equal(h.exposed.planningError.value, '')
    assert.equal(h.exposed.planning.value.events.length, 0)
})

test('edition failure settles readiness while retaining the native calendar and permission warning', async () => {
    const h = calendar(async () => {throw new Error('Sin conexión')})
    h.hooks.mounted.forEach(fn => fn())
    h.completeNative()
    await settle()
    assert.equal(h.exposed.professional.value, false)
    assert.equal(h.exposed.calendarBusy?.value, false)
    assert.match(h.exposed.planningError.value, /No se pudieron comprobar los permisos.*modo lectura/)
})

test('native completion cannot erase an earlier permission warning or enable annotations', async () => {
    const reads = []
    const h = calendar(async path => {reads.push(path); throw new Error('Sin conexión')})
    h.hooks.mounted.forEach(fn => fn())
    await settle()
    assert.equal(h.native.loading, true)
    assert.match(h.exposed.planningError.value, /No se pudieron comprobar los permisos/)
    h.completeNative()
    await settle()
    assert.deepEqual(reads, ['edition/'])
    assert.equal(h.exposed.calendarBusy.value, false)
    assert.match(h.exposed.planningError.value, /No se pudieron comprobar los permisos.*modo lectura/)
})
