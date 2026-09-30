<template>
    <v-card class="mt-2 cost-card" v-if="recipeId">
        <v-card-title class="text-h6">Costes y presupuesto</v-card-title>
        <v-card-text>
            <section aria-labelledby="ingredient-cost-title">
                <h2 id="ingredient-cost-title" class="text-subtitle-1 font-weight-bold mb-2">Coste de ingredientes</h2>
                <div v-if="loadingCost" role="status">Calculando…</div>
                <div v-else-if="costError" class="text-error" role="alert">{{ costError }}</div>
                <template v-else-if="cost">
                    <p v-if="cost.status === 'complete'" class="text-h5 mb-1">
                        {{ financeMoneyLabel(cost.display, cost.currency) }}
                    </p>
                    <p v-else class="text-h6 mb-1">Coste incompleto</p>
                    <p v-if="cost.per_serving && cost.status === 'complete'">
                        Por ración ({{ cost.servings }}): {{ financeMoneyLabel(cost.per_serving, cost.currency) }}
                    </p>
                    <p v-if="cost.status !== 'complete'">
                        Subtotal conocido:
                        {{ cost.known_subtotal == null ? "—" : financeMoneyLabel(cost.known_subtotal, cost.currency) }}.
                        Los precios que faltan no se cuentan como cero.
                    </p>
                    <p class="text-medium-emphasis">
                        Estimación de ingredientes para las raciones indicadas. No cambia la receta guardada.
                    </p>
                    <ul v-if="cost.warnings?.length">
                        <li v-for="warning in cost.warnings" :key="warning">{{ costWarningLabel(warning) }}</li>
                    </ul>
                </template>
            </section>

            <v-divider class="my-4" />

            <IngredientYieldPanel :recipe-id="recipeId" @saved="loadAll" />

            <v-divider class="my-4" />

            <section aria-labelledby="recipe-finance-title">
                <h2 id="recipe-finance-title" class="text-subtitle-1 font-weight-bold mb-2">Presupuesto y venta por ración</h2>
                <p v-if="loadingFinance" role="status">Cargando datos financieros…</p>
                <p v-if="financeError" class="text-error" role="alert">{{ financeError }}</p>
                <template v-if="finance">
                    <p class="text-body-2 mb-3">
                        Política {{ policyLabel }}. Precio y presupuesto se expresan con la misma política.
                    </p>
                    <v-row dense>
                        <v-col cols="12" sm="6">
                            <p><strong>Coste de ingredientes/ración:</strong> {{ financeMoneyLabel(finance.ingredient_cost_per_serving) }}</p>
                            <p><strong>Precio de venta/ración:</strong> {{ financeMoneyLabel(finance.selling_price_per_serving) }}</p>
                            <p><strong>Presupuesto/persona:</strong> {{ financeMoneyLabel(finance.budget_per_person) }}</p>
                        </v-col>
                        <v-col cols="12" sm="6">
                            <p><strong>Diferencia frente al coste:</strong> {{ financeMoneyLabel(finance.difference_per_serving) }}</p>
                            <p><strong>Margen hasta presupuesto:</strong> {{ financeMoneyLabel(finance.budget_gap_per_person) }}</p>
                            <p><strong>Porcentaje de coste de materia:</strong> {{ financeRatioLabel(finance.food_cost_ratio) }}</p>
                        </v-col>
                    </v-row>
                    <p class="text-medium-emphasis mt-2">
                        La diferencia compara referencias por ración; no es beneficio neto.
                    </p>
                    <ul v-if="finance.warnings?.length" class="mb-3">
                        <li v-for="warning in finance.warnings" :key="warning">{{ financeWarningLabel(warning) }}</li>
                    </ul>
                </template>

                <v-alert v-if="edition === 'esencial' && finance" type="info" variant="tonal" class="my-3">
                    Puedes consultar los datos existentes. La edición se habilita en Profesional e Integral.
                </v-alert>

                <form v-if="canEditFinance" @submit.prevent="saveFinance" class="mt-3">
                    <v-row dense>
                        <v-col cols="12" sm="6">
                            <v-text-field
                                :model-value="sellingPriceInput"
                                :label="`Precio de venta por ración (${policyLabel})`"
                                inputmode="decimal"
                                autocomplete="off"
                                min-height="44"
                                :error-messages="financeErrors.selling_price_per_serving"
                                :disabled="savingFinance"
                                @update:model-value="value => updateFinanceField('selling', String(value ?? ''))"
                            />
                        </v-col>
                        <v-col cols="12" sm="6">
                            <v-text-field
                                :model-value="budgetInput"
                                :label="`Presupuesto por persona (${policyLabel})`"
                                inputmode="decimal"
                                autocomplete="off"
                                min-height="44"
                                :error-messages="financeErrors.budget_per_person"
                                :disabled="savingFinance"
                                @update:model-value="value => updateFinanceField('budget', String(value ?? ''))"
                            />
                        </v-col>
                    </v-row>
                    <p class="text-body-2 mb-2">Admite coma española y hasta cuatro decimales. Vacío significa desconocido; cero es un valor guardado.</p>
                    <v-btn type="submit" color="primary" min-height="44" :loading="savingFinance">Guardar presupuesto</v-btn>
                    <p v-if="saveMessage" class="mt-2" role="status">{{ saveMessage }}</p>
                </form>
            </section>
        </v-card-text>
    </v-card>
