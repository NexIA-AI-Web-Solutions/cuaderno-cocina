<template>
    <v-container :class="{'ps-0 pe-0 pt-0': mobile}">
        <div v-if="loadingRecipe" role="status" aria-live="polite" class="pa-4">
            <p class="mb-3">Cargando receta…</p>
            <v-skeleton-loader type="article, image"></v-skeleton-loader>
        </div>
        <v-card v-else-if="recipeLoadError" class="ma-3 pa-5" variant="outlined" role="alert">
            <h1 class="text-h5 mb-3">{{ recipeLoadError === 'unavailable' ? 'Receta no disponible' : 'No se pudo cargar la receta' }}</h1>
            <p class="mb-4">{{ recipeLoadError === 'unavailable' ? 'Puede que la receta se haya eliminado o que tu cuenta no tenga acceso. Puedes buscar otra receta o volver a intentarlo.' : 'No hemos podido conectar con el recetario. Comprueba tu conexión y vuelve a intentarlo.' }}</p>
            <div class="d-flex flex-wrap ga-2">
                <v-btn color="primary" min-height="44" prepend-icon="fa-solid fa-rotate-right" @click="refreshData(props.id)">Reintentar</v-btn>
                <v-btn :to="{name: 'SearchPage'}" min-height="44" variant="tonal" prepend-icon="$search">Buscar recetas</v-btn>
                <v-btn :to="{name: 'StartPage'}" min-height="44" variant="text">Volver al inicio</v-btn>
            </div>
        </v-card>
        <v-defaults-provider v-else-if="recipe.id" :defaults="(useUserPreferenceStore().isPrintMode ? {VCard: {variant: 'flat'}} : {})">


           <recipe-view v-model="recipe" :servings="servings"></recipe-view>

            <div class="mt-2" v-if="isShared && Object.keys(recipe).length > 0">
                <import-tandoor-dialog></import-tandoor-dialog>
            </div>
        </v-defaults-provider>

    </v-container>

</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, provide, ref, watch} from 'vue'
import {ApiApi, ApiRecipeRetrieveRequest, Recipe, ViewLog} from "@/openapi";
import RecipeView from "@/components/display/RecipeView.vue";
import {useDisplay} from "vuetify";
import {useTitle, useUrlSearchParams} from "@vueuse/core";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import ImportTandoorDialog from "@/components/dialogs/ImportTandoorDialog.vue";
import {RECIPE_SHARE_TOKEN_KEY} from "@/cuaderno/sharedMedia";

const props = defineProps({
    id: {type: String, required: true}
})

const params = useUrlSearchParams('history')
const {mobile} = useDisplay()
const title = useTitle()

const shareToken = computed(() => typeof params.share === 'string' && params.share.length > 0 ? params.share : undefined)
const isShared = computed(() => shareToken.value !== undefined)
provide(RECIPE_SHARE_TOKEN_KEY, shareToken)

const servings = computed(() => {
    const value = params.servings
    if (!value) return undefined
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
})

const recipe = ref({} as Recipe)
const loadingRecipe = ref(false)
const recipeLoadError = ref<'unavailable' | 'failed' | null>(null)
let loadGeneration = 0
let loggedRecipeId: number | undefined
onBeforeUnmount(() => {loadGeneration++})

// On a deep link the recipe can arrive before user preferences. Log once when
// both are ready, including after authentication resolves asynchronously.
watch(() => [recipe.value.id, useUserPreferenceStore().isAuthenticated], () => {
    const id = recipe.value.id
    if (!id || !useUserPreferenceStore().isAuthenticated || loggedRecipeId === id) return
    loggedRecipeId = id
    new ApiApi().apiViewLogCreate({viewLog: {recipe: id} as ViewLog}).catch(err => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    })
})

watch(() => props.id, () => {
    refreshData(props.id)
})

onMounted(() => {
    refreshData(props.id)
})

function refreshData(recipeId: string) {
    const generation = ++loadGeneration
    const api = new ApiApi()
    recipe.value = {} as Recipe
    recipeLoadError.value = null
    loadingRecipe.value = true
    loggedRecipeId = undefined
    const id = Number(recipeId)
    if (!Number.isSafeInteger(id) || id <= 0) {
        loadingRecipe.value = false
        recipeLoadError.value = 'unavailable'
        title.value = 'Receta no disponible'
        return
    }

    let requestParameters: ApiRecipeRetrieveRequest = {id}
    if (isShared.value) {
        requestParameters.share = shareToken.value!
    }

    api.apiRecipeRetrieve(requestParameters).then(r => {
        if (generation !== loadGeneration) return
        recipe.value = r
        title.value = recipe.value.name

        setTimeout(() => {
            if (generation === loadGeneration && useUserPreferenceStore().isPrintMode) {
                window.print()
            }
        }, 500)

    }).catch(err => {
        if (generation !== loadGeneration) return
        recipeLoadError.value = [403, 404].includes(err?.response?.status) ? 'unavailable' : 'failed'
        title.value = recipeLoadError.value === 'unavailable' ? 'Receta no disponible' : 'No se pudo cargar la receta'
        if (recipeLoadError.value === 'failed') useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        if (generation === loadGeneration) loadingRecipe.value = false
    })
}

</script>

<style scoped>

</style>
