<template>
    <v-container>
        <header class="cuaderno-home-header">
            <div class="d-flex align-center ga-3">
                <h1 class="text-h4">{{ $t('Recipes') }}</h1>
                <v-chip v-if="totalRecipes >= 0" variant="tonal" color="secondary" :aria-label="`${$t('Recipes')}: ${totalRecipes}`">{{ totalRecipes }}</v-chip>
            </div>
            <v-btn v-if="totalRecipes > 0" min-height="44" rounded="lg" prepend-icon="$search" variant="tonal" :to="{name: 'SearchPage', params: {query: ''}}">{{ $t('View_Recipes') }}</v-btn>
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
    gap: 16px;
    margin-bottom: 24px;
}
.cuaderno-home-loading { max-width: 360px; padding-block: 16px; }
</style>
