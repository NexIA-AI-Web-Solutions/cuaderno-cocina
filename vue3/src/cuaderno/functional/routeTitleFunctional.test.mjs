import test from 'node:test'
import assert from 'node:assert/strict'
import {component, settle} from './functionalHarness.mjs'

// Execute the shipped shell script. Only router/reactivity and DOM boundaries are
// synthetic here; compilation and real Vue scheduling remain external CI checks.
function shell() {
    let locale = 'en', documentTitle = 'Cuaderno Cocina', routeHook, removed = false
    const subscriptions = []
    const currentRoute = {value: {fullPath: '/mealplan', name: 'MealPlanPage', meta: {title: 'Meal_Plan'}}}
    const translate = key => ({en: {Meal_Plan: 'Meal Plan', Help: 'Help', Recipe: 'Recipe'}, es: {Meal_Plan: 'Plan de comidas', Help: 'Ayuda', Recipe: 'Receta'}}[locale][key] ?? key)
    const document = {get title() {return documentTitle}, set title(value) {documentTitle = value}}
    const title = {get value() {return documentTitle}, set value(value) {documentTitle = value}}
    const h = component('apps/tandoor/Tandoor.vue', [], {globals: {
        document,
        useTitle: () => title,
        useI18n: () => ({t: translate}),
        useRouter: () => ({currentRoute, afterEach(fn) {routeHook = fn;return () => {removed = true}}}),
        watch(source, callback, options) {
            const subscription = {source, callback, previous: undefined}
            subscriptions.push(subscription)
            if (options?.immediate) {subscription.previous = source();callback(subscription.previous, undefined)}
        },
    }})
    const update = () => {for (const item of subscriptions) {const next = item.source();item.callback(next, item.previous);item.previous = next}}
    return {
        document,
        async navigate(name, key, path) {currentRoute.value = {name, meta: key ? {title: key} : {}, fullPath: path};update();routeHook(currentRoute.value, {});await settle()},
        async language(value) {locale = value;update();await settle()},
        async boot() {routeHook(currentRoute.value, {});await settle()},
        unmount() {for (const fn of h.hooks.unmounted) fn()},
        removed: () => removed,
    }
}

test('late Spanish messages update the already displayed calendar route title', async () => {
    const s = shell();await s.boot();assert.equal(s.document.title, 'Meal Plan')
    await s.language('es');assert.equal(s.document.title, 'Plan de comidas')
})
test('locale switches and history navigation retain the current route title', async () => {
    const s = shell();await s.boot();await s.language('es')
    await s.navigate('HelpPage', 'Help', '/help');assert.equal(s.document.title, 'Ayuda')
    await s.language('en');assert.equal(s.document.title, 'Help')
    await s.navigate('MealPlanPage', 'Meal_Plan', '/mealplan');assert.equal(s.document.title, 'Meal Plan')
    await s.language('es');assert.equal(s.document.title, 'Plan de comidas')
    await s.navigate('HelpPage', 'Help', '/help');assert.equal(s.document.title, 'Ayuda')
})
test('home fallback remains the own product title across locale changes', async () => {
    const s = shell();await s.navigate('StartPage', undefined, '/')
    await s.language('es');assert.equal(s.document.title, 'Cuaderno Cocina')
    await s.language('en');assert.equal(s.document.title, 'Cuaderno Cocina')
})
test('page-owned recipe and model titles survive late locale, even when equal to generic', async () => {
    for (const name of ['RecipeViewPage', 'ModelListPage', 'ModelEditPage', 'ModelDeletePage']) {
        const s = shell();await s.navigate(name, 'Recipe', '/custom')
        s.document.title = 'Recipe';await s.language('es');assert.equal(s.document.title, 'Recipe')
        s.document.title = 'Mi receta';await s.language('en');assert.equal(s.document.title, 'Mi receta')
        await s.navigate('HelpPage', 'Help', '/help');assert.equal(s.document.title, 'Help')
    }
})
test('another page title owner is not overwritten by locale updates', async () => {
    const s = shell();await s.boot();s.document.title = 'Título específico'
    await s.language('es');assert.equal(s.document.title, 'Título específico')
    await s.navigate('HelpPage', 'Help', '/help');assert.equal(s.document.title, 'Ayuda')
})
test('shell unmount unregisters its router hook', () => {
    const s = shell();s.unmount();assert.equal(s.removed(), true)
})
