<template>
    <v-container :class="{'ps-0 pe-0 pt-0': mobile}">
        <v-defaults-provider :defaults="(useUserPreferenceStore().isPrintMode ? {VCard: {variant: 'flat'}} : {})">


           <recipe-view v-model="recipe" :servings="servings"></recipe-view>

            <div class="mt-2" v-if="isShared && Object.keys(recipe).length > 0">
                <import-tandoor-dialog></import-tandoor-dialog>
            </div>
        </v-defaults-provider>

    </v-container>

</template>

<script setup lang="ts">
import {computed, onMounted, provide, ref, watch} from 'vue'
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
    const parsed = parseInt(value as string, 10)
    return parsed > 0 ? parsed : undefined
})

const recipe = ref({} as Recipe)

watch(() => props.id, () => {
    refreshData(props.id)
})

onMounted(() => {
    refreshData(props.id)
})

function refreshData(recipeId: string) {
    const api = new ApiApi()
    recipe.value = {} as Recipe
    const id = Number(recipeId)
    if (!Number.isInteger(id) || id <= 0) return

    let requestParameters: ApiRecipeRetrieveRequest = {id}
    if (isShared.value) {
        requestParameters.share = shareToken.value!
    }

    api.apiRecipeRetrieve(requestParameters).then(r => {
        recipe.value = r
        title.value = recipe.value.name

        setTimeout(() => {
            if (useUserPreferenceStore().isPrintMode) {
                window.print()
            }
        }, 500)

        if (useUserPreferenceStore().isAuthenticated) {
            api.apiViewLogCreate({viewLog: {recipe: Number(recipeId)} as ViewLog})
        }
    }).catch(err => {
        if (err.response.status == 403) {
            // TODO maybe redirect to login if fails with 403? or conflict with group/sapce system?
        } else {
            useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        }
    })
}

</script>

<style scoped>

</style>
