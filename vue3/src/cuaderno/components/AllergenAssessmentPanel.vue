<template>
    <section class="mt-3" :aria-label="title">
        <p class="font-weight-bold mb-1">{{ title }}</p>
        <v-progress-linear v-if="loading" indeterminate aria-label="Consultando alérgenos" />
        <v-alert v-if="error" type="error" role="alert" class="mt-2">{{ error }}</v-alert>
        <template v-else-if="!loading">
            <v-alert v-if="legacy" type="warning" role="status" class="mt-2">
                Información de alérgenos no congelada (desconocida).
            </v-alert>
            <p v-else :class="assessment?.assessment === 'declared' ? 'text-error' : 'text-medium-emphasis'">
                {{ allergenAssessmentLabel(assessment?.assessment) }}.
            </p>
            <p v-if="assessment?.unknown_ingredients" class="text-medium-emphasis">
                Hay ingredientes sin alimento identificable; su información de alérgenos es desconocida.
            </p>
            <v-list v-if="assessment?.foods.length" density="compact" class="allergen-list">
                <v-list-item v-for="food in assessment.foods" :key="food.id" :title="food.name">
                    <template #subtitle>
                        <span v-if="food.declarations.length">
                            {{ food.declarations.map(declaration => `${declaration.name}: ${declaration.state === 'declared' ? 'declarado' : 'desconocido'}${allergenDeclarationAuditLabel(declaration) ? ` (${allergenDeclarationAuditLabel(declaration)})` : ''}`).join(' · ') }}
                        </span>
                        <span v-else>Sin declaraciones registradas · estado desconocido</span>
                    </template>
                </v-list-item>
            </v-list>
            <p v-else-if="!legacy" class="text-medium-emphasis">No hay alimentos con declaraciones registradas.</p>
        </template>
        <v-alert type="warning" variant="tonal" role="note" class="mt-2">
            {{ ALLERGEN_SAFETY_NOTICE }}
        </v-alert>
    </section>
</template>

<script setup lang="ts">
import {
    ALLERGEN_SAFETY_NOTICE,
    allergenAssessmentLabel,
    allergenDeclarationAuditLabel,
    type AllergenAssessment,
} from '@/cuaderno/allergenUi'

withDefaults(defineProps<{
    assessment: AllergenAssessment | null
    source: 'food' | 'recipe' | 'snapshot'
    title: string
    loading?: boolean
    error?: string
    legacy?: boolean
}>(), {
    loading: false,
    error: '',
    legacy: false,
})
</script>

<style scoped>
.allergen-list {
    overflow-wrap: anywhere;
}
</style>
