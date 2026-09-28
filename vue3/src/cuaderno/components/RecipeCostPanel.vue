<template>
    <v-card class="mt-2 cost-card" v-if="recipeId">
        <v-card-title class="text-h6">Coste de ingredientes</v-card-title>
        <v-card-text>
            <div v-if="loading">Calculando…</div>
            <div v-else-if="error" class="text-error">{{ error }}</div>
            <template v-else-if="cost">
                <p v-if="cost.status === 'complete'" class="text-h5 mb-1">
                    {{ formatMoney(cost.display) }} {{ cost.currency }}
                </p>
                <p v-else class="text-h6 mb-1">Coste incompleto</p>
                <p v-if="cost.per_serving && cost.status === 'complete'">
                    Por ración ({{ cost.servings }}): {{ formatMoney(cost.per_serving) }} {{ cost.currency }}
                </p>
                <p v-if="cost.status !== 'complete'">
                    Subtotal conocido: {{ cost.known_subtotal == null ? "—" : formatMoney(cost.known_subtotal) }}
                    {{ cost.currency }}. Los precios que faltan no se cuentan como cero.
                </p>
                <p class="text-medium-emphasis">
                    Estimación de ingredientes para las raciones indicadas. No cambia la receta guardada.
                </p>
                <ul v-if="cost.warnings && cost.warnings.length">
                    <li v-for="warning in cost.warnings" :key="warning">{{ warningLabel(warning) }}</li>
                </ul>
            </template>
        </v-card-text>
    </v-card>
</template>

<script setup lang="ts">
import {onMounted, ref, watch} from "vue"
import {getCookie} from "@/utils/cookie"

const props = defineProps<{
    recipeId: number
    servings: number
}>()

const cost = ref<any>(null)
const loading = ref(false)
const error = ref("")

function formatMoney(value: string | number | null) {
    if (value == null) {
        return "—"
    }
    return Number(value).toLocaleString("es-ES", {minimumFractionDigits: 2, maximumFractionDigits: 2})
}

function warningLabel(code: string) {
    const labels: Record<string, string> = {
        precio_desconocido: "Falta el precio de algún ingrediente.",
        sin_formato: "Algún ingrediente no tiene formato de compra.",
        needs_conversion: "Falta una conversión de unidades.",
        sin_unidad: "Falta la unidad de algún ingrediente.",
        cantidad_desconocida: "Hay una cantidad vacía.",
        excluido: "Hay una línea excluida del coste (por ejemplo, al gusto).",
    }
    return labels[code] || code
}

async function load() {
    loading.value = true
    error.value = ""
    try {
        const response = await fetch(`/api/cuaderno/recipes/${props.recipeId}/cost/?servings=${props.servings}`, {
            credentials: "same-origin",
            headers: {"X-CSRFToken": getCookie("csrftoken")},
        })
        if (!response.ok) {
            error.value = "No se ha podido calcular el coste."
            cost.value = null
            return
        }
        cost.value = await response.json()
    } catch {
        error.value = "No se ha podido calcular el coste."
    } finally {
        loading.value = false
    }
}

onMounted(load)
watch(() => [props.recipeId, props.servings], load)
</script>

<style scoped>
@media print {
    .cost-card {
        break-inside: avoid;
    }
}
</style>
