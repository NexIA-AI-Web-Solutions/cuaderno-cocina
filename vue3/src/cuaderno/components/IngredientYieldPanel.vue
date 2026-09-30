<template>
    <section aria-labelledby="ingredient-yield-title">
        <h2 id="ingredient-yield-title" class="text-subtitle-1 font-weight-bold mb-2">Mermas de ingredientes</h2>
        <p class="text-body-2 text-medium-emphasis mb-3">
            Indica si la cantidad de la receta es bruta o neta útil. El rendimiento se guarda por ingrediente.
        </p>

        <p v-if="loading" role="status">Cargando rendimientos…</p>
        <v-alert v-else-if="loadError" type="error" variant="tonal" role="alert" class="mb-3">
            {{ loadError }}
            <template #append>
                <v-btn variant="text" min-height="44" @click="load">Reintentar</v-btn>
            </template>
        </v-alert>
        <template v-else-if="payload">
            <v-alert v-if="!payload.can_edit" type="info" variant="tonal" class="mb-3">
                Puedes consultar las mermas. La edición requiere Profesional o Integral y permisos sobre la receta.
            </v-alert>
            <p v-if="!payload.ingredients.length" class="text-medium-emphasis">Esta receta no tiene ingredientes editables.</p>

            <v-row v-else dense>
                <v-col v-for="ingredient in payload.ingredients" :key="ingredient.id" cols="12" lg="6">
                    <v-card variant="outlined" class="h-100 yield-row">
                        <v-card-text>
                            <div class="d-flex flex-wrap justify-space-between ga-2 mb-2">
                                <div>
                                    <p class="font-weight-bold mb-0">{{ ingredient.food_name || "Ingrediente sin alimento" }}</p>
                                    <p class="text-body-2 text-medium-emphasis mb-0">
                                        {{ ingredient.amount }} {{ ingredient.unit || "sin unidad" }}
                                    </p>
                                </div>
                                <v-chip size="small" variant="tonal">{{ draftSummary(ingredient) }}</v-chip>
                            </div>

                            <v-alert v-if="ingredient.is_subrecipe" type="info" variant="tonal" density="compact" class="mb-2">
                                Esta línea es una subelaboración. Su rendimiento se define en la receta hija para evitar doble merma.
                            </v-alert>

                            <v-row dense>
                                <v-col cols="12" sm="6">
                                    <v-select
                                        :model-value="drafts[ingredient.id]?.quantityBasis"
                                        :items="basisOptions"
                                        item-title="title"
                                        item-value="value"
                                        label="Base de la cantidad"
                                        min-height="44"
                                        hide-details="auto"
                                        :disabled="!payload.can_edit || ingredient.is_subrecipe || savingIngredient !== null"
                                        @update:model-value="value => updateBasis(ingredient.id, value)"
                                    />
                                </v-col>
                                <v-col cols="12" sm="6">
                                    <v-text-field
                                        :model-value="drafts[ingredient.id]?.ratio"
                                        label="Rendimiento (0 a 1)"
                                        inputmode="decimal"
                                        autocomplete="off"
                                        min-height="44"
                                        hide-details="auto"
                                        :error-messages="drafts[ingredient.id]?.error"
                                        :disabled="!payload.can_edit || ingredient.is_subrecipe || savingIngredient !== null"
                                        @update:model-value="value => updateRatio(ingredient.id, String(value ?? ''))"
                                    />
                                </v-col>
                            </v-row>
                            <p class="text-caption text-medium-emphasis mt-2 mb-2">
                                <template v-if="drafts[ingredient.id]?.quantityBasis === 'net_usable'">
                                    La cantidad es útil: el coste puede necesitar más cantidad comprada según el rendimiento.
                                </template>
                                <template v-else>
                                    La cantidad ya es bruta: el rendimiento solo informa la merma y no vuelve a dividirla.
                                </template>
                            </p>
                            <div v-if="payload.can_edit && !ingredient.is_subrecipe" class="d-flex align-center flex-wrap ga-2">
                                <v-btn
                                    color="primary"
                                    variant="tonal"
                                    min-height="44"
                                    :loading="savingIngredient === ingredient.id"
                                    :disabled="savingIngredient !== null || !drafts[ingredient.id]?.dirty"
                                    @click="save(ingredient)"
                                >
                                    Guardar merma
                                </v-btn>
                                <span v-if="draftMessage(ingredient.id)" role="status" class="text-body-2">
                                    {{ draftMessage(ingredient.id) }}
                                </span>
                            </div>
                        </v-card-text>
                    </v-card>
                </v-col>
            </v-row>
        </template>
    </section>
</template>

<script setup lang="ts">
import {onBeforeUnmount, ref, watch} from 'vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {
    ingredientYieldBody,
    quantityBasisLabel,
    yieldSummary,
    type QuantityBasis,
} from '@/cuaderno/ingredientYieldUi'

type IngredientYield = {
    id: number
    food_name: string | null
    amount: string
    unit: string | null
    quantity_basis: QuantityBasis
    yield_ratio: string | null
    is_subrecipe: boolean
}

type IngredientYieldResponse = {
    recipe_id: number
    edition: string
    can_edit: boolean
    ingredients: IngredientYield[]
}

