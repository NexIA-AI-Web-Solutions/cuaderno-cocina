import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`

async function generatedModule(relativePath) {
    const helpers = [
        'UserFromJSON', 'UserFromJSONTyped', 'UserToJSON', 'UserToJSONTyped',
        'FoodShoppingFromJSON', 'FoodShoppingFromJSONTyped', 'FoodShoppingToJSON', 'FoodShoppingToJSONTyped',
        'ShoppingListFromJSON', 'ShoppingListFromJSONTyped', 'ShoppingListToJSON', 'ShoppingListToJSONTyped',
        'ShoppingListRecipeFromJSON', 'ShoppingListRecipeFromJSONTyped', 'ShoppingListRecipeToJSON', 'ShoppingListRecipeToJSONTyped',
        'UnitFromJSON', 'UnitFromJSONTyped', 'UnitToJSON', 'UnitToJSONTyped',
    ]
    const dependency = moduleUrl(`${helpers.map(name => `export const ${name} = value => value;`).join('\n')}\nexport const mapValues = value => value;`)
    const source = readFileSync(new URL(relativePath, import.meta.url), 'utf8')
    let code = ts.transpileModule(source, {compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    }}).outputText
    code = code.replace(/from (["'])([^"']+)\1/g, `from ${JSON.stringify(dependency)}`)
    return import(moduleUrl(code))
}

test('generated shopping SDK preserves opaque microsecond revisions without Date conversion', async () => {
    const sdk = await generatedModule('../openapi/models/ShoppingListEntry.ts')
    const revision = '2026-10-04T12:30:00.123456+02:00'
    const parsed = sdk.ShoppingListEntryFromJSON({
        id: 7, revision, food: {id: 3}, amount: 1,
        list_recipe_data: {}, created_by: {},
        created_at: revision, updated_at: revision,
    })
    assert.equal(parsed.revision, revision)
    assert.equal(sdk.instanceOfShoppingListEntry(parsed), true)
})

test('generated bulk SDK round-trips the per-entry opaque revision map exactly', async () => {
    const sdk = await generatedModule('../openapi/models/ShoppingListEntryBulk.ts')
    const revisions = {
        '7': '2026-10-04T12:30:00.123456+02:00',
        '8': 'opaque-etag-v2',
    }
    const parsed = sdk.ShoppingListEntryBulkFromJSON({ids: [7, 8], revisions, timestamp: '2026-10-04T10:30:00Z'})
    assert.deepEqual(parsed.revisions, revisions)
    assert.deepEqual(sdk.ShoppingListEntryBulkToJSON(parsed).revisions, revisions)
})
