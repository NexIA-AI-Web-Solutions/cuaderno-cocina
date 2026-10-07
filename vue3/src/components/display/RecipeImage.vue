<template>
    <v-img :class="{'cuaderno-recipe-placeholder': !props.recipe?.image}" :cover="props.recipe?.image ? cover : false" :style="{'height': height, 'width': width,}" color="recipeImagePlaceholderBg" :src="image" :alt="$t('Recipe_Image')" :rounded="props.rounded">
        <slot name="overlay">

        </slot>
    </v-img>
</template>

<script setup lang="ts">

import {computed, inject, PropType, type Ref} from "vue";
import {Recipe, RecipeOverview} from "@/openapi";
import recipeDefaultImage from '../../assets/cuaderno-recipe-placeholder.svg'
import {RECIPE_SHARE_TOKEN_KEY, sharedMediaUrl} from "@/cuaderno/sharedMedia";

const props = defineProps({
    recipe: {type: {} as PropType<Recipe | RecipeOverview | undefined>, required: false, default: undefined},
    height: {type: String},
    width: {type: String},
    cover: {type: Boolean, default: true},
    rounded: {type: [Boolean, String], default: false},
})

const shareToken = inject<Readonly<Ref<string | undefined>>>(RECIPE_SHARE_TOKEN_KEY)

const image = computed(() => {

    if (props.recipe != undefined && props.recipe.image != undefined) {
        return sharedMediaUrl(props.recipe.image, shareToken?.value, window.location.origin)
    } else {
        return recipeDefaultImage
    }
})

</script>

<style scoped>

</style>
