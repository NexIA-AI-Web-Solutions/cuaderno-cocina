<template>
    <v-container>
        <header class="cuaderno-home-header">
            <div class="cuaderno-home-intro">
            <p class="cuaderno-home-eyebrow">TU CUADERNO DE COCINA</p>
            <div class="d-flex align-center ga-3">
                <h1 class="text-h4">{{ $t('Recipes') }}</h1>
                <v-chip v-if="totalRecipes >= 0" variant="tonal" color="secondary" :aria-label="`${$t('Recipes')}: ${totalRecipes}`">{{ totalRecipes }}</v-chip>
            </div>
            <p class="text-body-1 mt-2">Encuentra una receta y lleva tus ideas a la mesa.</p>
            </div>
            <div v-if="useUserPreferenceStore().canWriteNativeRecipes" class="cuaderno-home-actions">
                <v-btn min-height="44" rounded="lg" color="primary" variant="flat" prepend-icon="$add" :to="{name: 'ModelEditPage', params: {model: 'recipe'}}">{{ $t('Create Recipe') }}</v-btn>
                <v-btn min-height="44" rounded="lg" variant="text" prepend-icon="$import" :to="{name: 'RecipeImportPage'}">{{ $t('Import') }}</v-btn>
            </div>
            <form class="cuaderno-home-search" role="search" aria-label="Buscar recetas" @submit.prevent="searchRecipes">
                <div class="cuaderno-home-search-field">
                    <label for="cuaderno-recipe-search" class="cuaderno-home-search-label">Buscar en tus recetas</label>
                    <v-text-field id="cuaderno-recipe-search" v-model="recipeQuery" type="search" placeholder="Nombre de la receta" prepend-inner-icon="$search" variant="outlined" bg-color="surface" rounded="lg" hide-details clearable></v-text-field>
                </div>
                <v-btn type="submit" min-height="56" color="secondary" rounded="lg" variant="flat">{{ $t('Search') }}</v-btn>
            </form>
            <v-btn v-if="totalRecipes > 0" min-height="44" rounded="lg" append-icon="fa-solid fa-arrow-right" variant="text" :to="{name: 'SearchPage'}">Ver todas las recetas</v-btn>
        </header>
        <div v-if="totalRecipes < 0 && !countError" role="status" aria-live="polite" class="cuaderno-home-loading">
            <p>{{ $t('Loading') }}</p>
            <v-skeleton-loader type="card" max-width="360"></v-skeleton-loader>
        </div>
        <v-alert v-if="countError" role="alert" type="error" variant="tonal" class="mb-4">
            {{ $t('LoadRecipesFailure') }}
            <v-btn variant="text" min-height="44" @click="loadRecipeCount">{{ $t('Refresh') }}</v-btn>
        </v-alert>
        <horizontal-meal-plan-window v-if="useUserPreferenceStore().deviceSettings.start_showMealPlan"></horizontal-meal-plan-window>

        <v-card v-if="totalRecipes == 0" class="mt-5 mb-5">
            <v-card-title class="text-center"><i class="fa-solid fa-eye-slash"></i> {{ $t('search_no_recipes') }}</v-card-title>
            <v-card-text>
                <native-recipe-access-notice v-if="!useUserPreferenceStore().canWriteNativeRecipes" :access="useUserPreferenceStore().nativeRecipeWriteAccess" :show-back="false" />
                <v-card
                    v-if="useUserPreferenceStore().canWriteNativeRecipes"
                    :title="$t('Create Recipe')"
                    variant="outlined"
                    :to="{name: 'ModelEditPage', params: {model: 'Recipe'}}"
                    prepend-icon="$recipes"
                    append-icon="fa-solid fa-arrow-right"
                    class="mb-4">
                    <template #subtitle>
                        <p class="text-wrap">
                            {{ $t('CreateFirstRecipe') }}
                        </p>
                    </template>
                </v-card>

                <v-card
                    v-if="useUserPreferenceStore().canWriteNativeRecipes"
                    :title="$t('Import')"
                    variant="outlined"
                    :to="{name: 'RecipeImportPage', params: {}}"
                    prepend-icon="$import"
                    append-icon="fa-solid fa-arrow-right">
                    <template #subtitle>
                        <p class="text-wrap">
                            {{ $t('ImportFirstRecipe') }}
                        </p>
                    </template>
                </v-card>
            </v-card-text>
        </v-card>
        <template v-if="totalRecipes > 0">
            <horizontal-recipe-scroller :skeletons="4" mode="recent" v-if="totalRecipes > 10"></horizontal-recipe-scroller>
            <horizontal-recipe-scroller :skeletons="4" mode="new" v-if="totalRecipes > 10"></horizontal-recipe-scroller>
            <horizontal-recipe-scroller :skeletons="4" mode="keyword" v-if="totalRecipes > 10"></horizontal-recipe-scroller>
            <horizontal-recipe-scroller :skeletons="4" mode="random" v-if="totalRecipes > 0"></horizontal-recipe-scroller>
            <horizontal-recipe-scroller :skeletons="4" mode="created_by" v-if="totalRecipes > 10"></horizontal-recipe-scroller>
            <horizontal-recipe-scroller :skeletons="2" mode="rating" v-if="totalRecipes > 10"></horizontal-recipe-scroller>
            <horizontal-recipe-scroller :skeletons="4" mode="keyword" v-if="totalRecipes > 25"></horizontal-recipe-scroller>
            <horizontal-recipe-scroller :skeletons="4" mode="random" v-if="totalRecipes > 25"></horizontal-recipe-scroller>

        </template>


    </v-container>