</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, ref, watch} from "vue"
import {cuadernoFetch, readJson} from "@/cuaderno/api"
import {apiError} from "@/cuaderno/forms"
import IngredientYieldPanel from "@/cuaderno/components/IngredientYieldPanel.vue"
import {
    financeBody,
    financeMoneyLabel,
    financeRatioLabel,
    financeWarningLabel,
    pricePolicyLabel,
    type FinanceErrors,
    type RecipeFinance,
} from "@/cuaderno/financeUi"

type CostResult = {
    status: string
    display: string | null
    per_serving: string | null
    known_subtotal: string | null
    servings: string
    currency: string
    warnings?: string[]
}

const props = defineProps<{
    recipeId: number
    servings: number
}>()

const cost = ref<CostResult | null>(null)
const finance = ref<RecipeFinance | null>(null)
const edition = ref("")
const loadingCost = ref(false)
const loadingFinance = ref(false)
const savingFinance = ref(false)
const costError = ref("")
const financeError = ref("")
const saveMessage = ref("")
const sellingPriceInput = ref("")
const budgetInput = ref("")
const financeErrors = ref<FinanceErrors>({})
const financeDirty = ref(false)
const formRevision = ref(0)
let formRecipeId: number | null = null
let requestGeneration = 0
let costController: AbortController | null = null
let financeController: AbortController | null = null
let saveController: AbortController | null = null

const canEditFinance = computed(() => ['profesional', 'integral'].includes(edition.value))
const policyLabel = computed(() => pricePolicyLabel(finance.value?.price_policy || ''))

function requestKey() {
    return `${props.recipeId}:${props.servings}`
}

function isCurrent(generation: number, key: string) {
    return generation === requestGeneration && key === requestKey()
}

