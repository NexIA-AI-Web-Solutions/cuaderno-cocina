<template>
    <template v-if="ingredient.isHeader">
        <span class="font-weight-bold">{{ ingredient.note}}</span>
    </template>
    <template v-else>
        <span v-if="!isZeroIngredientAmount(ingredient.amount)">{{ ingredientAmountLabel(ingredient.amount) }}</span>
        <span class="ms-1" v-if="ingredient.unit">{{ ingredient.unit.name}}</span>
        <span class="ms-1" v-if="ingredient.food">{{ ingredient.food.name}}</span>
    </template>
</template>


<script setup lang="ts">

import {Ingredient} from "@/openapi";
import {PropType} from "vue";
import {ingredientAmountLabel, isZeroIngredientAmount} from "@/utils/ingredient_amounts";

const props = defineProps({
    ingredient: {type: {} as PropType<Ingredient>, required: true}
})

</script>


<style scoped>

</style>
