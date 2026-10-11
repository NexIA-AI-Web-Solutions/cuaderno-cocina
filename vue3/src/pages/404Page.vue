<script setup lang="ts">

</script>

<template>
<v-container class="cuaderno-not-found">
    <v-card class="pa-6 pa-sm-10 text-center" rounded="xl" variant="outlined">
        <v-chip color="secondary" variant="tonal" class="mb-4">404</v-chip>
        <h1 class="text-h4 mb-4">Página no encontrada</h1>
        <p class="text-body-1 mb-6">Esta dirección no existe o ha cambiado. Tu recetario sigue aquí: vuelve al inicio o busca una receta.</p>
        <div class="d-flex flex-wrap justify-center ga-3">
            <v-btn :to="{name: 'StartPage'}" color="primary" min-height="44" prepend-icon="$recipes">Volver al inicio</v-btn>
            <v-btn :to="{name: 'SearchPage'}" variant="tonal" min-height="44" prepend-icon="$search">Buscar recetas</v-btn>
        </div>
    </v-card>
</v-container>
</template>

<style scoped>
.cuaderno-not-found { max-width: 760px; padding-top: clamp(24px, 8vh, 96px); }
</style>
