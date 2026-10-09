<template>
    <section class="cuaderno-native-recipe-access mb-4" :aria-busy="access === 'loading'">
        <v-alert type="info" variant="tonal" role="status" class="mb-3">{{ message }}</v-alert>
        <v-btn v-if="showBack" :to="{name: 'StartPage'}" variant="tonal" min-height="44" prepend-icon="$recipes">Volver a recetas</v-btn>
    </section>
</template>

<script setup lang="ts">
import {computed, type PropType} from 'vue'
import {nativeRecipeWriteMessage, type NativeRecipeWriteAccess} from '@/cuaderno/nativeRecipeWriteUi'

const props = defineProps({
    access: {type: String as PropType<NativeRecipeWriteAccess>, default: 'unavailable'},
    showBack: {type: Boolean, default: true},
})
const message = computed(() => nativeRecipeWriteMessage(props.access))
</script>
