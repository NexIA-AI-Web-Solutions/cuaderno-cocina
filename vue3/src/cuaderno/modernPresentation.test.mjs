import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {stripTypeScriptTypes} from 'node:module'

const root = new URL(process.env.CUADERNO_PRESENTATION_ROOT || '../', import.meta.url)
const read = path => readFileSync(new URL(path, root), 'utf8')
const template = path => read(path).split('<script')[0]

function contrast(first, second) {
    const light = color => color.match(/[0-9a-f]{2}/gi).map(part => parseInt(part, 16) / 255)
        .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
        .reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0)
    const [low, high] = [light(first), light(second)].sort((a, b) => a - b)
    return (high + 0.05) / (low + 0.05)
}

test('both themes explicitly give text and action surfaces accessible contrast', () => {
    const source = stripTypeScriptTypes(read('vuetify.ts').split('export type')[0], {mode: 'transform'})
        .replace(/^import .*$/gm, '').replace('export default createVuetify', 'return createVuetify')
    const options = new Function('createVuetify', 'aliases', 'fa', 'vuetifyLocales', 'DateTime', source)(x => x, {}, {}, {}, {})
    for (const theme of Object.values(options.theme.themes)) {
        for (const surface of ['primary', 'secondary', 'surface', 'background']) {
            assert.ok(theme.colors['on-' + surface], `explicit text color for ${surface}`)
            assert.ok(contrast(theme.colors[surface], theme.colors['on-' + surface]) >= 4.5, `${surface} normal text contrast`)
        }
    }
})

