<template>
    <v-container class="cuaderno-production-page">
        <v-btn :to="{name: 'MealPlanPage'}" variant="text" prepend-icon="fa-solid fa-calendar-days" min-height="44" class="mb-3">Ver planificación de menús</v-btn>
        <h1 class="text-h5 mb-3">Producción</h1>
        <p class="mb-4">
            Crear y confirmar un servicio no descuenta stock. Confirmar conserva sus necesidades y costes.
            Producir es una acción explícita: solo en Integral consume ingredientes de las existencias del hogar del servicio.
            Un alérgeno sin declarar no se trata como ausente.
        </p>
        <v-alert v-if="editionMessage" type="info" variant="tonal" class="mb-4" role="status">{{ editionMessage }}</v-alert>
        <v-alert v-if="notice" type="info" class="mb-4" role="status">{{ notice }}</v-alert>
        <v-alert v-if="productionEnabled && !canOperate" type="info" variant="tonal" class="mb-4" role="status">Modo Consulta: las fichas están disponibles solo para lectura.</v-alert>
        <div v-if="productionEnabled">
        <v-row class="no-print">
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title><h2 class="text-h6">Ficha desde recetas</h2></v-card-title>
                    <v-card-text>
                        <p class="text-body-2 mb-3">Calcula las necesidades de las recetas con sus cantidades guardadas. Las subrecetas necesitan un rendimiento de salida declarado.</p>
                        <v-model-select v-model="selectedRecipes" model="Recipe" label="Recetas" multiple chips search-on-load :disabled="!canOperate || calculatingRecipes" />
                        <v-btn color="primary" :loading="calculatingRecipes" :disabled="!canOperate || !selectedRecipes.length" min-height="44" @click="calculateRecipes">Calcular necesidades</v-btn>
                        <p class="mt-2" role="status">{{ recipeMessage }}</p>
                        <v-alert v-for="(warning, index) in recipeWarnings" :key="index" type="warning" class="mt-3" role="status">{{ warning }}</v-alert>
                        <v-list v-if="recipeNeeds.length">
                            <v-list-item v-for="line in recipeNeeds" :key="line.name" :title="line.name" :subtitle="line.quantity" />
                        </v-list>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card>
                    <v-card-title><h2 class="text-h6">Rendimiento de subreceta</h2></v-card-title>
                    <v-card-text>
                        <p class="text-body-2 mb-3">Indica cuánto producto terminado obtienes al elaborar una vez la receta completa. No equivale al número de raciones.</p>
                        <v-model-select v-model="output.recipe" model="Recipe" label="Receta" search-on-load :disabled="!canOperate || savingYield" />
                        <v-text-field v-model="output.quantity" label="Cantidad obtenida" inputmode="decimal" :disabled="!canOperate || savingYield" />
                        <v-model-select v-model="output.unit" model="Unit" label="Unidad de salida" search-on-load :disabled="!canOperate || savingYield" />
                        <v-btn color="primary" :loading="savingYield" :disabled="!canOperate" min-height="44" @click="saveYield">Guardar rendimiento</v-btn>
                        <p class="mt-2" role="status">{{ yieldMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title><h2 class="text-h6">Servicio</h2></v-card-title>
                    <v-card-text>
                        <v-text-field v-model="service.title" label="Nombre" :disabled="!canOperate || savingService" />
                        <v-text-field v-model="service.date" label="Fecha del servicio" type="date" :disabled="!canOperate || savingService" />
                        <v-row dense>
                            <v-col cols="12" sm="4"><v-text-field v-model="service.baseCovers" label="Comensales previstos" inputmode="numeric" :disabled="!canOperate || savingService" /></v-col>
                            <v-col cols="6" sm="4"><v-text-field v-model="service.extra" label="Altas" inputmode="numeric" :disabled="!canOperate || savingService" /></v-col>
                            <v-col cols="6" sm="4"><v-text-field v-model="service.cancelled" label="Cancelaciones" inputmode="numeric" :disabled="!canOperate || savingService" /></v-col>
                        </v-row>
                        <p class="text-body-2">Total del servicio: {{ serviceCoversTotal ?? '—' }} comensales.</p>
                        <v-model-select v-model="service.recipe" model="Recipe" label="Receta del servicio" search-on-load :disabled="!canOperate || savingService" />
                        <allergen-assessment-panel
                            class="no-print"
                            title="Alérgenos de la receta seleccionada"
                            source="recipe"
                            :assessment="recipeAllergens"
                            :loading="loadingRecipeAllergens"
                            :error="recipeAllergenError"
                        />
                        <v-btn color="primary" :loading="savingService" :disabled="!canOperate" min-height="44" @click="saveService">Anotar servicio</v-btn>
                        <p class="mt-2" role="status">{{ serviceMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title><h2 class="text-h6">Consolidación manual</h2></v-card-title>
                    <v-card-text>
                        <p class="text-body-2 mb-3">Suma las necesidades introducidas. Incluye la unidad en el componente y usa la misma unidad en todas sus líneas. No se guardan como receta ni descuentan existencias.</p>
                        <v-text-field v-model="sheet.component" label="Componente y unidad" placeholder="Por ejemplo: aceite · L" :disabled="!canOperate || consolidating" />
                        <v-text-field v-model="sheet.quantity" label="Cantidad" inputmode="decimal" :disabled="!canOperate || consolidating" />
                        <v-btn variant="text" :disabled="!canOperate || consolidating" min-height="44" @click="addUsage">Añadir línea</v-btn>
                        <v-btn color="primary" :loading="consolidating" :disabled="!canOperate || !usages.length" min-height="44" @click="consolidate">Consolidar</v-btn>
                        <v-list v-if="usages.length">
                            <v-list-item v-for="(line, index) in usages" :key="index" :title="`${line.component} · ${line.quantity}`">
                                <template #append><v-btn variant="text" icon="fa-solid fa-xmark" :aria-label="`Quitar ${line.component}`" :disabled="!canOperate || consolidating" min-height="44" @click="removeUsage(index)" /></template>
                            </v-list-item>
                        </v-list>
                        <p role="status">{{ sheetMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card>
                    <v-card-title><h2 class="text-h6">Alérgeno</h2></v-card-title>
                    <v-card-text>
                        <v-model-select v-model="allergen.food" model="Food" label="Alimento" search-on-load :disabled="!canOperate || savingAllergen" />
                        <v-text-field v-model="allergen.name" label="Nombre" :disabled="!canOperate || savingAllergen" />
                        <v-select v-model="allergen.state" label="Estado" :items="states" item-title="title" item-value="value" :disabled="!canOperate || savingAllergen" />
                        <v-btn color="primary" :loading="savingAllergen" :disabled="!canOperate" min-height="44" @click="saveAllergen">Declarar</v-btn>
                        <p class="mt-2" role="status">{{ allergenMessage }}</p>
                        <allergen-assessment-panel
                            class="no-print"
                            title="Alérgenos del alimento seleccionado"
                            source="food"
                            :assessment="foodAllergens"
                            :loading="loadingFoodAllergens"
                            :error="foodAllergenError"
                        />
                    </v-card-text>
                </v-card>
            </v-col>
        </v-row>
        <section class="mt-6" aria-labelledby="service-list-title">
            <div class="d-flex flex-wrap align-center ga-3 mb-3 no-print">
                <h2 id="service-list-title" class="text-h6">Servicios guardados (últimos 100)</h2>
                <v-btn variant="text" :loading="loadingServices" min-height="44" @click="loadServices">Actualizar servicios</v-btn>
                <v-btn variant="text" prepend-icon="fa-solid fa-print" min-height="44" @click="printServices">Imprimir fichas</v-btn>
            </div>
            <p v-if="listMessage" role="status">{{ listMessage }}</p>
            <p v-if="!loadingServices && !services.length && !listMessage">Aún no hay servicios en tu hogar. Anota uno arriba para preparar su ficha.</p>
            <v-row>
                <v-col v-for="plan in services" :key="plan.id" cols="12" md="6">
                    <v-card class="print-card">
                        <v-card-title><h2 class="text-h6">{{ plan.title }}</h2></v-card-title>
                        <v-card-text>
                            <div class="d-flex flex-wrap align-center ga-3 mb-3"><p>{{ plan.service_date || 'Fecha heredada desconocida' }} · {{ plan.covers }} comensales</p><v-chip class="cuaderno-service-state" variant="tonal" :color="plan.state === 'produced' ? 'success' : plan.state === 'cancelled' ? 'error' : 'secondary'">{{ stateLabel(plan.state) }}</v-chip></div>
                            <p v-if="plan.snapshot?.cost" class="mt-2">
                                Coste estimado de ingredientes congelado:
                                {{ confirmedCostLabel(plan.snapshot.cost) }}.
                                No es beneficio neto ni valoración contable de existencias.
                            </p>
                            <div v-if="plan.snapshot?.finance" class="mt-3">
                                <p class="font-weight-bold">
                                    Referencias financieras congeladas (política {{ pricePolicyLabel(plan.snapshot.finance.price_policy) }})
                                </p>
                                <p>Precio de venta/ración: {{ financeMoneyLabel(plan.snapshot.finance.selling_price_per_serving) }}</p>
                                <p>Presupuesto/persona: {{ financeMoneyLabel(plan.snapshot.finance.budget_per_person) }}</p>
                                <p>Coste de ingredientes/ración: {{ financeMoneyLabel(plan.snapshot.finance.ingredient_cost_per_serving) }}</p>
                                <p>Diferencia frente al coste: {{ financeMoneyLabel(plan.snapshot.finance.difference_per_serving) }}</p>
                                <p>Margen hasta presupuesto: {{ financeMoneyLabel(plan.snapshot.finance.budget_gap_per_person) }}</p>
                                <p>Porcentaje de coste de materia: {{ financeRatioLabel(plan.snapshot.finance.food_cost_ratio) }}</p>
                                <p class="text-medium-emphasis">
                                    Esta referencia pertenece a la confirmación del servicio: no se recalcula con el precio actual y la diferencia no es beneficio neto.
                                </p>
                                <v-alert v-for="warning in plan.snapshot.finance.warnings || []" :key="warning" type="warning" class="mt-2">
                                    {{ financeWarningLabel(warning) }}
                                </v-alert>
                            </div>
                            <v-alert v-for="(warning, index) in plan.snapshot?.warnings || []" :key="index" type="warning" class="mt-2">{{ productionWarning(warning) }}</v-alert>
                            <allergen-assessment-panel
                                title="Alérgenos congelados al confirmar"
                                source="snapshot"
                                :assessment="frozenAllergens(plan)"
                                :legacy="frozenAllergens(plan) === null"
                            />
                            <v-list v-if="plan.snapshot?.needs?.length">
                                <v-list-item v-for="line in plan.snapshot.needs" :key="line.food_id" :title="line.food_name" :subtitle="`${line.quantity} ${line.unit_name || '(sin unidad)'}`" />
                            </v-list>
                            <p v-if="plan.state === 'confirmed'" class="mt-2">La ficha no cambia al actualizar precios o recetas. Producir no registra stock de producto terminado ni descuenta subelaboraciones además de sus ingredientes.</p>
                            <v-alert v-if="plan.state === 'cancelled' && plan.snapshot?.production?.reversal" type="success" role="status" class="mt-3">
                                <p class="font-weight-bold">Producción revertida</p>
                                <p>{{ reversalAuditLabel(plan.snapshot.production) }}</p>
                            </v-alert>
                            <production-waste-panel
                                v-if="plan.state === 'produced' || plan.state === 'cancelled'"
                                :classification="frozenProductionWaste(plan)"
                            />
                            <service-preparation-panel class="mt-4" :service-id="plan.id" :service-state="plan.state" :can-operate="canOperate" />
                        </v-card-text>
                        <v-card-actions class="flex-wrap ga-2 no-print">
                            <v-btn v-if="plan.state === 'draft'" color="primary" :loading="busyPlan === plan.id" :disabled="!canOperate || busyPlan !== null" min-height="44" @click="transition(plan, 'confirm')">Confirmar ficha</v-btn>
                            <v-btn v-if="plan.state === 'confirmed'" color="primary" :disabled="!canOperate || busyPlan !== null" min-height="44" @click="openConfirmation(plan, 'produce')">Producir</v-btn>
                            <v-btn v-if="plan.state === 'produced'" color="primary" :disabled="!canOperate || busyPlan !== null" min-height="44" @click="openConfirmation(plan, 'reverse')">Revertir producción</v-btn>
                            <v-btn v-if="['draft', 'confirmed'].includes(plan.state)" :disabled="!canOperate || busyPlan !== null" min-height="44" @click="openConfirmation(plan, 'cancel')">Cancelar servicio</v-btn>
                        </v-card-actions>
                    </v-card>
                </v-col>
            </v-row>
        </section>
        <v-dialog :model-value="confirmation !== null" max-width="520" @update:model-value="value => { if (!value && busyPlan === null) confirmation = null }">
            <v-card v-if="confirmation">
                <v-card-title>{{ confirmationTitle(confirmation.action) }}</v-card-title>
                <v-card-text>
                    <p>{{ confirmation.plan.title }} · {{ confirmation.plan.covers }} comensales.</p>
                    <p v-if="confirmation.action === 'produce'">En Integral se consumirán las necesidades congeladas del hogar asignado. Si faltan existencias utilizables no se descontará nada. En Profesional solo se registrará el estado producido.</p>
                    <p v-else-if="confirmation.action === 'reverse'">
                        La reversión completa restaurará todas las asignaciones de existencias consumidas por este servicio.
                        La necesidad bruta ya incluía la merma: no se registrará un segundo consumo.
                        Los movimientos originales se conservarán en el historial.
                        En Profesional no se modificó el stock y la reversión tampoco creará movimientos de existencias.
                    </p>
                    <p v-else>Se conservará el servicio como cancelado sin cambiar las existencias.</p>
                </v-card-text>
                <v-card-actions>
                    <v-btn :disabled="busyPlan !== null" min-height="44" @click="confirmation = null">Volver</v-btn>
                    <v-btn color="primary" :disabled="!canOperate || busyPlan !== null" :loading="busyPlan !== null" min-height="44" @click="transition(confirmation.plan, confirmation.action)">
                        {{ confirmation.action === 'reverse' ? 'Confirmar reversión' : 'Confirmar acción' }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
        </div>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onMounted, onUnmounted, reactive, ref, watch} from "vue"
import {cuadernoFetch, readJson} from "@/cuaderno/api"
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import ServicePreparationPanel from '@/cuaderno/components/ServicePreparationPanel.vue'
import AllergenAssessmentPanel from '@/cuaderno/components/AllergenAssessmentPanel.vue'
import ProductionWastePanel from '@/cuaderno/components/ProductionWastePanel.vue'
import {apiError, productionUsage, productionWarning, serviceBody, serviceCovers, yieldBody, confirmedCostLabel} from '@/cuaderno/forms'
import {inventoryRequests} from '@/cuaderno/inventoryRequests'
import {editionOperationalRole} from '@/cuaderno/operationalRoleUi'
import {cuadernoNavigationCapabilities} from '@/cuaderno/navigationUi'
import {
    financeMoneyLabel,
    financeRatioLabel,
    financeWarningLabel,
    pricePolicyLabel,
    type RecipeFinance,
} from '@/cuaderno/financeUi'
import {
    allergenAssessmentEnvelope,
    allergenDeclarationName,
    allergenDeclarationResponse,
    isSafeAllergenId,
    type AllergenAssessment,
    type AllergenState,
} from '@/cuaderno/allergenUi'
import {
    productionWasteEnvelope,
    type ProductionWasteClassification,
} from '@/cuaderno/productionWasteUi'

const states = [
    {title: "Desconocido", value: "unknown"},
    {title: "Declarado", value: "declared"},
]
const notice = ref("")
const serviceMessage = ref("")
const sheetMessage = ref("")
const allergenMessage = ref("")
const usages = ref<{component: string; quantity: string}[]>([])
const service = reactive({title: "", baseCovers: "", extra: "0", cancelled: "0", date: "", recipe: null as any})
const serviceCoversTotal = computed(() => {
    const values = serviceCovers(service.baseCovers, service.extra, service.cancelled)
    if (!values) return null
    return (BigInt(values.base_covers) + BigInt(values.extra) - BigInt(values.cancelled)).toString()
})
type ServiceRow = {
    id: number; title: string; covers: string; service_date: string | null; state: string;
    snapshot?: {cost?: {status: string; total: string | null; display: string | null}; warnings?: unknown[];
        finance?: RecipeFinance;
        recipe_id?: number | null;
        allergens?: unknown;
        needs?: {food_id: number; food_name: string; quantity: string; unit_name: string | null}[];
        production?: {
            produced_at?: string; edition?: string; movement_ids?: number[]; stock_changed?: boolean;
            waste_classification?: unknown;
            reversal?: {
                key_sha256?: string; reversed_at?: string; reversed_by?: number;
                original_movement_ids?: number[]; movement_ids?: number[];
            };
        };
    }
}

function frozenProductionWaste(plan: ServiceRow): ProductionWasteClassification | null {
    return productionWasteEnvelope(plan.snapshot?.production?.waste_classification)
}
type ServiceAction = 'confirm' | 'produce' | 'cancel' | 'reverse'
type ReversalResponse = ServiceRow & {stock_changed: boolean; reversal_movement_ids: number[]}
const services = ref<ServiceRow[]>([])
const loadingServices = ref(false)
const listMessage = ref('')
const busyPlan = ref<number | null>(null)
const confirmation = ref<{plan: ServiceRow; action: 'produce' | 'cancel' | 'reverse'} | null>(null)
const serviceRequests = inventoryRequests()
const canOperate = ref(false)
const productionEnabled = ref<boolean | null>(null)
const editionMessage = ref('')
const sheet = reactive({component: "", quantity: ""})
const allergen = reactive({food: null as any, name: "", state: "unknown"})
const foodAllergens = ref<AllergenAssessment | null>(null)
const recipeAllergens = ref<AllergenAssessment | null>(null)
const loadingFoodAllergens = ref(false)
const loadingRecipeAllergens = ref(false)
const foodAllergenError = ref('')
const recipeAllergenError = ref('')
let foodAllergenGeneration = 0
let recipeAllergenGeneration = 0
let foodAllergenController: AbortController | null = null
let recipeAllergenController: AbortController | null = null
const savingService = ref(false)
const consolidating = ref(false)
const savingAllergen = ref(false)
const selectedRecipes = ref<any[]>([])
const recipeNeeds = ref<{name: string; quantity: string}[]>([])
const recipeWarnings = ref<string[]>([])
const recipeMessage = ref('')
const calculatingRecipes = ref(false)
const output = reactive({recipe: null as any, quantity: '', unit: null as any})
const yieldMessage = ref('')
const savingYield = ref(false)

watch(selectedRecipes, () => {
    recipeNeeds.value = []
    recipeWarnings.value = []
    recipeMessage.value = ''
}, {deep: true})

async function loadFoodAllergens(foodId: number | null) {
    const generation = ++foodAllergenGeneration
    foodAllergenController?.abort()
    foodAllergenController = null
    foodAllergens.value = null
    foodAllergenError.value = ''
    loadingFoodAllergens.value = false
    if (!isSafeAllergenId(foodId)) return
    const controller = new AbortController()
    foodAllergenController = controller
    loadingFoodAllergens.value = true
    try {
        const {ok, status, data} = await readJson(await cuadernoFetch(
            `/api/cuaderno/allergens/?food=${foodId}`,
            {signal: controller.signal},
        ))
        if (generation !== foodAllergenGeneration || controller.signal.aborted) return
        if (!ok) {
            foodAllergenError.value = explain(status, data)
            return
        }
        const parsed = allergenAssessmentEnvelope(data, 'food', Number(foodId))
        if (!parsed) {
            foodAllergenError.value = 'La respuesta de alérgenos está incompleta o incoherente.'
            return
        }
        foodAllergens.value = parsed
    } catch {
        if (generation === foodAllergenGeneration && !controller.signal.aborted) {
            foodAllergenError.value = 'No se pudo consultar la información de alérgenos.'
        }
    } finally {
        if (generation === foodAllergenGeneration) loadingFoodAllergens.value = false
    }
}

async function loadRecipeAllergens(recipeId: number | null) {
    const generation = ++recipeAllergenGeneration
    recipeAllergenController?.abort()
    recipeAllergenController = null
    recipeAllergens.value = null
    recipeAllergenError.value = ''
    loadingRecipeAllergens.value = false
    if (!isSafeAllergenId(recipeId)) return
    const controller = new AbortController()
    recipeAllergenController = controller
    loadingRecipeAllergens.value = true
    try {
        const {ok, status, data} = await readJson(await cuadernoFetch(
            `/api/cuaderno/allergens/?recipe=${recipeId}`,
            {signal: controller.signal},
        ))
        if (generation !== recipeAllergenGeneration || controller.signal.aborted) return
        if (!ok) {
            recipeAllergenError.value = explain(status, data)
            return
        }
        const parsed = allergenAssessmentEnvelope(data, 'recipe', Number(recipeId))
        if (!parsed) {
            recipeAllergenError.value = 'La respuesta de alérgenos está incompleta o incoherente.'
            return
        }
        recipeAllergens.value = parsed
    } catch {
        if (generation === recipeAllergenGeneration && !controller.signal.aborted) {
            recipeAllergenError.value = 'No se pudo consultar la información de alérgenos.'
        }
    } finally {
        if (generation === recipeAllergenGeneration) loadingRecipeAllergens.value = false
    }
}

watch(() => allergen.food?.id ?? null, value => {
    void loadFoodAllergens(value)
}, {flush: 'sync'})

watch(() => service.recipe?.id ?? null, value => {
    void loadRecipeAllergens(value)
}, {flush: 'sync'})

function frozenAllergens(plan: ServiceRow): AllergenAssessment | null {
    const raw = plan.snapshot?.allergens
    if (raw === undefined || raw === null) return null
    const expectedId = plan.snapshot?.recipe_id
    return allergenAssessmentEnvelope(
        raw,
        'recipe',
        typeof expectedId === 'number' ? expectedId : undefined,
    )
}

async function calculateRecipes() {
    if (!canOperate.value) return
    if (calculatingRecipes.value || !selectedRecipes.value.length) return
    calculatingRecipes.value = true
    recipeNeeds.value = []
    recipeWarnings.value = []
    recipeMessage.value = ''
    const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/production/', {
        method: 'POST',
        body: JSON.stringify({recipe_ids: selectedRecipes.value.map(recipe => recipe.id)}),
    }))
    calculatingRecipes.value = false
    if (!ok) { recipeMessage.value = explain(status, data); return }
    recipeNeeds.value = Object.entries(data.needs as Record<string, string>).map(([name, quantity]) => ({
        name, quantity: `${quantity} ${data.units?.[name] || '(sin unidad declarada)'}`,
    }))
    recipeWarnings.value = (data.warnings || []).map(productionWarning)
    recipeMessage.value = recipeWarnings.value.length
        ? 'Necesidades parciales. Revisa los avisos antes de preparar la producción.'
        : recipeNeeds.value.length ? 'Necesidades calculadas. Las existencias no han cambiado.' : 'No hay necesidades calculables en estas recetas.'
}

async function saveYield() {
    if (!canOperate.value) return
    if (savingYield.value) return
    const payload = yieldBody(output.quantity, output.unit?.id)
    if (!output.recipe?.id || !payload) { yieldMessage.value = 'Selecciona receta, unidad y una cantidad de salida positiva.'; return }
    savingYield.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch(`/api/cuaderno/recipes/${output.recipe.id}/yield/`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    }))
    savingYield.value = false
    yieldMessage.value = ok ? 'Rendimiento guardado. Vuelve a calcular la ficha para aplicar el cambio.' : explain(status, data)
}

function explain(status: number, data: unknown) {
    if (status === 403) {
        notice.value = apiError(status, data)
        return notice.value
    }
    return apiError(status, data)
}

function addUsage() {
    if (!canOperate.value) return
    const line = productionUsage(sheet.component, sheet.quantity)
    if (!line) { sheetMessage.value = 'Indica un componente con su unidad y una cantidad positiva.'; return }
    usages.value.push(line)
    sheetMessage.value = ''
    sheet.component = ""
    sheet.quantity = ""
}

function removeUsage(index: number) {
    if (!canOperate.value || consolidating.value) return
    usages.value.splice(index, 1)
    sheetMessage.value = ''
}

async function saveService() {
    if (!canOperate.value) return
    if (savingService.value) return
    const covers = serviceCovers(service.baseCovers, service.extra, service.cancelled)
    const total = serviceCoversTotal.value
    const base = total === null ? null : serviceBody(service.title, total, service.date, service.recipe?.id)
    if (!covers || !base) { serviceMessage.value = 'Indica nombre, fecha válida y comensales previstos, altas y cancelaciones; el total debe estar entre 1 y 9999.'; return }
    const {covers: _total, ...serviceData} = base
    const payload = {...serviceData, ...covers}
    savingService.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/services/", {
        method: "POST",
        body: JSON.stringify(payload),
    }))
    savingService.value = false
    serviceMessage.value = ok
        ? `${data.covers} comensales. Stock ${data.stock_changed ? "alterado" : "sin cambios"}. Menú ${data.meal_plan}.`
        : explain(status, data)
    if (ok) await loadServices()
}

