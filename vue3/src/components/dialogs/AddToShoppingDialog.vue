<template>
    <v-dialog activator="parent" max-width="600px" v-model="dialog">
        <v-card :loading="loading">
            <v-closable-card-title :title="$t('Add_Servings_to_Shopping', {servings: servings})" v-model="dialog"></v-closable-card-title>
            <v-card-text>
                <v-alert v-if="loadError" type="error" variant="tonal" role="alert" class="mb-3">{{ loadError }}<v-btn variant="text" min-height="44" :disabled="loading" @click="loadRecipeData">Reintentar ingredientes</v-btn></v-alert>
                <v-model-select model="ShoppingList" chips :hint="$t('LeaveEmptyForDefaultList')" v-model="selectedShoppingLists"></v-model-select>
                <v-expansion-panels variant="accordion" v-model="panel">
                    <v-expansion-panel v-for="(r, recipeIndex) in dialogRecipes" :key="r.recipe.id ?? recipeIndex" :value="r.recipe.id ?? recipeIndex">
                        <v-expansion-panel-title>{{ r.recipe.name }}</v-expansion-panel-title>
                        <v-expansion-panel-text>
                            <v-table density="compact">
                                <tbody>
                                <tr v-for="(e, entryIndex) in r.entries" :key="e.ingredient?.id ?? entryIndex" @click="e.checked = !e.checked" class="cursor-pointer">
                                    <td style="width: 1%; text-wrap: nowrap" class="pa-0">
                                        <v-checkbox-btn v-model="e.checked" color="success" :aria-label="`Incluir ${e.food?.name || e.ingredient?.note || 'ingrediente'} de ${r.recipe.name}`" @click.stop></v-checkbox-btn>
                                    </td>
                                    <td style="width: 1%; text-wrap: nowrap" class="pr-1"
                                        v-html="calculateFoodAmount(e.amount, ingredientFactor, useUserPreferenceStore().userSettings.useFractions)"></td>
                                    <td style="width: 1%; text-wrap: nowrap" class="pr-1">
                                        <template v-if="e.unit && e.ingredient"> {{ ingredientToUnitString(e.ingredient, ingredientFactor) }}</template>
                                    </td>
                                    <td>
                                        <template v-if="e.food && e.ingredient"> {{ ingredientToFoodString(e.ingredient, ingredientFactor) }}</template>
                                    </td>
                                </tr>
                                </tbody>
                            </v-table>
                        </v-expansion-panel-text>
                    </v-expansion-panel>
                </v-expansion-panels>
                <v-number-input v-model="servings" class="mt-3" control-variant="split" :label="$t('Servings')" :precision="2" :min="0" :error-messages="servingsError" :disabled="loading"></v-number-input>
            </v-card-text>
            <v-card-actions>
                <v-btn class="float-right" prepend-icon="$create" color="create" @click="createShoppingListRecipe()" :disabled="loading || !!loadError || !validServings">{{ $t('Add_to_Shopping') }}</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script setup lang="ts">

import {computed, onMounted, PropType, ref} from "vue";
import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import {ApiApi, MealPlan, Recipe, RecipeFlat, RecipeOverview, ShoppingList, type ShoppingListEntryBulkCreate, ShoppingListRecipe} from "@/openapi";
import {ErrorMessageType, PreparedMessage, useMessageStore} from "@/stores/MessageStore";
import {ShoppingDialogRecipe, ShoppingDialogRecipeEntry} from "@/types/Shopping";
import {calculateFoodAmount} from "@/utils/number_utils";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import {ingredientToUnitString, ingredientToFoodString} from "@/utils/model_utils.ts";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import VModelSelect from "@/components/inputs/VModelSelect.vue";

const emit = defineEmits(['created'])

const props = defineProps({
    recipe: {type: Object as PropType<Recipe | RecipeFlat | RecipeOverview>, required: true},
    mealPlan: {type: Object as PropType<MealPlan>, required: false},
})

const dialog = ref(false)
const loading = ref(false)
const loadError = ref('')
const validServings = computed(() => typeof servings.value === 'number' && Number.isFinite(servings.value) && servings.value > 0)
const servingsError = computed(() => validServings.value ? '' : 'Indica raciones positivas y válidas.')
const panel = ref(0)

const servings = ref(1)
const selectedShoppingLists = ref([] as ShoppingList[])
const recipe = ref({} as Recipe)
const relatedRecipes = ref([] as Recipe[])

const dialogRecipes = ref([] as ShoppingDialogRecipe[])

const ingredientFactor = computed(() => {
    return servings.value / ((recipe.value.servings != undefined) ? recipe.value.servings : 1)
})

onMounted(() => {
    loadRecipeData()
})

/**
 * load data for the given recipe and all of its related recipes
 */
async function loadRecipeData() {
    if (loading.value) return
    loading.value = true
    loadError.value = ''
    const api = new ApiApi()
    try {
        const [main, related] = await Promise.all([
            api.apiRecipeRetrieve({id: props.recipe.id!}),
            api.apiRecipeRelatedList({id: props.recipe.id!}),
        ])
        const children = await Promise.all(related.map(rs => api.apiRecipeRetrieve({id: rs.id!})))
        recipe.value = main
        relatedRecipes.value = children
        servings.value = main.servings || 1
        panel.value = main.id!
        dialogRecipes.value = [main, ...children].map(item => ({
            recipe: item,
            entries: item.steps.flatMap(step => step.ingredients.filter(ingredient => !ingredient.isHeader).map(ingredient => ({
                amount: Number(ingredient.amount), food: ingredient.food, unit: ingredient.unit, ingredient,
                checked: ingredient.food ? !(ingredient.food.ignoreShopping || ingredient.food.foodOnhand) : true,
            }))),
        }))
    } catch (err) {
        loadError.value = 'No se han podido cargar todos los ingredientes. Reintenta antes de añadirlos.'
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    } finally { loading.value = false }
}

/**
 * creates a shopping list recipe from all selected ingredients
 */
async function createShoppingListRecipe() {
    if (loading.value || loadError.value || !validServings.value) return
    let api = new ApiApi()
    loading.value = true

    let shoppingListRecipe = {
        recipe: props.recipe.id,
        servings: servings.value,
    } as ShoppingListRecipe

    if (props.mealPlan && props.mealPlan.id) {
        shoppingListRecipe.mealplan = props.mealPlan.id!
    }

    let shoppingListEntries = {
        entries: [],
        shoppingListsIds: selectedShoppingLists.value.map(sl => sl.id!)
    } as ShoppingListEntryBulkCreate

    dialogRecipes.value.forEach(dialogRecipe => {
        dialogRecipe.entries.forEach(entry => {
            if (entry.checked) {
                shoppingListEntries.entries.push({
                    amount: entry.amount * (servings.value / (recipe.value.servings ? recipe.value.servings : 1)),
                    foodId: entry.food ? entry.food.id! : null,
                    unitId: entry.unit ? entry.unit.id! : null,
                    ingredientId: entry.ingredient ? entry.ingredient.id! : null,
                })
            }
        })
    })

    try {
        const slr = await api.apiShoppingListRecipeCreate({shoppingListRecipe})
        await api.apiShoppingListRecipeBulkCreateEntriesCreate({id: slr.id!, shoppingListEntryBulkCreate: shoppingListEntries})
        useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS)
        dialog.value = false
        emit('created')
    } catch (err) { useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err) }
    finally { loading.value = false }

}

</script>

<style scoped>

</style>
