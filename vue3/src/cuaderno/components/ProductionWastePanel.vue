<template>
    <section class="mt-4 production-waste" aria-label="Merma teórica declarada">
        <h3 class="text-subtitle-1">Merma teórica declarada</h3>
        <p class="text-body-2 text-medium-emphasis">
            Cobertura: solo rendimientos declarados. Es una estimación incluida en las necesidades brutas;
            no registra un segundo consumo de existencias ni representa toda la merma real.
        </p>
        <v-alert v-if="!classification || classification.status === 'unknown'" type="info" variant="tonal" role="note" class="mt-2">
            La merma teórica es desconocida: no hay rendimientos declarados suficientes. No se inventa un valor cero.
        </v-alert>
        <v-alert v-else-if="classification.status === 'incomplete'" type="warning" variant="tonal" role="note" class="mt-2">
            La clasificación está incompleta porque faltan identidades o rendimientos congelados.
        </v-alert>
        <v-list v-if="classification?.lines.length" density="compact" class="waste-lines">
            <v-list-item v-for="(line, index) in classification.lines" :key="`${line.ingredient_id}:${index}`">
                <template #title>{{ line.food_name || `Ingrediente ${line.ingredient_id}` }}</template>
                <template #subtitle>
                    <span v-if="line.waste_quantity !== null">
                        Merma teórica: {{ line.waste_quantity }} {{ line.unit_name || '(unidad desconocida)' }} ·
                        cantidad comprada {{ line.purchased_quantity }} · cantidad útil {{ line.useful_quantity }} ·
                        rendimiento {{ line.yield_ratio }}
                    </span>
                    <span v-else>
                        Cantidad comprada {{ line.purchased_quantity }} {{ line.unit_name || '(unidad desconocida)' }} · rendimiento desconocido
                    </span>
                </template>
            </v-list-item>
        </v-list>
    </section>
</template>

<script setup lang="ts">
import type {ProductionWasteClassification} from '@/cuaderno/productionWasteUi'

defineProps<{classification: ProductionWasteClassification | null}>()
</script>

<style scoped>
.production-waste,
.waste-lines {
    overflow-wrap: anywhere;
}
</style>
