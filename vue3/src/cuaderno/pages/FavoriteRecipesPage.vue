<template>
    <v-container>
        <h1 class="text-h4 mb-2">Recetas favoritas</h1><p class="mb-5">Tu selección personal de recetas a las que tienes acceso.</p>
        <v-alert v-if="error" type="error" role="alert" class="mb-3">{{ error }}</v-alert>
        <v-progress-linear v-if="loading" indeterminate aria-label="Cargando favoritas" />
        <v-row><v-col v-for="recipe in recipes" :key="recipe.id" cols="12" sm="6" md="4"><v-card :to="{name: 'RecipeViewPage', params: {id: recipe.id}}"><v-img v-if="recipe.image" :src="recipe.image" :alt="recipe.name" height="180" cover /><v-card-title class="text-wrap">{{ recipe.name }}</v-card-title></v-card></v-col></v-row>
        <p v-if="!loading && !error && !recipes.length" class="my-5">Guarda recetas con el corazón de «Fotos, variantes y dietas» para encontrarlas aquí.</p>
        <div class="d-flex flex-wrap ga-2 mt-5"><v-btn :disabled="loading || page === 0" @click="page--; load()">Anterior</v-btn><span class="align-self-center">{{ count }} favoritas · página {{ page + 1 }}</span><v-btn :disabled="loading || (page + 1) * 50 >= count" @click="page++; load()">Siguiente</v-btn><v-btn variant="text" :disabled="loading" @click="load">Actualizar</v-btn></div>
    </v-container>
</template>
<script setup lang="ts">
import {onMounted, ref} from 'vue'
import {planningRequest} from '@/cuaderno/planningApi'
const recipes = ref<{id: number; name: string; image: string | null}[]>([]), count = ref(0), page = ref(0), loading = ref(false), error = ref('')
async function load() {
    loading.value = true; error.value = ''; recipes.value = []
    try {const data = await planningRequest<{count: number; results: typeof recipes.value}>(`favorites/?offset=${page.value * 50}&limit=50`); recipes.value = data.results; count.value = data.count}
    catch (failure) {error.value = (failure as Error).message} finally {loading.value = false}
}
onMounted(load)
</script>