test('shell has skip link and named keyboard-operable user and creation controls', () => {
    const app = template('apps/tandoor/Tandoor.vue')
    assert.match(app, /<a[^>]+href="#cuaderno-main"/)
    assert.match(app, /<v-main[^>]+id="cuaderno-main"[^>]+tabindex="-1"/)
    assert.match(app, /<v-btn[^>]+icon="\$add"[^>]+:aria-label=/)
    assert.match(app, /<v-btn[^>]+class="cuaderno-user-menu[^>]+:aria-label=/)
    const bottom = app.split('<v-bottom-navigation')[1].split('</v-bottom-navigation>')[0]
    for (const key of ['Recipes', 'Meal_Plan', 'Shopping_list', 'More']) assert.match(bottom, new RegExp(`<span[^>]*>[^<]*\\$t\\('${key}'\\)`))
})

test('mobile settings can collapse navigation while all native settings and plugins remain reachable', () => {
    const settings = template('pages/SettingsPage.vue')
    assert.match(settings, /<details[^>]+:open="mdAndUp"/)
    assert.match(settings, /<summary[^>]+class="cuaderno-settings-summary"/)
    assert.match(settings, /<nav[^>]+:aria-label=/)
    for (const name of ['AccountSettings', 'CosmeticSettings', 'ShoppingSettings', 'MealPlanSettings', 'SearchSettings', 'SpaceSettings', 'OpenDataImportSettings', 'ExportDataSettings', 'ApiSettings']) assert.match(settings, new RegExp(`name: '${name}'`))
    assert.match(settings, /p\.settingsComponent/)
    assert.match(settings, /<router-view/)
})

test('recipe names and section actions are native links with preserved destination and target', () => {
    const card = template('components/display/RecipeCard.vue')
    assert.match(card, /<router-link[^>]+class="cuaderno-recipe-title"[^>]+:to="dest"[^>]+:target="linkTarget"/)
    assert.doesNotMatch(card, /<div[^>]+@click="openRecipe\(\)"/)
    const scroller = template('components/display/HorizontalRecipeWindow.vue')
    assert.match(scroller, /<v-btn[^>]+@click="openSearch\(\)"[^>]+:aria-label=/)
    assert.match(scroller, /<v-col[^>]+cols="12"[^>]+sm="6"[^>]+md="3"[^>]+lg="3"[^>]+v-for="r in w"/)
})

test('loading and settled recipe illustrations both use bundled owned assets rather than route-relative URLs', () => {
    const card = read('components/display/RecipeCard.vue')
    const image = read('components/display/RecipeImage.vue')
    assert.doesNotMatch(template('components/display/RecipeCard.vue'), /src="\.\.\/\.\.\/assets\//)
    assert.match(card, /import recipePlaceholder from ['"]\.\.\/\.\.\/assets\/cuaderno-recipe-placeholder\.svg['"]/)
    assert.match(card, /<v-img :src="recipePlaceholder"/)
    assert.match(image, /import recipeDefaultImage from ['"]\.\.\/\.\.\/assets\/cuaderno-recipe-placeholder\.svg['"]/)
    assert.match(image, /:src="image"/)
})

test('calendar previous today and next actions have44px targets and accessible names', () => {
    const header = template('components/display/MealPlanCalendarHeader.vue')
    const actions = [...header.matchAll(/<v-btn[^>]+>/g)].map(match => match[0])
    assert.equal(actions.length, 3)
    for (const action of actions) {
        assert.match(action, /min-width="44"/)
        assert.match(action, /min-height="44"/)
        assert.match(action, /:aria-label=/)
    }
    assert.match(header, /:label="\$t\('Date'\)"/)
})

test('calendar date formatting accepts supported locale filenames as valid native Intl tags', () => {
    const component = read('components/display/MealPlanCalendarHeader.vue')
    const selected = component.match(/\.setLocale\((\w+)\)/)[1]
    const script = component.split('<script setup lang="ts">')[1].split('</script>')[0]
    const executable = stripTypeScriptTypes(script, {mode: 'transform'}).replace(/^import .*$/gm, '')
    for (const locale of ['nb_NO', 'zh_Hans', 'zh_Hant', 'pt_BR', 'es', 'en']) {
        const displayed = new Function('computed', 'ref', 'watch', 'useI18n', 'defineEmits', 'defineProps', `${executable};return ${selected}`)(
            get => ({get value() {return get()}}), value => ({value}), () => {}, () => ({locale: {value: locale}}), () => () => {}, () => ({}),
        )
        const format = new Intl.DateTimeFormat(displayed.value, {dateStyle: 'medium'})
        assert.ok(format.format(new Date('2026-10-07T12:00:00Z')))
        assert.equal(displayed.value, locale.replaceAll('_', '-'))
    }
})

test('initial recipe count has visible accessible loading feedback rather than a blank page', () => {
    const start = template('pages/StartPage.vue')
    assert.match(start, /v-if="totalRecipes < 0 && !countError"[^>]+role="status"[^>]+aria-live="polite"/)
    assert.match(start, /v-skeleton-loader/)
    assert.match(start, /\$t\('Loading'\)/)
    assert.match(start, /v-if="totalRecipes > 0"/)
    assert.match(start, /v-if="totalRecipes == 0"/)
})

test('shopping retains visible task labels and explains a settled empty collection with a native next step', () => {
    const shopping = template('components/display/ShoppingListView.vue')
    const tabs = shopping.split('<v-tabs')[1].split('</v-tabs>')[0]
    for (const key of ['Shopping_list', 'Recipes']) {
        assert.match(tabs, new RegExp(`<span[^>]+class="ms-1">[^]*?\\$t\\('${key}'\\)`))
    }
    assert.match(shopping, /initialized && !useShoppingStore\(\)\.currentlyUpdating && !shoppingListItems\.length/)
    assert.match(shopping, /\$t\('ShoppingEmptyHelp'\)/)
    assert.match(shopping, /name: 'CuadernoListaPage'/)
    const source = read('components/display/ShoppingListView.vue')
    assert.match(source, /cuaderno-shopping-toolbar[^]*?border:/)
    assert.match(source, /cuaderno-shopping-tabs[^]*?border-radius:/)
})

test('appearance and preferences form separate named sections without losing either native save action', () => {
    const appearance = template('components/settings/CosmeticSettings.vue')
    assert.match(appearance, /<section[^>]+aria-labelledby="cuaderno-appearance-heading"/)
    assert.match(appearance, /<h1[^>]+id="cuaderno-appearance-heading"/)
    assert.match(appearance, /<section[^>]+aria-labelledby="cuaderno-preferences-heading"/)
    assert.match(appearance, /<h2[^>]+id="cuaderno-preferences-heading"/)
    assert.equal([...appearance.matchAll(/@click="useUserPreferenceStore\(\)\.updateUserSettings\(\)"/g)].length, 2)
})

test('quick shopping separates pending and completed counts while preserving native check handlers', () => {
    const quick = template('cuaderno/pages/ListaPage.vue')
    for (const [title, group] of [['Pendiente', 'pending'], ['Hecho', 'done']]) {
        assert.match(quick, new RegExp(`<h2[^>]*>${title}</h2>[^]*?\\{\\{ ${group}\\.length \\}\\}`))
    }
    assert.match(quick, /@update:model-value="toggle\(entry, true\)"/)
    assert.match(quick, /@update:model-value="toggle\(entry, false\)"/)
    assert.match(read('cuaderno/pages/ListaPage.vue'), /cuaderno-completed-entry[^]*?line-through/)
})

test('production has readable form headings and independent labeled service-state chips', () => {
    const production = template('cuaderno/pages/ProduccionPage.vue')
    for (const title of ['Ficha desde recetas', 'Rendimiento de subreceta', 'Servicio', 'Consolidación manual']) {
        assert.match(production, new RegExp(`<h2[^>]*>${title}</h2>`))
    }
    assert.match(production, /<h2[^>]*>\{\{ plan\.title \}\}<\/h2>/)
    assert.match(production, /<v-chip[^>]+class="cuaderno-service-state"[^>]+:color=[^>]+>\{\{ stateLabel\(plan\.state\) \}\}/)
})

test('warehouse names its movement and history sections and groups each actual audit detail', () => {
    const warehouse = template('cuaderno/pages/AlmacenPage.vue')
    assert.match(warehouse, /<h2[^>]*>Movimiento manual<\/h2>/)
    assert.match(warehouse, /<h2[^>]*>Historial de existencias<\/h2>/)
    assert.match(warehouse, /class="movement-detail[^>]+>\{\{ movementAuditLabel\(row\) \}\}/)
    assert.match(read('cuaderno/pages/AlmacenPage.vue'), /\.movement-detail[^}]+line-height: 1\.6;[^}]+padding: 6px 10px;/)
})

test('home count failure stops loading and preserves a visible retry without fabricating an empty collection', () => {
    const component = read('pages/StartPage.vue')
    const script = component.split('<script setup lang="ts">')[1].split('</script>')[0]
    const executable = stripTypeScriptTypes(script, {mode: 'transform'}).replace(/^import .*$/gm, '')
    let fail = true, count = 0, errorMessages = 0
    const state = new Function('ref', 'onMounted', 'onBeforeUnmount', 'ApiApi', 'useMessageStore', 'settleComponentRequest', 'ErrorMessageType', `${executable};return {totalRecipes,countError,loadRecipeCount}`)(
        value => ({value}), () => {}, () => {}, class {apiRecipeList() {return Promise.resolve({count})}},
        () => ({addError() {errorMessages++}}), (_, signal, success, failure) => {if (fail) failure(new Error('benign count failure')); else success({count})}, {FETCH_ERROR: 'fetch'},
    )
    state.loadRecipeCount()
    assert.equal(state.countError.value, true)
    assert.equal(state.totalRecipes.value, -1)
    assert.equal(errorMessages, 1)
    assert.match(component, /v-if="countError"[^>]+role="alert"/)
    assert.match(component, /@click="loadRecipeCount"/)
    fail = false; count = 2
    state.loadRecipeCount()
    assert.equal(state.countError.value, false)
    assert.equal(state.totalRecipes.value, 2)
})

test('quick search retains usable selection at the final result and handles errors without a cause', () => {
    const component = read('components/inputs/GlobalSearchDialog.vue')
    const script = component.split('<script setup lang="ts">')[1].split('</script>')[0]
    const executable = stripTypeScriptTypes(script, {mode: 'transform'}).replace(/^import .*$/gm, '')
    const box = value => ({value})
    const state = new Function('computed', 'onMounted', 'onUnmounted', 'ref', 'watch', 'useRouter', 'useDisplay', 'useI18n', 'useDebouncedSearch', `${executable};return {dialog,flatRecipes,selectedResult,searchResults,handleKeydown}`)(
        get => ({get value() {return get()}}), () => {}, () => {}, box, () => {}, () => ({push() {}}), () => ({mobile: box(true)}), () => ({t: key => key}), () => ({inputValue: box(''), debouncedValue: box(''), signal: box(undefined), reset() {}}),
    )
    state.flatRecipes.value = [{id: 1, name: 'Benign recipe'}]
    state.dialog.value = true
    for (let index = 0; index < 5; index++) state.handleKeydown({key: 'ArrowDown'})
    assert.equal(state.selectedResult.value, state.searchResults.value.length - 1)
    const body = script.match(/\.catch\(err => \{\s*(if \(err[^]*?)\n\s*\}\)\.finally/)[1]
    let reports = 0
    const report = new Function('err', 'useMessageStore', 'ErrorMessageType', body)
    report(new Error('benign failure'), () => ({addError() {reports++}}), {FETCH_ERROR: 'fetch'})
    assert.equal(reports, 1)
    report({name: 'AbortError'}, () => ({addError() {reports++}}), {FETCH_ERROR: 'fetch'})
    report({cause: {name: 'AbortError'}}, () => ({addError() {reports++}}), {FETCH_ERROR: 'fetch'})
    assert.equal(reports, 1)
})

test('search pending truth survives debounce and an older aborted request while the new body is outstanding', async () => {
    const component = read('components/inputs/GlobalSearchDialog.vue')
    const script = component.split('<script setup lang="ts">')[1].split('</script>')[0]
    const executable = stripTypeScriptTypes(script, {mode: 'transform'}).replace(/^import .*$/gm, '')
    const box = value => ({value}), watchers = [], requests = []
    const inputs = {inputValue: box(''), debouncedValue: box(''), signal: box(new AbortController().signal), reset() {}}
    const state = new Function('computed', 'onMounted', 'onUnmounted', 'ref', 'watch', 'useRouter', 'useDisplay', 'useI18n', 'useDebouncedSearch', 'ApiApi', 'useMessageStore', 'ErrorMessageType', `${executable};return {searchQuery,debouncedSearchQuery,asyncLoading,searchPending: typeof searchPending === 'undefined' ? computed(() => flatListLoading.value || asyncLoading.value) : searchPending,searchResults}`)(
        get => ({get value() {return get()}}), () => {}, () => {}, box, (target, callback) => watchers.push({target, callback}), () => ({push() {}}), () => ({mobile: box(true)}), () => ({t: key => key}), () => inputs,
        class {apiRecipeList() {return new Promise((resolve, reject) => requests.push({resolve, reject}))}}, () => ({addError() {}}), {FETCH_ERROR: 'fetch'},
    )
    const update = watchers.find(watcher => watcher.target === inputs.debouncedValue).callback
    state.searchQuery.value = 'one'
    assert.equal(state.searchPending.value, true)
    state.debouncedSearchQuery.value = 'one'; update('one')
    state.searchQuery.value = 'two'
    state.debouncedSearchQuery.value = 'two'; inputs.signal.value = new AbortController().signal; update('two')
    requests[0].reject(Object.assign(new Error('benign abort'), {name: 'AbortError'}))
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(state.asyncLoading.value, true)
    assert.equal(state.searchPending.value, true)
    requests[1].resolve({results: [{id: 2, name: 'two'}]})
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(state.searchPending.value, false)
    assert.ok(state.searchResults.value.some(item => item.recipeId === 2))
    state.searchQuery.value = 'three'
    assert.equal(state.searchPending.value, true)
    assert.ok(state.searchResults.value.every(item => item.recipeId !== 2))
    assert.match(component, /searchQuery && !searchPending && !searchResults/)
})