type YieldDraft = {
    quantityBasis: QuantityBasis
    ratio: string
    error: string
    message: string
    dirty: boolean
    revision: number
}

const props = defineProps<{recipeId: number}>()
const emit = defineEmits<{saved: []}>()
const payload = ref<IngredientYieldResponse | null>(null)
const drafts = ref<Record<number, YieldDraft>>({})
const loading = ref(false)
const loadError = ref('')
const savingIngredient = ref<number | null>(null)
const basisOptions = [
    {title: quantityBasisLabel('gross'), value: 'gross'},
    {title: quantityBasisLabel('net_usable'), value: 'net_usable'},
]
let requestGeneration = 0
let loadedRecipeId: number | null = null
let loadController: AbortController | null = null
let saveController: AbortController | null = null

function serverDraft(ingredient: IngredientYield): YieldDraft {
    return {
        quantityBasis: ingredient.quantity_basis,
        ratio: ingredient.yield_ratio ?? '',
        error: '',
        message: '',
        dirty: false,
        revision: 0,
    }
}

function applyPayload(data: IngredientYieldResponse, savedId: number | null = null, savedRevision = -1) {
    const previous = drafts.value
    const next: Record<number, YieldDraft> = {}
    for (const ingredient of data.ingredients) {
        const current = previous[ingredient.id]
        if (current?.dirty && !(ingredient.id === savedId && current.revision === savedRevision)) {
            next[ingredient.id] = current
        } else {
            const fresh = serverDraft(ingredient)
            if (ingredient.id === savedId) fresh.message = 'Merma guardada.'
            next[ingredient.id] = fresh
        }
    }
    payload.value = data
    drafts.value = next
}

async function load() {
    const generation = ++requestGeneration
    const recipeAtLoad = props.recipeId
    loadController?.abort()
    saveController?.abort()
    savingIngredient.value = null
    if (loadedRecipeId !== recipeAtLoad) {
        loadedRecipeId = recipeAtLoad
        payload.value = null
        drafts.value = {}
    }
    loadError.value = ''
    loading.value = true
    loadController = new AbortController()
    const controller = loadController
    const {ok, status, data} = await readJson(await cuadernoFetch(
        `/api/cuaderno/recipes/${recipeAtLoad}/ingredient-yields/`,
        {signal: controller.signal},
    ))
    if (controller.signal.aborted || generation !== requestGeneration || recipeAtLoad !== props.recipeId) return
    loading.value = false
    if (!ok || data?.recipe_id !== recipeAtLoad || !Array.isArray(data?.ingredients)) {
        loadError.value = apiError(status, data)
        return
    }
    applyPayload(data as IngredientYieldResponse)
}

function updateBasis(id: number, value: unknown) {
    const draft = drafts.value[id]
    if (!draft || (value !== 'gross' && value !== 'net_usable')) return
    draft.quantityBasis = value
    draft.error = ''
    draft.message = ''
    draft.dirty = true
    draft.revision += 1
}

function updateRatio(id: number, value: string) {
    const draft = drafts.value[id]
    if (!draft) return
    draft.ratio = value
    draft.error = ''
    draft.message = ''
    draft.dirty = true
    draft.revision += 1
}

function draftSummary(ingredient: IngredientYield) {
    const draft = drafts.value[ingredient.id]
    if (!draft) return yieldSummary(ingredient.yield_ratio)
    const parsed = ingredientYieldBody(ingredient.id, draft.quantityBasis, draft.ratio, ingredient.is_subrecipe)
    return yieldSummary(parsed.body?.yield_ratio ?? ingredient.yield_ratio)
}

function draftMessage(id: number) {
    return drafts.value[id]?.message || ''
}

async function save(ingredient: IngredientYield) {
    const draft = drafts.value[ingredient.id]
    if (!payload.value?.can_edit || !draft || savingIngredient.value !== null) return
    const parsed = ingredientYieldBody(ingredient.id, draft.quantityBasis, draft.ratio, ingredient.is_subrecipe)
    draft.error = parsed.error
    draft.message = ''
    if (!parsed.body) return

    const generation = requestGeneration
    const recipeAtSave = props.recipeId
    const revision = draft.revision
    saveController?.abort()
    saveController = new AbortController()
    const controller = saveController
    savingIngredient.value = ingredient.id
    const {ok, status, data} = await readJson(await cuadernoFetch(
        `/api/cuaderno/recipes/${recipeAtSave}/ingredient-yields/`,
        {method: 'PUT', body: JSON.stringify(parsed.body), signal: controller.signal},
    ))
    if (controller.signal.aborted || generation !== requestGeneration || recipeAtSave !== props.recipeId) return
    savingIngredient.value = null
    if (!ok || data?.recipe_id !== recipeAtSave || !Array.isArray(data?.ingredients)) {
        draft.error = apiError(status, data)
        return
    }
    applyPayload(data as IngredientYieldResponse, ingredient.id, revision)
    emit('saved')
}

watch(() => props.recipeId, load, {immediate: true})
onBeforeUnmount(() => {
    ++requestGeneration
    loadController?.abort()
    saveController?.abort()
})
</script>

<style scoped>
.yield-row {
    min-width: 0;
}
</style>
