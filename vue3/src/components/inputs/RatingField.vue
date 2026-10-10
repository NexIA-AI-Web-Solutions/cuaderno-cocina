<template>
    <v-input :label="$t('Rating')">
        <template #prepend v-if="$slots.prepend">
            <slot name="prepend">
            </slot>
        </template>

        <v-rating v-model="model"></v-rating>

         <template #append v-if="$slots.append">
            <slot name="append">
            </slot>
        </template>
    </v-input>
</template>

<script setup lang="ts">

const model = defineModel<number>({required: true})

</script>


<style scoped>

</style>