function stateLabel(state: string) {
    return ({draft: 'Borrador', confirmed: 'Confirmado', produced: 'Producido', cancelled: 'Cancelado'} as Record<string, string>)[state] || state
}

function confirmationTitle(action: ServiceAction) {
    if (action === 'produce') return 'Producir servicio'
    if (action === 'reverse') return 'Revertir producción'
    return 'Cancelar servicio'
}

function openConfirmation(plan: ServiceRow, action: 'produce' | 'cancel' | 'reverse') {
    if (!canOperate.value || busyPlan.value !== null) return
    confirmation.value = {plan, action}
}

function reversalAuditLabel(production: NonNullable<NonNullable<ServiceRow['snapshot']>['production']>) {
    const audit = production.reversal
    if (!audit) return ''
    const completed = audit.reversed_at ? `Reversión completada el ${audit.reversed_at}. ` : 'Reversión completada. '
    if (production.edition === 'profesional') {
        return `${completed}Profesional: completada sin movimientos de existencias. Se conserva el historial original de producción.`
    }
    const count = audit.movement_ids?.length || 0
    return `${completed}Existencias restauradas con ${count} movimientos compensatorios. Se conserva el historial original de consumos.`
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function positiveIds(value: unknown): number[] | null {
    if (!Array.isArray(value) || value.some(item => !Number.isInteger(item) || item <= 0)) return null
    const identifiers = value as number[]
    return new Set(identifiers).size === identifiers.length ? identifiers : null
}

function sameIds(first: number[], second: number[]) {
    return first.length === second.length && first.every((value, index) => value === second[index])
}

function validReversalResponse(value: unknown, plan: ServiceRow): value is ReversalResponse {
    if (!isRecord(value) || value.id !== plan.id || value.state !== 'cancelled' || typeof value.stock_changed !== 'boolean') return false
    const responseIds = positiveIds(value.reversal_movement_ids)
    const snapshot = value.snapshot
    const previousProduction = plan.snapshot?.production
    if (responseIds === null || !isRecord(snapshot) || !previousProduction || !isRecord(snapshot.production)) return false
    const production = snapshot.production
    const audit = production.reversal
    if (!isRecord(audit) || Object.keys(audit).sort().join(',') !== 'key_sha256,movement_ids,original_movement_ids,reversed_at,reversed_by') return false
    const originalIds = positiveIds(audit.original_movement_ids)
    const reversalIds = positiveIds(audit.movement_ids)
    const productionIds = positiveIds(production.movement_ids)
    const previousIds = positiveIds(previousProduction.movement_ids)
    if (originalIds === null || reversalIds === null || productionIds === null || previousIds === null) return false
    if (
        !sameIds(responseIds, reversalIds)
        || reversalIds.length !== originalIds.length
        || !sameIds(originalIds, productionIds)
        || !sameIds(originalIds, previousIds)
        || reversalIds.some(identifier => originalIds.includes(identifier))
        || value.stock_changed !== (reversalIds.length > 0)
        || production.produced_at !== previousProduction.produced_at
        || production.edition !== previousProduction.edition
        || production.stock_changed !== previousProduction.stock_changed
    ) return false
    return (
        typeof audit.key_sha256 === 'string'
        && /^[0-9a-f]{64}$/.test(audit.key_sha256)
        && typeof audit.reversed_at === 'string'
        && audit.reversed_at.length > 0
        && !Number.isNaN(Date.parse(audit.reversed_at))
        && Number.isInteger(audit.reversed_by)
        && Number(audit.reversed_by) > 0
    )
}

async function loadServices() {
    if (productionEnabled.value !== true) return
    if (loadingServices.value) return
    loadingServices.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/services/'))
    loadingServices.value = false
    if (!ok) { listMessage.value = explain(status, data); return }
    services.value = data
    listMessage.value = ''
}

async function transition(plan: ServiceRow, action: ServiceAction) {
    if (!canOperate.value) return
    if (busyPlan.value !== null) return
    const submittedConfirmation = confirmation.value
    busyPlan.value = plan.id
    const payload = {
        action,
        ...(action === 'produce' ? {idempotency_key: serviceRequests.key('produce-service', {plan: plan.id})} : {}),
        ...(action === 'reverse' ? {idempotency_key: serviceRequests.key('reverse-service', {plan: plan.id})} : {}),
    }
    try {
        const {ok, status, data} = await readJson(await cuadernoFetch(`/api/cuaderno/services/${plan.id}/`, {
            method: 'POST', body: JSON.stringify(payload),
        }))
        if (!ok) {
            listMessage.value = explain(status, data)
            if (action !== 'reverse' && confirmation.value === submittedConfirmation) confirmation.value = null
            return
        }
        if (action === 'reverse' && !validReversalResponse(data, plan)) {
            listMessage.value = 'La respuesta de reversión está incompleta o incoherente. No se actualizó el servicio; reintenta con la misma confirmación.'
            return
        }
        const index = services.value.findIndex(row => row.id === plan.id)
        if (index !== -1) {
            // Reversal changes only state and its audit. Never replace the
            // frozen financial/needs document with unrelated response fields.
            services.value[index] = action === 'reverse' ? {
                ...plan,
                state: 'cancelled',
                snapshot: {
                    ...plan.snapshot,
                    production: {...plan.snapshot?.production, reversal: data.snapshot.production.reversal},
                },
            } : data
        }
        if (confirmation.value === submittedConfirmation) confirmation.value = null
        if (action === 'reverse') {
            const professional = data.snapshot?.production?.edition === 'profesional'
            listMessage.value = data.stock_changed
                ? 'Producción revertida y existencias restauradas. Los consumos originales permanecen en el historial.'
                : professional
                    ? 'Producción revertida. En Profesional no se había modificado el stock; no se crearon movimientos de existencias. El historial original se conserva.'
                    : 'Producción revertida. Las existencias no habían cambiado y el historial original se conserva.'
            return
        }
        listMessage.value = data.stock_changed ? 'Producción registrada y existencias descontadas una sola vez.' : `${stateLabel(data.state)}. Las existencias no han cambiado.`
    } catch {
        listMessage.value = action === 'reverse'
            ? 'No se pudo revertir la producción. La confirmación sigue abierta para reintentar con seguridad.'
            : 'No se pudo completar la acción del servicio. Inténtalo de nuevo.'
    } finally {
        busyPlan.value = null
    }
}

function printServices() { window.print() }
async function loadEdition() {
    const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/edition/'))
    canOperate.value = false
    if (!ok) {
        productionEnabled.value = false
        editionMessage.value = apiError(status, data)
        return
    }
    productionEnabled.value = cuadernoNavigationCapabilities(data).production
    if (!productionEnabled.value) {
        editionMessage.value = 'La producción está disponible en las ediciones Profesional e Integral.'
        return
    }
    editionMessage.value = ''
    canOperate.value = editionOperationalRole(data)?.can_operate_cuaderno === true
    await loadServices()
}

onMounted(loadEdition)
onUnmounted(() => {
    foodAllergenController?.abort()
    recipeAllergenController?.abort()
})

async function consolidate() {
    if (!canOperate.value) return
    if (consolidating.value || !usages.value.length) return
    consolidating.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/production/", {
        method: "POST",
        body: JSON.stringify({usages: usages.value}),
    }))
    consolidating.value = false
    if (!ok) {
        sheetMessage.value = explain(status, data)
        return
    }
    const lines = Object.entries(data.needs as Record<string, string>).map(([name, qty]) => `${name}: ${qty}`)
    sheetMessage.value = lines.length ? lines.join(" · ") : "Sin necesidades."
    if (data.stock_changed) sheetMessage.value += " El stock ha cambiado."
}

