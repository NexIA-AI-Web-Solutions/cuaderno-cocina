import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {stripTypeScriptTypes} from 'node:module'
const view = readFileSync(new URL('../components/display/HelpView.vue', import.meta.url), 'utf8')

test('help product guidance contains no hardcoded English promotional paragraphs or blanket visibility claims', () => {
    assert.doesNotMatch(view, /All your data|Recipes are the foundation|most powerful features|While everyone can access all recipes|Recipes, by default, are visible to all/)
    assert.match(view, /helpSections/)
})

test('all historical help topics and original native navigation actions remain available', () => {
    const source = readFileSync(new URL('./helpContent.ts', import.meta.url), 'utf8')
    const executable = stripTypeScriptTypes(source, {mode: 'transform'}).replace(/export /g, '')
    const {helpSections, validHelpSection} = new Function(`${executable};return {helpSections,validHelpSection}`)()
    assert.deepEqual(helpSections.map(section => section.id), ['start', 'space', 'recipes', 'import', 'ai', 'unit', 'food', 'keyword', 'recipe_structure', 'properties', 'recipe_search', 'search_filter', 'books', 'shopping', 'meal_plan'])
    for (const section of helpSections) {assert.ok(section.paragraphs.length);assert.ok(section.paragraphs.every(text => text.length > 30))}
    assert.equal(validHelpSection('translations'), 'translations')
    assert.equal(validHelpSection('does-not-exist'), 'start')
    assert.equal(validHelpSection(undefined), 'start')
    assert.equal(validHelpSection('recipes'), 'recipes')
    const actions = helpSections.flatMap(section => section.actions || [])
    for (const route of ['StartPage', 'UserSpaceSettings', 'SpaceSettings', 'SpaceMemberSettings', 'ModelEditPage', 'SearchPage', 'RecipeImportPage', 'BooksPage', 'ShoppingListPage', 'ShoppingSettings', 'MealPlanPage']) assert.ok(actions.some(action => action.to.name === route), route)
    for (const model of ['AiProvider', 'AiLog', 'Unit', 'UnitConversion', 'Food', 'Keyword', 'PropertyType', 'MealType']) assert.ok(actions.some(action => action.to.params?.model === model), model)
    const privacy = helpSections.find(section => section.id === 'recipes').paragraphs.join(' ')
    assert.match(privacy, /privada.*autorización/)
    assert.match(privacy, /compartid/)
})

test('AI availability follows the actual space flag and provider links require enabled status', () => {
    assert.match(view, /activeSpace\.aiEnabled === true/)
    assert.match(view, /section\.id === 'ai' && !aiEnabled/)
    assert.match(view, /section\.id !== 'ai' \|\| aiEnabled/)
    assert.doesNotMatch(view, /Depending on your subscription|AI Credits|Some AI Providers are available globally/)
})
