<template>
    <v-container class="pb-0">
        <v-btn :to="{name: 'CuadernoListaPage'}" variant="text" prepend-icon="fa-solid fa-list-check" min-height="44">
            Vista rápida de la lista
        </v-btn>
    </v-container>
    <shopping-list-view></shopping-list-view>
</template>

<script lang="ts" setup>

import ShoppingListView from "@/components/display/ShoppingListView.vue";

</script>

<style scoped>

</style>