function costWarningLabel(code: string) {
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

function replaceInputsFromFinance(value: RecipeFinance) {
    sellingPriceInput.value = value.selling_price_per_serving ?? ''
    budgetInput.value = value.budget_per_person ?? ''
    financeDirty.value = false
    financeErrors.value = {}
}

async function loadCost(generation: number, key: string, controller: AbortController) {
    const {ok, status, data} = await readJson(await cuadernoFetch(
        `/api/cuaderno/recipes/${props.recipeId}/cost/?servings=${encodeURIComponent(String(props.servings))}`,
        {signal: controller.signal},
    ))
    if (!isCurrent(generation, key) || controller.signal.aborted) return
    loadingCost.value = false
    if (!ok) {
        costError.value = apiError(status, data)
        return
    }
    cost.value = data as CostResult
}

async function loadFinance(generation: number, key: string, controller: AbortController) {
    const recipeAtLoad = props.recipeId
    const {ok, status, data} = await readJson(await cuadernoFetch(
        `/api/cuaderno/recipes/${recipeAtLoad}/finance/?servings=${encodeURIComponent(String(props.servings))}`,
        {signal: controller.signal},
    ))
    if (!isCurrent(generation, key) || controller.signal.aborted) return
    loadingFinance.value = false
    if (!ok || !data?.finance) {
        financeError.value = apiError(status, data)
        return
    }
    edition.value = String(data.edition || '')
    finance.value = data.finance as RecipeFinance
    if (!financeDirty.value && formRecipeId === recipeAtLoad) replaceInputsFromFinance(finance.value)
}

function loadAll() {
    const generation = ++requestGeneration
    const key = requestKey()
    costController?.abort()
    financeController?.abort()
    saveController?.abort()
    savingFinance.value = false

    if (formRecipeId !== props.recipeId) {
        formRecipeId = props.recipeId
        sellingPriceInput.value = ''
        budgetInput.value = ''
        financeDirty.value = false
        formRevision.value += 1
    }
    cost.value = null
    finance.value = null
    edition.value = ''
    costError.value = ''
    financeError.value = ''
    saveMessage.value = ''
    financeErrors.value = {}
    loadingCost.value = true
    loadingFinance.value = true
    costController = new AbortController()
    financeController = new AbortController()
    void loadCost(generation, key, costController)
    void loadFinance(generation, key, financeController)
}

function updateFinanceField(field: 'selling' | 'budget', value: string) {
    if (field === 'selling') sellingPriceInput.value = value
    else budgetInput.value = value
    financeDirty.value = true
    formRevision.value += 1
    financeErrors.value = {...financeErrors.value}
    delete financeErrors.value[field === 'selling' ? 'selling_price_per_serving' : 'budget_per_person']
    saveMessage.value = ''
}

async function saveFinance() {
    if (savingFinance.value || !canEditFinance.value) return
    const parsed = financeBody(sellingPriceInput.value, budgetInput.value)
    financeErrors.value = parsed.errors
    if (!parsed.body) {
        saveMessage.value = 'Revisa los importes antes de guardar.'
        return
    }
    const generation = requestGeneration
    const key = requestKey()
    const revision = formRevision.value
    const recipeAtSave = props.recipeId
    financeController?.abort()
    loadingFinance.value = false
    saveController?.abort()
    saveController = new AbortController()
    const controller = saveController
    savingFinance.value = true
    saveMessage.value = ''
    const {ok, status, data} = await readJson(await cuadernoFetch(
        `/api/cuaderno/recipes/${recipeAtSave}/finance/?servings=${encodeURIComponent(String(props.servings))}`,
        {method: 'PUT', body: JSON.stringify(parsed.body), signal: controller.signal},
    ))
    if (!isCurrent(generation, key) || controller.signal.aborted || recipeAtSave !== props.recipeId) return
    savingFinance.value = false
    if (!ok || !data?.finance) {
        saveMessage.value = apiError(status, data)
        return
    }
    if (revision !== formRevision.value) {
        saveMessage.value = 'Se guardó la versión enviada. Conservamos en el formulario tus cambios posteriores.'
        return
    }
    edition.value = String(data.edition || edition.value)
    finance.value = data.finance as RecipeFinance
    replaceInputsFromFinance(finance.value)
    saveMessage.value = 'Presupuesto guardado.'
}

watch(() => [props.recipeId, props.servings], loadAll, {immediate: true})
onBeforeUnmount(() => {
    ++requestGeneration
    costController?.abort()
    financeController?.abort()
    saveController?.abort()
})
</script>

<style scoped>
@media print {
    .cost-card {
        break-inside: avoid;
    }
}
</style>