async function saveAllergen() {
    if (!canOperate.value) return
    if (savingAllergen.value) return
    const submittedName = allergenDeclarationName(allergen.name)
    if (!isSafeAllergenId(allergen.food?.id) || !submittedName) {
        allergenMessage.value = 'Selecciona un alimento con identificador válido e indica un nombre válido, sin caracteres no permitidos.'
        return
    }
    const submittedFoodId = allergen.food.id as number
    const submittedState: AllergenState = allergen.state === 'declared' ? 'declared' : 'unknown'
    savingAllergen.value = true
    try {
        const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/allergens/", {
            method: "POST",
            body: JSON.stringify({
                food: submittedFoodId,
                name: submittedName,
                state: submittedState,
            }),
        }))
        if (!ok) {
            allergenMessage.value = explain(status, data)
            return
        }
        if (!allergenDeclarationResponse(data, submittedState)) {
            allergenMessage.value = 'La respuesta de la declaración está incompleta o incoherente. Conservamos el formulario.'
            return
        }
        allergenMessage.value = `${states.find(state => state.value === submittedState)?.title || 'Guardado'}. No declarar no significa que el alérgeno esté ausente.`
        await Promise.all([
            allergen.food?.id === submittedFoodId ? loadFoodAllergens(submittedFoodId) : Promise.resolve(),
            service.recipe?.id ? loadRecipeAllergens(service.recipe.id) : Promise.resolve(),
        ])
    } catch {
        allergenMessage.value = 'No se pudo guardar la declaración. Conservamos el formulario.'
    } finally {
        savingAllergen.value = false
    }
}
</script>

<style scoped>
@media screen {
    .cuaderno-production-page :deep(.v-card-title) { padding: 18px 20px; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .12); background: rgba(var(--v-theme-secondary), .06); }
    .cuaderno-production-page :deep(.v-card-text) { padding: 20px; }
    .cuaderno-production-page :deep(.v-list-item) { margin-block: 8px; border-inline-start: 3px solid rgba(var(--v-theme-primary), .4); border-radius: 8px; }
}

@media print {
    .print-card { break-inside: avoid; }
    .no-print { display: none; }
}
</style>