</template>

<script setup lang="ts">
import {onBeforeUnmount, onMounted, ref} from "vue"
import {ApiApi} from "@/openapi"
import HorizontalRecipeScroller from "@/components/display/HorizontalRecipeWindow.vue"
import HorizontalMealPlanWindow from "@/components/display/HorizontalMealPlanWindow.vue"
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import {settleComponentRequest} from "@/utils/componentRequest";
import NativeRecipeAccessNotice from '@/cuaderno/components/NativeRecipeAccessNotice.vue';
import {useRouter} from 'vue-router';

const router = useRouter()
const recipeQuery = ref('')
function searchRecipes() {
    const query = (recipeQuery.value || '').trim()
    void router.push({name: 'SearchPage', query: query ? {query} : {}})
}
const totalRecipes = ref(-1)
const countError = ref(false)
const messageStore = useMessageStore()
let requestController: AbortController | undefined

function abortPendingRequest() {
    requestController?.abort()
    requestController = undefined
}

function loadRecipeCount() {
    abortPendingRequest()
    countError.value = false
    const controller = new AbortController()
    requestController = controller
    const api = new ApiApi()
    void settleComponentRequest(
        api.apiRecipeList({pageSize: 1}, {signal: controller.signal}),
        controller.signal,
        response => { totalRecipes.value = response.count },
        error => { countError.value = true; messageStore.addError(ErrorMessageType.FETCH_ERROR, error) },
    )
}

function restoreFromPageCache(event: PageTransitionEvent) {
    if (event.persisted) {
        loadRecipeCount()
    }
}

onMounted(() => {
    window.addEventListener('pagehide', abortPendingRequest)
    window.addEventListener('pageshow', restoreFromPageCache)
    loadRecipeCount()
})

onBeforeUnmount(() => {
    window.removeEventListener('pagehide', abortPendingRequest)
    window.removeEventListener('pageshow', restoreFromPageCache)
    abortPendingRequest()
})
</script>

<style scoped>
.cuaderno-home-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 20px;
    margin-bottom: 24px;
    padding: clamp(20px, 3vw, 32px);
    border: 1px solid rgba(var(--v-theme-primary), .18);
    border-radius: 24px;
    background: linear-gradient(120deg, rgba(var(--v-theme-primary), .08), rgba(var(--v-theme-surface), 1) 75%);
}
.cuaderno-home-intro { flex: 1 1 320px; }
.cuaderno-home-eyebrow { color: rgb(var(--v-theme-primary)); font-size: .75rem; font-weight: 700; letter-spacing: .12em; margin-bottom: 10px; }
.cuaderno-home-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.cuaderno-home-search { display: flex; align-items: flex-end; flex: 1 0 100%; gap: 12px; min-width: 0; }
.cuaderno-home-search-field { flex: 1; min-width: 0; }
.cuaderno-home-search-label { display: block; margin-bottom: 8px; font-weight: 600; font-size: .875rem; }
.cuaderno-home-search :deep(.v-input) { min-width: 0; }
@media (max-width: 599px) {
    .cuaderno-home-header { gap: 16px; padding: 20px 16px; border-radius: 18px; }
    .cuaderno-home-search { flex-wrap: wrap; }
    .cuaderno-home-search-field { flex-basis: 100%; }
    .cuaderno-home-search > .v-btn { width: 100%; min-height: 44px !important; }
}
.cuaderno-home-loading { max-width: 360px; padding-block: 16px; }
</style>
