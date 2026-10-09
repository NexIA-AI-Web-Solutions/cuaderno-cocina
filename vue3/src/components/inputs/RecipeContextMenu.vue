<template>
    <v-btn v-bind="props" icon="fa-solid fa-ellipsis-v" variant="plain" :size="props.size" class="d-print-none">
        <v-icon icon="fa-solid fa-ellipsis-v"></v-icon>
        <v-menu activator="parent" close-on-content-click>
            <v-list density="compact" class="pt-1 pb-1">
                <v-list-item v-if="useUserPreferenceStore().canWriteNativeRecipes" :to="{ name: 'ModelEditPage', params: {model: 'recipe', id: recipe.id} }" prepend-icon="$edit">
                    {{ $t('Edit') }}
                </v-list-item>
                <v-list-item prepend-icon="$mealplan" @click="mealPlanDialog = true">
                    {{ $t('Add_to_Plan') }}
                </v-list-item>
                <v-list-item prepend-icon="$shopping" link>
                    {{ $t('Add_to_Shopping') }}
                    <add-to-shopping-dialog :recipe="props.recipe"></add-to-shopping-dialog>
                </v-list-item>
                <v-list-item :to="{ name: 'PropertyEditorPage', query: {recipe: recipe.id} }" prepend-icon="fa-solid fa-table" link>
                    {{ $t('Property_Editor') }}
                </v-list-item>
                <v-list-item prepend-icon="$pantry" @click="addToPantry()" :loading="pantryLoading" link>
                    {{ $t('Pantry') }}
                </v-list-item>
                <v-list-item prepend-icon="fa-solid fa-share-nodes" link>
                    {{ $t('Share') }}
                    <recipe-share-dialog :recipe="props.recipe"></recipe-share-dialog>
                </v-list-item>
                <v-list-item v-if="useUserPreferenceStore().canWriteNativeRecipes" @click.stop="duplicateRecipe()" prepend-icon="$copy" :disabled="duplicateLoading">
                    {{ $t('Duplicate') }}
                    <template #append>
                        <v-progress-circular v-if="duplicateLoading" indeterminate size="small"></v-progress-circular>
                    </template>
                </v-list-item>
                <v-list-item v-if="canCreateVariant && useUserPreferenceStore().canWriteNativeRecipes" @click.stop="duplicateRecipe(true)" prepend-icon="fa-solid fa-code-branch" :disabled="duplicateLoading">Crear variante vinculada</v-list-item>
                <v-list-item :to="{ name: 'RecipeViewPage', params: { id: recipe.id}, query: {print: 'true', servings: props.servings} }" :active="false" target="_blank"
                             prepend-icon="fa-solid fa-print">
                    {{ $t('Print') }}
                </v-list-item>
            </v-list>
        </v-menu>
    </v-btn>

    <model-edit-dialog model="MealPlan" :itemDefaults="{recipe: recipe, servings: recipe.servings}" :close-after-create="false" :close-after-save="false"
                       v-model="mealPlanDialog"></model-edit-dialog>

    <pantry-booking-dialog booking-mode="add" v-model="pantryDialog" :food-id="pantryFoodId"></pantry-booking-dialog>
    <v-dialog :model-value="variantCopy !== null" max-width="560" persistent>
        <v-card title="La copia ya está creada">
            <v-card-text><p>No se pudo guardar el vínculo con la receta de origen. Puedes volver a guardar solo el vínculo o abrir la copia; no se creará otra receta.</p><v-alert v-if="variantError" type="error" role="alert" class="mt-3">{{ variantError }}</v-alert></v-card-text>
            <v-card-actions class="flex-wrap"><v-btn :disabled="duplicateLoading" @click="openVariantCopy">Abrir copia sin vínculo</v-btn><v-btn color="primary" :loading="duplicateLoading" @click="retryVariantLink">Guardar vínculo</v-btn></v-card-actions>
        </v-card>
    </v-dialog>

</template>

<script setup lang="ts">
import {nextTick, PropType, ref} from 'vue'
import {ApiApi, Recipe, RecipeFlat, RecipeOverview, RecipeRequest} from "@/openapi";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";
import RecipeShareDialog from "@/components/dialogs/RecipeShareDialog.vue";
import AddToShoppingDialog from "@/components/dialogs/AddToShoppingDialog.vue";
import {ErrorMessageType, MessageType, useMessageStore} from "@/stores/MessageStore.ts";
import {useRouter} from "vue-router";
import {useFileApi} from "@/composables/useFileApi.ts";
import {useI18n} from "vue-i18n";
import PantryBookingDialog from "@/components/dialogs/PantryBookingDialog.vue";
import {planningRequest, type RecipeExtras} from '@/cuaderno/planningApi';
import {useUserPreferenceStore} from '@/stores/UserPreferenceStore';
import {nativeRecipeWriteMessage} from '@/cuaderno/nativeRecipeWriteUi';

