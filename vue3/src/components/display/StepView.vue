<template>
    <v-card>
        <v-card-title>
            <v-row>
                <v-col>
                    <span v-if="step.name">{{ step.name }}</span>
                    <span v-else>{{ $t('Step') }} {{ props.stepNumber }}</span>
                </v-col>
                <v-col class="text-right">
                    <v-btn-group density="compact" variant="tonal" class="d-print-none">
                        <v-btn size="small" color="info" v-if="step.time != undefined && step.time > 0" @click="timerRunning = true"><i
                            class="fas fa-stopwatch mr-1 fa-fw"></i> {{ step.time }}
                        </v-btn>
                        <v-btn size="small" color="success" v-if="hasDetails" @click="stepChecked = !stepChecked"><i class="fas fa-fw"
                                                                                                                     :class="{'fa-check': !stepChecked, 'fa-times': stepChecked}"></i>
                        </v-btn>
                    </v-btn-group>
                </v-col>
            </v-row>
        </v-card-title>
        <template v-if="!stepChecked">
            <timer :seconds="step.time != undefined ? step.time*60 : 0" @stop="timerRunning = false" v-if="timerRunning"></timer>
            <v-card-text v-if="step.ingredients.length > 0 || step.instruction != ''">
                <v-row>
                    <v-col :cols="(useUserPreferenceStore().isPrintMode) ? 6 : 12" md="6" v-if="step.ingredients.length > 0 && step.showIngredientsTable">
                        <ingredients-table v-model="step.ingredients" :ingredient-factor="ingredientFactor"></ingredients-table>
                    </v-col>
                    <v-col :cols="(useUserPreferenceStore().isPrintMode) ? 6 : 12" md="6" class="markdown-body">
                        <instructions :instructions_html="step.instructionsMarkdown" :ingredient_factor="ingredientFactor"></instructions>
                    </v-col>
                </v-row>
            </v-card-text>

            <template v-if="step.stepRecipe">
                <v-card class="ma-2 border-md">
                    <v-card-title>
                        <v-icon icon="$recipes"></v-icon>
                        {{ step.stepRecipeData.name }}
                        <v-btn icon="fa-solid fa-up-right-from-square" size="x-small" :to="{name: 'RecipeViewPage', params: {id: step.stepRecipeData.id}}" target="_blank" variant="plain"></v-btn>
                    </v-card-title>
                    <v-card-text class="mt-1" v-for="(subRecipeStep, subRecipeStepIndex) in step.stepRecipeData.steps" :key="subRecipeStep.id">
                        <step-view v-model="step.stepRecipeData.steps[subRecipeStepIndex]" :step-number="Number(subRecipeStepIndex) + 1" :ingredientFactor="ingredientFactor"></step-view>
                    </v-card-text>
                </v-card>
            </template>
            <template v-if="step.file">
                <v-img :src="stepPreview" v-if="step.file.preview"></v-img>
                <a :href="stepDownload" v-else>{{ $t('Download') }}</a>
            </template>
        </template>

    </v-card>
</template>

<script setup lang="ts">
import {computed, inject, ref, type Ref} from 'vue'
import IngredientsTable from "@/components/display/IngredientsTable.vue";
import {Step} from "@/openapi";

import Instructions from "@/components/display/Instructions.vue";
import Timer from "@/components/display/Timer.vue";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";
import {RECIPE_SHARE_TOKEN_KEY, sharedMediaUrl} from "@/cuaderno/sharedMedia.ts";

const step = defineModel<Step>({required: true})
const shareToken = inject<Readonly<Ref<string | undefined>>>(RECIPE_SHARE_TOKEN_KEY)

const props = defineProps({
    stepNumber: {
        type: Number,
        required: false,
        default: 1
    },
    ingredientFactor: {
        type: Number,
        required: true,
    },
})

const timerRunning = ref(false)
const stepChecked = ref(false)

const stepPreview = computed(() => sharedMediaUrl(step.value.file?.preview, shareToken?.value, window.location.origin))
const stepDownload = computed(() => sharedMediaUrl(step.value.file?.fileDownload, shareToken?.value, window.location.origin))

const hasDetails = computed(() => {
    return step.value.ingredients.length > 0 || (step.value.instruction != undefined && step.value.instruction.length > 0) || step.value.stepRecipeData != undefined || step.value.file != undefined
})

</script>

<style scoped>

</style>
