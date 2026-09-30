<template>
    <section :aria-labelledby="`price-impact-title-${recipeId}`">
        <h2 :id="`price-impact-title-${recipeId}`" class="text-subtitle-1 font-weight-bold mb-2">Cambios de precio</h2>
        <p class="text-body-2 mb-3">
            Compara las dos últimas versiones vigentes de un formato para esta receta y sus subelaboraciones.
            Los demás ingredientes conservan su precio actual. Los servicios confirmados no se recalculan.
        </p>
        <v-btn v-if="packages === null" variant="tonal" min-height="44" :loading="loadingPackages" @click="loadPackages">
            Elegir formato para comparar
        </v-btn>
        <template v-else>
            <p v-if="packages.length === 0">No hay formatos de referencia disponibles. Añádelos en «Formatos y precios».</p>
            <v-select
                v-else v-model="selectedPackage" :items="packages" item-value="id"
                :item-title="item => `${item.food_name} — ${item.label}`"
                label="Formato de referencia" clearable :disabled="loadingImpact"
            />
            <v-btn v-if="packages.length" color="primary" min-height="44" :loading="loadingImpact"
                   :disabled="selectedPackage === null || loadingImpact" @click="compare">
                Comparar precios
            </v-btn>
        </template>
        <p v-if="error" class="text-error mt-2" role="alert">{{ error }}</p>
        <div v-if="impact" class="mt-3" role="status" aria-live="polite">
            <p v-if="!impact.affected">Este formato no se utiliza al calcular el coste de la receta.</p>
            <v-row dense>
                <v-col cols="12" sm="6">
                    <p><strong>Con precio anterior:</strong> {{ costLabel(impact.before) }}</p>
                </v-col>
                <v-col cols="12" sm="6">
                    <p><strong>Con precio actual:</strong> {{ costLabel(impact.after) }}</p>
                </v-col>
            </v-row>
            <template v-if="impact.difference !== null">
                <p>Diferencia total: {{ financeMoneyLabel(impact.difference, impact.currency) }}</p>
                <p>Por ración: {{ financeMoneyLabel(impact.difference_per_serving, impact.currency) }}</p>
            </template>
            <p v-else>No se puede calcular la diferencia: falta un precio anterior o hay un coste incompleto. No equivale a cero.</p>
            <p class="text-body-2 text-medium-emphasis">
                Raciones: {{ impact.after.servings }}. Política {{ pricePolicyLabel(impact.price_policy) }}.
                Estimación de ingredientes, no beneficio neto. Consulta calculada en {{ impact.as_of }}.
            </p>
        </div>
    </section>
</template>

<script setup lang="ts">
import {onBeforeUnmount, ref, watch} from 'vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {financeMoneyLabel, pricePolicyLabel} from '@/cuaderno/financeUi'
import {packageSummaries, type PackageSummary} from '@/cuaderno/priceHistoryUi'
import {priceImpactEnvelope, priceImpactRequest, type ImpactSheet, type PriceImpact} from '@/cuaderno/priceImpactUi'

const props = defineProps<{recipeId: number; servings: number}>()
const packages = ref<PackageSummary[] | null>(null)
const selectedPackage = ref<number | null>(null)
const impact = ref<PriceImpact | null>(null)
const error = ref('')
const loadingPackages = ref(false)
const loadingImpact = ref(false)
let generation = 0
let controller: AbortController | null = null

function invalidate() {
    generation += 1
    controller?.abort()
    controller = null
    loadingPackages.value = false
    loadingImpact.value = false
    impact.value = null
    error.value = ''
}

watch(() => [props.recipeId, props.servings], () => {
    invalidate()
    // Catalog identity belongs to the active recipe/Space context. Do not
    // carry selected IDs into another recipe or reload without user action.
    packages.value = null
    selectedPackage.value = null
})
watch(selectedPackage, invalidate)
onBeforeUnmount(invalidate)

async function loadPackages() {
    if (loadingPackages.value || loadingImpact.value) return
    invalidate()
    const requestGeneration = generation
    const requestController = new AbortController()
    controller = requestController
    loadingPackages.value = true
    try {
        const result = await readJson(await cuadernoFetch('/api/cuaderno/packages/', {signal: requestController.signal}))
        if (requestGeneration !== generation) return
        if (!result.ok) { error.value = apiError(result.status, result.data); return }
        const rows = packageSummaries(result.data)
        if (rows === null) { error.value = 'El servidor devolvió formatos no válidos. Reintenta la consulta.'; return }
        packages.value = rows.filter(row => row.is_reference)
    } finally {
        if (requestGeneration === generation) loadingPackages.value = false
    }
}

async function compare() {
    if (loadingImpact.value || loadingPackages.value || selectedPackage.value === null) return
    const recipeId = props.recipeId
    const packageId = selectedPackage.value
    const servings = String(props.servings)
    const url = priceImpactRequest(recipeId, packageId, servings)
    if (url === null) { error.value = 'Selecciona un formato y unas raciones positivas válidas.'; return }
    invalidate()
    const requestGeneration = generation
    const requestController = new AbortController()
    controller = requestController
    loadingImpact.value = true
    try {
        const result = await readJson(await cuadernoFetch(url, {signal: requestController.signal}))
        if (requestGeneration !== generation) return
        if (!result.ok) { error.value = apiError(result.status, result.data); return }
        const payload = priceImpactEnvelope(result.data, recipeId, packageId, servings)
        if (payload === null) { error.value = 'La comparación recibida no corresponde a esta ficha. Reintenta la consulta.'; return }
        impact.value = payload
    } finally {
        if (requestGeneration === generation) loadingImpact.value = false
    }
}

function costLabel(sheet: ImpactSheet): string {
    return sheet.status === 'complete'
        ? financeMoneyLabel(sheet.unrounded, impact.value?.currency ?? 'EUR') : 'Coste incompleto'
}
</script>
