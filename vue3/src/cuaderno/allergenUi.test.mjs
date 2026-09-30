import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./allergenUi.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {
    ALLERGEN_SAFETY_NOTICE,
    allergenDeclarationName,
    allergenAssessmentEnvelope,
    allergenAssessmentLabel,
    unknownAllergenAssessment,
} = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)

const declaration = {id: 31, name: 'Gluten', state: 'declared'}
const foodEnvelope = {
    scope: {type: 'food', id: 7, name: 'Harina'},
    assessment: 'declared',
    undeclared_means_absent: false,
    unknown_ingredients: false,
    foods: [{id: 7, name: 'Harina', declarations: [declaration]}],
}

test('valid allergen envelopes preserve declared and unknown server states exactly', () => {
    assert.deepEqual(allergenAssessmentEnvelope(foodEnvelope, 'food', 7), foodEnvelope)
    const unknown = {
        scope: {type: 'recipe', id: 12, name: 'Sopa'},
        assessment: 'unknown',
        undeclared_means_absent: false,
        unknown_ingredients: true,
        foods: [{id: 8, name: 'Caldo', declarations: []}],
    }
    assert.deepEqual(allergenAssessmentEnvelope(unknown, 'recipe', 12), unknown)
    assert.equal(allergenAssessmentLabel('declared'), 'Alérgenos declarados')
    assert.equal(allergenAssessmentLabel('unknown'), 'Estado de alérgenos desconocido')
})

test('envelope validation rejects incoherent scopes, unsafe states and coerced identifiers', () => {
    const malformed = [
        null,
        [],
        {...foodEnvelope, scope: {...foodEnvelope.scope, id: true}},
        {...foodEnvelope, scope: {...foodEnvelope.scope, id: 9007199254740992}},
        {...foodEnvelope, scope: {...foodEnvelope.scope, type: 'recipe'}},
        {...foodEnvelope, scope: {...foodEnvelope.scope, id: 8}},
        {...foodEnvelope, scope: {...foodEnvelope.scope, name: ''}},
        {...foodEnvelope, assessment: 'absent'},
        {...foodEnvelope, assessment: 'unknown'},
        {...foodEnvelope, undeclared_means_absent: true},
        {...foodEnvelope, unknown_ingredients: 0},
        {...foodEnvelope, foods: []},
        {...foodEnvelope, foods: [{...foodEnvelope.foods[0], id: '7'}]},
        {...foodEnvelope, foods: [{...foodEnvelope.foods[0], id: 9007199254740992}]},
        {...foodEnvelope, foods: [{...foodEnvelope.foods[0], id: 8}]},
        {...foodEnvelope, foods: [{...foodEnvelope.foods[0], declarations: [{...declaration, name: ''}]}]},
        {...foodEnvelope, foods: [{...foodEnvelope.foods[0], declarations: [{...declaration, id: 9007199254740992}]}]},
        {...foodEnvelope, foods: [{...foodEnvelope.foods[0], declarations: [{...declaration, state: 'safe'}]}]},
        {...foodEnvelope, foods: [foodEnvelope.foods[0], foodEnvelope.foods[0]]},
        {...foodEnvelope, foods: [{...foodEnvelope.foods[0], declarations: [declaration, declaration]}]},
    ]
    for (const value of malformed) {
        assert.equal(allergenAssessmentEnvelope(value, 'food', 7), null, JSON.stringify(value))
    }
})

test('names reject controls and isolated surrogates while preserving valid Unicode code points', () => {
    assert.equal(allergenDeclarationName('  Crustáceos 🦐  '), 'Crustáceos 🦐')
    assert.equal(allergenDeclarationName('🦐'.repeat(128)), '🦐'.repeat(128))
    for (const value of [
        '', '   ', `Gluten\u0000oculto`, `Leche\u001f`, `Soja\u0085`,
        `Huevo\ud800`, `Pescado\udc00`, 'x'.repeat(129), '🦐'.repeat(129), 17, null,
    ]) {
        assert.equal(allergenDeclarationName(value), null, String(value))
    }

    for (const name of ['Harina\u0000', 'Harina\u0085', 'Harina\ud800']) {
        assert.equal(allergenAssessmentEnvelope({
            ...foodEnvelope,
            scope: {...foodEnvelope.scope, name},
        }, 'food', 7), null)
        assert.equal(allergenAssessmentEnvelope({
            ...foodEnvelope,
            foods: [{...foodEnvelope.foods[0], name}],
        }, 'food', 7), null)
        assert.equal(allergenAssessmentEnvelope({
            ...foodEnvelope,
            foods: [{...foodEnvelope.foods[0], declarations: [{...declaration, name}]}],
        }, 'food', 7), null)
    }
})

test('legacy services remain explicitly unknown and the permanent warning never claims absence', () => {
    assert.deepEqual(unknownAllergenAssessment(), {
        assessment: 'unknown',
        undeclared_means_absent: false,
        unknown_ingredients: true,
        foods: [],
    })
    assert.equal(
        ALLERGEN_SAFETY_NOTICE,
        'Sin declaraciones registradas no significa que el alimento o la receta estén libres de alérgenos.',
    )
    assert.doesNotMatch(ALLERGEN_SAFETY_NOTICE, /\bsegur[oa]s?\b|\bausente\b/iu)
})