const router = useRouter()
const {t} = useI18n()
const {updateRecipeImage} = useFileApi()

const props = defineProps({
    recipe: {type: Object as PropType<Recipe | RecipeOverview>, required: true},
    servings: {type: Number, default: undefined},
    size: {type: String, default: 'medium'},
    canCreateVariant: {type: Boolean, default: false},
})

const mealPlanDialog = ref(false)
const duplicateLoading = ref(false)
const pantryDialog = ref(false)
const pantryLoading = ref(false)
const pantryFoodId = ref<number | undefined>(undefined)
const variantCopy = ref<number | null>(null)
const variantOrigin = ref<number | null>(null)
const variantError = ref('')
function ensureCanWriteRecipes() {
    const store = useUserPreferenceStore()
    if (store.canWriteNativeRecipes) return true
    useMessageStore().addMessage(MessageType.WARNING, {title: 'Permisos de recetas', text: nativeRecipeWriteMessage(store.nativeRecipeWriteAccess)}, 8000)
    return false
}
async function linkVariant(id: number, origin: number) {
    if (!useUserPreferenceStore().canWriteNativeRecipes) throw new Error(nativeRecipeWriteMessage(useUserPreferenceStore().nativeRecipeWriteAccess))
    const extras = await planningRequest<RecipeExtras>(`recipes/${id}/extras/`)
    if (!useUserPreferenceStore().canWriteNativeRecipes) throw new Error(nativeRecipeWriteMessage(useUserPreferenceStore().nativeRecipeWriteAccess))
    await planningRequest(`recipes/${id}/extras/`, 'PUT', {revision: extras.revision, variant_of: origin})
}
function openVariantCopy() {
    const id = variantCopy.value; variantCopy.value = null
    if (id !== null) router.push({name: 'RecipeViewPage', params: {id}})
}
async function retryVariantLink() {
    if (!useUserPreferenceStore().canWriteNativeRecipes) return
    if (variantCopy.value === null || variantOrigin.value === null || duplicateLoading.value) return
    duplicateLoading.value = true; variantError.value = ''
    try {await linkVariant(variantCopy.value, variantOrigin.value); openVariantCopy()}
    catch (error) {variantError.value = (error as Error).message}
    finally {duplicateLoading.value = false}
}

/**
 * create a duplicate of the recipe by pulling its current data and creating a new recipe with the same data
 */
function duplicateRecipe(linkedVariant = false) {
    if (!useUserPreferenceStore().canWriteNativeRecipes) return
    if (duplicateLoading.value || (linkedVariant && !props.canCreateVariant)) return
    const originId = props.recipe.id!
    let api = new ApiApi()
    duplicateLoading.value = true
    api.apiRecipeRetrieve({id: props.recipe.id!}).then(originalRecipe => {
        if (!ensureCanWriteRecipes()) {duplicateLoading.value = false; return}

        const {id: _recipeId, ...recipeFields} = originalRecipe
        const recipe: RecipeRequest = {
            ...recipeFields,
            name: `${originalRecipe.name}(${t('Copy')})`,
            steps: originalRecipe.steps.map(({id: _stepId, ingredients, ...step}) => ({
                ...step,
                ingredients: ingredients.map(({id: _ingredientId, ...ingredient}) => ingredient),
            })),
            properties: originalRecipe.properties?.map(({id: _propertyId, ...property}) => property),
        }

        api.apiRecipeCreate({recipe: recipe}).then(async newRecipe => {
            if (!ensureCanWriteRecipes()) {
                duplicateLoading.value = false
                return router.push({name: 'RecipeViewPage', params: {id: newRecipe.id!}})
            }
            if (linkedVariant) {
                try {await linkVariant(newRecipe.id!, originId)}
                catch (error) {
                    variantCopy.value = newRecipe.id!; variantOrigin.value = originId; variantError.value = (error as Error).message; duplicateLoading.value = false
                    return
                }
            }

            if (originalRecipe.image && ensureCanWriteRecipes()) {
                updateRecipeImage(newRecipe.id!, null, originalRecipe.image).then(r => {
                    router.push({name: 'RecipeViewPage', params: {id: newRecipe.id!}})
                }).catch(err => {
                    useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
                    duplicateLoading.value = false
                })
            } else {
                router.push({name: 'RecipeViewPage', params: {id: newRecipe.id!}})
            }
        }).catch(err => {
            useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
            duplicateLoading.value = false
        })
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        duplicateLoading.value = false
    })
}

/**
 * create a food based on the recipe name (or re-use existing one) and open the pantry booking dialog
 */
function addToPantry() {
    const api = new ApiApi()
    if (props.recipe) {
        pantryLoading.value = true
        api.apiFoodCreate({food: {name: props.recipe.name}}).then(r => {
            pantryFoodId.value = r.id
            pantryDialog.value = true
        }).catch(err => {
            useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
        }).finally(() => {
            pantryLoading.value = false
        })
    }
}

</script>


<style scoped>

</style>
