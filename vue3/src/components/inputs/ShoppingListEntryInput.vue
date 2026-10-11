<template>
    <v-text-field :label="$t('Shopping_input_placeholder')" density="compact" @keyup.enter="parseIngredient()" v-model="ingredientInput" :loading="props.loading || loading || submitting" :disabled="props.loading || submitting" hide-detail
                  v-if="!useUserPreferenceStore().deviceSettings.shopping_input_autocomplete" s>
        <template #append>
            <v-btn
                density="comfortable"
                @click="parseIngredient()"
                :icon="ingredientInputIcon"
                aria-label="Añadir alimento a la compra" min-height="44" min-width="44" :disabled="props.loading || submitting"
                color="create"
            ></v-btn>
        </template>
    </v-text-field>

    <Multiselect
        v-if="useUserPreferenceStore().deviceSettings.shopping_input_autocomplete"
        :placeholder="$t('Shopping_input_placeholder')"
        :no-options-text="$t('No_Results')"
        :no-results-text="$t('No_Results')"
        :aria="{label: $t('Shopping_input_placeholder')}"
        class="material-multiselect "
        v-model="ingredientModelInput"
        :options="search"
        :on-create="createObject"
        create-option
        @select="selectObject"
        valueProp="id"
        label="name"
        :delay="300"
        :searchable="true"
        :strict="false"
        :disabled="props.loading || submitting"
        :classes="{
                dropdown: 'multiselect-dropdown z-3000',
                containerActive: '',
            }"
    />
    <v-alert v-if="failedDraft && useUserPreferenceStore().deviceSettings.shopping_input_autocomplete" type="error" variant="tonal" role="alert" class="mt-2">
        El alimento no se ha añadido. Conservamos el texto para reintentar.
        <v-text-field v-model="ingredientInput" label="Alimento pendiente" :disabled="submitting" hide-details class="mt-2" @keyup.enter="parseIngredient" />
        <v-btn min-height="44" :disabled="submitting || !ingredientInput.trim()" :loading="submitting" @click="parseIngredient">Reintentar alimento</v-btn>
    </v-alert>
</template>

<script setup lang="ts">


import {PropType, ref} from "vue";
import {ApiApi, Food, FoodSimple, ShoppingListEntryRequest, ShoppingListRecipe, Unit} from "@/openapi";
import {useShoppingStore} from "@/stores/ShoppingStore";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import Multiselect from "@vueform/multiselect";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";

const props = defineProps({
    shoppingListRecipe: {type: {} as PropType<ShoppingListRecipe>, required: false},
    mealPlanId: {type: Number, required: false},
    loading: {type: Boolean, required: false},
})

const ingredientInput = ref('')
const ingredientInputIcon = ref('fa-solid fa-plus')

const ingredientModelInput = ref({} as Food)
const searchQuery = ref('')

const loading = ref(false)
const submitting = ref(false)
const failedDraft = ref(false)

/**
 * add new ingredient from ingredient text input
 */
async function addIngredient(amount: number, unit: Unit | null, food: Food|FoodSimple | null) {
    if (!Number.isFinite(amount) || amount <= 0 || !food) throw new Error('Indica un alimento y una cantidad positiva.')
    const sle = {
        amount, unit, food,
        shoppingLists: useShoppingStore().shoppingLists.filter(sl => useUserPreferenceStore().deviceSettings.shopping_selected_shopping_lists.includes(sl.id))
    } as ShoppingListEntryRequest
    if (props.mealPlanId) sle.mealplanId = props.mealPlanId
    const saved = await useShoppingStore().createObject(sle, true)
    // The native store reports failed writes and resolves undefined.
    if (!saved) { failedDraft.value = true; return false }
    ingredientInput.value = ''
    ingredientModelInput.value = {} as Food
    failedDraft.value = false
    ingredientInputIcon.value = 'fa-solid fa-check'
    setTimeout(() => { ingredientInputIcon.value = 'fa-solid fa-plus' }, 1000)
    return true
}

async function parseIngredient() {
    if (submitting.value || props.loading) return
    const ingredient = ingredientInput.value.trim()
    if (!ingredient) return
    submitting.value = true
    loading.value = true
    try {
        const r = await new ApiApi().apiIngredientParserPostCreate({ingredientParserRequest: {ingredient}})
        if (!r.ingredient) throw new Error('No se ha podido interpretar el alimento. Revisa el texto.')
        return await addIngredient(Number(r.ingredient.amount), r.ingredient.unit, r.ingredient.food)
    } catch (err) {
        failedDraft.value = true
        useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    } finally {
        submitting.value = false
        loading.value = false
    }
}

// ----------- FUNCTIONS FOR TESTING MULTISELECT INPUT -------------

function createObject(object: any, select$: Multiselect) {
    ingredientInput.value = object['name']
    select$.close()
    void parseIngredient().then(saved => { if (saved) select$.clearSearch() })
    return false
}

async function selectObject(foodId: number, food: Food, select$: Multiselect) {
    if (submitting.value || props.loading) return false
    ingredientInput.value = food.name || ''
    submitting.value = true
    try { await addIngredient(1, null, food) }
    catch (err) { failedDraft.value = true; useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err) }
    finally { submitting.value = false }
    return false
}

/**
 * performs the API request to search for the selected input
 * @param query input to search for on the API
 */
function search(query: string) {
    loading.value = true
    let api = new ApiApi()

    return api.apiFoodList({query: query, page: 1, pageSize: 25}).then(r => {
        return r.results
    }).catch((err: any) => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        loading.value = false
    })
}

</script>

<style src="@vueform/multiselect/themes/default.css"></style>
<!-- style can't be scoped (for whatever reason) -->
<style>
.material-multiselect {
    --ms-bg: rgba(210, 210, 210, 0.1);
    --ms-border-color: 0;
    --ms-border-color-active: 0;
    border-bottom: inset 1px rgba(50, 50, 50, 0.8);
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
}

.model-select--density-compact {
    --ms-line-height: 1.3;
}

.model-select--density-comfortable {
    --ms-line-height: 1.8;
}

.model-select--density-default {
    --ms-line-height: 2.3;
}


.multiselect-tag {
    background-color: #b98766 !important;
}

.z-3000 {
    z-index: 3000;
}
</style>
