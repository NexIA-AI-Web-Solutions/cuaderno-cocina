<template>
    <v-container>
        <v-btn :to="{name: 'MealPlanPage'}" variant="text" prepend-icon="fa-solid fa-calendar-days" min-height="44" class="mb-3">Ver planificación de menús</v-btn>
        <h1 class="text-h5 mb-3">Producción</h1>
        <p class="mb-4">
            Crear y confirmar un servicio no descuenta stock. Confirmar conserva sus necesidades y costes.
            Producir es una acción explícita: solo en Integral consume ingredientes de las existencias del hogar del servicio.
            Un alérgeno sin declarar no se trata como ausente.
        </p>
        <v-alert v-if="notice" type="info" class="mb-4" role="status">{{ notice }}</v-alert>
        <v-row>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title>Ficha desde recetas</v-card-title>
                    <v-card-text>
                        <p class="text-body-2 mb-3">Calcula las necesidades de las recetas con sus cantidades guardadas. Las subrecetas necesitan un rendimiento de salida declarado.</p>
                        <v-model-select v-model="selectedRecipes" model="Recipe" label="Recetas" multiple chips search-on-load :disabled="calculatingRecipes" />
                        <v-btn color="primary" :loading="calculatingRecipes" :disabled="!selectedRecipes.length" min-height="44" @click="calculateRecipes">Calcular necesidades</v-btn>
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
                    <v-card-title>Rendimiento de subreceta</v-card-title>
                    <v-card-text>
                        <p class="text-body-2 mb-3">Indica cuánto producto terminado obtienes al elaborar una vez la receta completa. No equivale al número de raciones.</p>
                        <v-model-select v-model="output.recipe" model="Recipe" label="Receta" search-on-load />
                        <v-text-field v-model="output.quantity" label="Cantidad obtenida" inputmode="decimal" />
                        <v-model-select v-model="output.unit" model="Unit" label="Unidad de salida" search-on-load />
                        <v-btn color="primary" :loading="savingYield" min-height="44" @click="saveYield">Guardar rendimiento</v-btn>
                        <p class="mt-2" role="status">{{ yieldMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title>Servicio</v-card-title>
                    <v-card-text>
                        <v-text-field v-model="service.title" label="Nombre" />
                        <v-text-field v-model="service.date" label="Fecha del servicio" type="date" />
                        <v-text-field v-model="service.covers" label="Comensales" inputmode="numeric" />
                        <v-model-select v-model="service.recipe" model="Recipe" label="Receta del servicio" search-on-load />
                        <v-btn color="primary" :loading="savingService" min-height="44" @click="saveService">Anotar servicio</v-btn>
                        <p class="mt-2" role="status">{{ serviceMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title>Consolidación manual</v-card-title>
                    <v-card-text>
                        <p class="text-body-2 mb-3">Suma las necesidades introducidas. Incluye la unidad en el componente y usa la misma unidad en todas sus líneas. No se guardan como receta ni descuentan existencias.</p>
                        <v-text-field v-model="sheet.component" label="Componente y unidad" placeholder="Por ejemplo: aceite · L" />
                        <v-text-field v-model="sheet.quantity" label="Cantidad" inputmode="decimal" />
                        <v-btn variant="text" :disabled="consolidating" min-height="44" @click="addUsage">Añadir línea</v-btn>
                        <v-btn color="primary" :loading="consolidating" :disabled="!usages.length" min-height="44" @click="consolidate">Consolidar</v-btn>
                        <v-list v-if="usages.length">
                            <v-list-item v-for="(line, index) in usages" :key="index" :title="`${line.component} · ${line.quantity}`">
                                <template #append><v-btn variant="text" icon="fa-solid fa-xmark" :aria-label="`Quitar ${line.component}`" :disabled="consolidating" min-height="44" @click="usages.splice(index, 1); sheetMessage = ''" /></template>
                            </v-list-item>
                        </v-list>
                        <p role="status">{{ sheetMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card>
                    <v-card-title>Alérgeno</v-card-title>
                    <v-card-text>
                        <v-model-select v-model="allergen.food" model="Food" label="Alimento" search-on-load />
                        <v-text-field v-model="allergen.name" label="Nombre" />
                        <v-select v-model="allergen.state" label="Estado" :items="states" item-title="title" item-value="value" />
                        <v-btn color="primary" :loading="savingAllergen" min-height="44" @click="saveAllergen">Declarar</v-btn>
                        <p class="mt-2" role="status">{{ allergenMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
        </v-row>
        <section class="mt-6" aria-labelledby="service-list-title">
            <div class="d-flex flex-wrap align-center ga-3 mb-3">
                <h2 id="service-list-title" class="text-h6">Servicios guardados (últimos 100)</h2>
                <v-btn variant="text" :loading="loadingServices" min-height="44" @click="loadServices">Actualizar servicios</v-btn>
                <v-btn variant="text" prepend-icon="fa-solid fa-print" min-height="44" @click="printServices">Imprimir fichas</v-btn>
            </div>
            <p v-if="listMessage" role="status">{{ listMessage }}</p>
            <p v-if="!loadingServices && !services.length && !listMessage">Aún no hay servicios en tu hogar. Anota uno arriba para preparar su ficha.</p>
            <v-row>
                <v-col v-for="plan in services" :key="plan.id" cols="12" md="6">
                    <v-card class="print-card">
                        <v-card-title>{{ plan.title }}</v-card-title>
                        <v-card-text>
                            <p>{{ plan.service_date || 'Fecha heredada desconocida' }} · {{ plan.covers }} comensales · {{ stateLabel(plan.state) }}</p>
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
                            <v-list v-if="plan.snapshot?.needs?.length">
                                <v-list-item v-for="line in plan.snapshot.needs" :key="line.food_id" :title="line.food_name" :subtitle="`${line.quantity} ${line.unit_name || '(sin unidad)'}`" />
                            </v-list>
                            <p v-if="plan.state === 'confirmed'" class="mt-2">La ficha no cambia al actualizar precios o recetas. Producir no registra stock de producto terminado ni descuenta subelaboraciones además de sus ingredientes.</p>
                        </v-card-text>
                        <v-card-actions class="flex-wrap ga-2 no-print">
                            <v-btn v-if="plan.state === 'draft'" color="primary" :loading="busyPlan === plan.id" :disabled="busyPlan !== null" min-height="44" @click="transition(plan, 'confirm')">Confirmar ficha</v-btn>
                            <v-btn v-if="plan.state === 'confirmed'" color="primary" :disabled="busyPlan !== null" min-height="44" @click="confirmation = {plan, action: 'produce'}">Producir</v-btn>
                            <v-btn v-if="['draft', 'confirmed'].includes(plan.state)" :disabled="busyPlan !== null" min-height="44" @click="confirmation = {plan, action: 'cancel'}">Cancelar servicio</v-btn>
                        </v-card-actions>
                    </v-card>
                </v-col>
            </v-row>
        </section>
        <v-dialog :model-value="confirmation !== null" max-width="520" @update:model-value="value => { if (!value && busyPlan === null) confirmation = null }">
            <v-card v-if="confirmation">
                <v-card-title>{{ confirmation.action === 'produce' ? 'Producir servicio' : 'Cancelar servicio' }}</v-card-title>
                <v-card-text>
                    <p>{{ confirmation.plan.title }} · {{ confirmation.plan.covers }} comensales.</p>
                    <p v-if="confirmation.action === 'produce'">En Integral se consumirán las necesidades congeladas del hogar asignado. Si faltan existencias utilizables no se descontará nada. En Profesional solo se registrará el estado producido.</p>
                    <p v-else>Se conservará el servicio como cancelado sin cambiar las existencias.</p>
                </v-card-text>
                <v-card-actions>
                    <v-btn :disabled="busyPlan !== null" min-height="44" @click="confirmation = null">Volver</v-btn>
                    <v-btn color="primary" :loading="busyPlan !== null" min-height="44" @click="transition(confirmation.plan, confirmation.action)">Confirmar acción</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </v-container>
</template>

<script setup lang="ts">
import {onMounted, reactive, ref, watch} from "vue"
import {cuadernoFetch, readJson} from "@/cuaderno/api"
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import {apiError, productionUsage, productionWarning, serviceBody, yieldBody, confirmedCostLabel} from '@/cuaderno/forms'
import {inventoryRequests} from '@/cuaderno/inventoryRequests'
import {
    financeMoneyLabel,
    financeRatioLabel,
    financeWarningLabel,
    pricePolicyLabel,
    type RecipeFinance,
} from '@/cuaderno/financeUi'

const states = [
    {title: "Desconocido", value: "unknown"},
    {title: "Declarado", value: "declared"},
]
const notice = ref("")
const serviceMessage = ref("")
const sheetMessage = ref("")
const allergenMessage = ref("")
const usages = ref<{component: string; quantity: string}[]>([])
const service = reactive({title: "", covers: "", date: "", recipe: null as any})
type ServiceRow = {
    id: number; title: string; covers: string; service_date: string | null; state: string;
    snapshot?: {cost?: {status: string; total: string | null; display: string | null}; warnings?: unknown[];
        finance?: RecipeFinance;
        needs?: {food_id: number; food_name: string; quantity: string; unit_name: string | null}[]}
}
const services = ref<ServiceRow[]>([])
const loadingServices = ref(false)
const listMessage = ref('')
const busyPlan = ref<number | null>(null)
const confirmation = ref<{plan: ServiceRow; action: 'produce' | 'cancel'} | null>(null)
const serviceRequests = inventoryRequests()
const sheet = reactive({component: "", quantity: ""})
const allergen = reactive({food: null as any, name: "", state: "unknown"})
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

async function calculateRecipes() {
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
    const line = productionUsage(sheet.component, sheet.quantity)
    if (!line) { sheetMessage.value = 'Indica un componente con su unidad y una cantidad positiva.'; return }
    usages.value.push(line)
    sheetMessage.value = ''
    sheet.component = ""
    sheet.quantity = ""
}

async function saveService() {
    if (savingService.value) return
    const payload = serviceBody(service.title, service.covers, service.date, service.recipe?.id)
    if (!payload) { serviceMessage.value = 'Indica nombre, fecha válida y de 1 a 9999 comensales enteros.'; return }
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

async function loadServices() {
    if (loadingServices.value) return
    loadingServices.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/services/'))
    loadingServices.value = false
    if (!ok) { listMessage.value = explain(status, data); return }
    services.value = data
    listMessage.value = ''
}

async function transition(plan: ServiceRow, action: 'confirm' | 'produce' | 'cancel') {
    if (busyPlan.value !== null) return
    busyPlan.value = plan.id
    const payload = {action, ...(action === 'produce' ? {idempotency_key: serviceRequests.key('produce-service', {plan: plan.id})} : {})}
    const {ok, status, data} = await readJson(await cuadernoFetch(`/api/cuaderno/services/${plan.id}/`, {method: 'POST', body: JSON.stringify(payload)}))
    busyPlan.value = null
    if (!ok) { listMessage.value = explain(status, data); confirmation.value = null; return }
    const index = services.value.findIndex(row => row.id === plan.id)
    if (index !== -1) services.value[index] = data
    confirmation.value = null
    listMessage.value = data.stock_changed ? 'Producción registrada y existencias descontadas una sola vez.' : `${stateLabel(data.state)}. Las existencias no han cambiado.`
}

function printServices() { window.print() }
onMounted(loadServices)

async function consolidate() {
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
    if (savingAllergen.value) return
    if (!allergen.food?.id || !allergen.name.trim()) { allergenMessage.value = 'Selecciona un alimento e indica el nombre del alérgeno.'; return }
    savingAllergen.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/allergens/", {
        method: "POST",
        body: JSON.stringify({
            food: allergen.food.id,
            name: allergen.name.trim(),
            state: allergen.state,
        }),
    }))
    savingAllergen.value = false
    allergenMessage.value = ok
        ? `${states.find(state => state.value === data.state)?.title || 'Guardado'}. No declarar no significa que el alérgeno esté ausente.`
        : explain(status, data)
}
</script>

<style scoped>
@media print {
    .print-card { break-inside: avoid; }
    .no-print { display: none; }
}
</style>
