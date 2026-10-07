import test from 'node:test'
import assert from 'node:assert/strict'
import {effectScope, nextTick, ref, watch} from 'vue'
import {createI18n} from 'vue-i18n'
import {component} from './functionalHarness.mjs'

// Real Vue and vue-i18n run the shipped shell script. Only the router
// and document boundary are supplied; full DOM acceptance remains Playwright.
function shell() {
    const scope = effectScope()
    const document = {title: 'Cuaderno Cocina'}
    const route = ref({fullPath: '/mealplan', name: 'MealPlanPage', meta: {title: 'Meal_Plan'}})
    const i18n = createI18n({legacy: true, locale: 'en', fallbackLocale: 'en', messages: {en: {Meal_Plan: 'Meal Plan', Help: 'Help', Recipe: 'Recipe'}}})
    const removeHook = () => {}
    const h = scope.run(() => component('apps/tandoor/Tandoor.vue', [], {globals: {
        document, watch,
        useI18n: () => ({t: i18n.global.t.bind(i18n.global)}),
        useRouter: () => ({currentRoute: route, afterEach: () => removeHook}),
    }}))
    return {
        document,
        async spanish() {
            // Matches setupI18n: English initially, asynchronous messages then locale.
            await Promise.resolve()
            i18n.global.setLocaleMessage('es', {Meal_Plan: 'Plan de comidas', Help: 'Ayuda', Recipe: 'Receta'})
            i18n.global.locale = 'es'
            await nextTick()
        },
        async english() {i18n.global.locale = 'en';await nextTick()},
        async navigate(name, title, fullPath) {route.value = {name, meta: title ? {title} : {}, fullPath};await nextTick()},
        dispose() {for (const hook of h.hooks.unmounted) hook();scope.stop();i18n.dispose()},
    }
}

test('actual Vue dependencies refresh title after deferred locale and messages', async () => {
    const s = shell()
    try {
        await nextTick();assert.equal(s.document.title, 'Meal Plan')
        await s.spanish();assert.equal(s.document.title, 'Plan de comidas')
        await s.english();assert.equal(s.document.title, 'Meal Plan')
    } finally {s.dispose()}
})
test('actual Vue locale change preserves all native page-owned titles', async () => {
    for (const name of ['RecipeViewPage', 'ModelListPage', 'ModelEditPage', 'ModelDeletePage']) {
        const s = shell()
        try {
            await s.navigate(name, 'Recipe', '/custom')
            s.document.title = 'Recipe'
            await s.spanish();assert.equal(s.document.title, 'Recipe')
            s.document.title = 'Nombre de receta'
            await s.english();assert.equal(s.document.title, 'Nombre de receta')
            await s.navigate('HelpPage', 'Help', '/help');assert.equal(s.document.title, 'Help')
        } finally {s.dispose()}
    }
})
test('actual Vue history transitions and home fallback follow the active route', async () => {
    const s = shell()
    try {
        await s.spanish()
        await s.navigate('HelpPage', 'Help', '/help');assert.equal(s.document.title, 'Ayuda')
        await s.navigate('MealPlanPage', 'Meal_Plan', '/mealplan');assert.equal(s.document.title, 'Plan de comidas')
        await s.navigate('HelpPage', 'Help', '/help');assert.equal(s.document.title, 'Ayuda')
        await s.navigate('StartPage', undefined, '/');assert.equal(s.document.title, 'Cuaderno Cocina')
        await s.english();assert.equal(s.document.title, 'Cuaderno Cocina')
    } finally {s.dispose()}
})
