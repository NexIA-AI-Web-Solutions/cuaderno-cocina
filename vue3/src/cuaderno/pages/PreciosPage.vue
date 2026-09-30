<template>
    <v-container>
        <v-card>
            <v-card-title>Formatos y precios</v-card-title>
            <v-card-text>
                <p class="mb-4">
                    El precio es del envase, sin existencias.
                    <span v-if="currency">La moneda del espacio es {{ currency }}.</span>
                    <span v-else>No se ha podido confirmar la moneda del espacio.</span>
                    Un precio desconocido no se guarda como cero.
                </p>
                <v-row>
                    <v-col cols="12" md="4">
                        <v-model-select v-model="food" model="Food" label="Ingrediente" search-on-load />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-model-select v-model="unit" model="Unit" label="Unidad del contenido" search-on-load />
                    </v-col>
                    <v-col cols="12" md="4"><v-text-field v-model="label" label="Formato" placeholder="Garrafa 5 L" /></v-col>
                    <v-col cols="12" md="4"><v-text-field v-model="quantity" label="Contenido" placeholder="5" inputmode="decimal" /></v-col>
                    <v-col cols="12" md="4">
                        <v-text-field
                            v-model="price"
                            :label="currency ? `Precio ${currency}` : 'Precio (moneda no disponible)'"
                            placeholder="32,00"
                            inputmode="decimal"
                            hint="Déjalo vacío si todavía no conoces el precio."
                            persistent-hint
                        />
                        <v-checkbox v-model="newPackageExplicitFree" label="Gratis explícitamente" density="compact" hide-details="auto" />
                    </v-col>
                    <v-col cols="12" md="4" class="d-flex align-center">
                        <v-btn color="primary" :loading="saving" min-height="44" @click="save">Guardar formato</v-btn>
                    </v-col>
                </v-row>
                <v-alert v-if="createMessage" :type="createSucceeded ? 'success' : 'error'" variant="tonal" class="mt-2" role="status">
                    {{ createMessage }}
                </v-alert>

                <v-divider class="my-6" />
                <div class="d-flex flex-wrap align-center justify-space-between ga-2 mb-2">
                    <div>
                        <h2 class="text-h6 mb-0">Formatos guardados</h2>
                        <p class="text-body-2 text-medium-emphasis mb-0">Abre un formato para actualizar su precio o consultar su historial.</p>
                    </div>
                    <v-btn variant="text" min-height="44" :disabled="loading" @click="load">Actualizar lista</v-btn>
                </div>
                <v-progress-linear v-if="loading && !packages.length" indeterminate aria-label="Cargando precios" />
                <v-alert v-if="loadError" type="error" variant="tonal" class="mb-3" role="alert">{{ loadError }}</v-alert>
                <p v-if="!loading && !packages.length" class="my-4">
                    Todavía no hay formatos. Selecciona un ingrediente y su unidad para guardar el primero.
                </p>
                <v-list v-if="packages.length" lines="two" class="pa-0">
                    <v-list-item v-for="item in packages" :key="item.id" class="package-row px-0">
                        <v-list-item-title>{{ item.food_name }} — {{ item.label }}</v-list-item-title>
                        <v-list-item-subtitle>
                            {{ item.quantity }} {{ item.unit_name }}
                            <span v-if="item.current_price">
                                · {{ priceAmountLabel(item.current_price.amount, currency ?? '') }}
                                <span v-if="item.current_price.explicit_free"> (gratis explícitamente)</span>
                            </span>
                            <span v-else> · precio desconocido</span>
                        </v-list-item-subtitle>
                        <template #append>
                            <v-btn
                                variant="outlined"
                                min-height="44"
                                :disabled="savingPrice"
                                :aria-label="`Gestionar el precio de ${item.food_name}, ${item.label}`"
                                @click="selectPackage(item.id)"
                            >
                                Gestionar precio
                            </v-btn>
                        </template>
                    </v-list-item>
                </v-list>
            </v-card-text>
        </v-card>

        <v-card v-if="selectedPackage" class="mt-4">
            <v-card-title>{{ selectedPackage.food_name }} — {{ selectedPackage.label }}</v-card-title>
            <v-card-text>
                <p class="text-body-2 mb-4">Añade el precio que entra en vigor ahora. Este formulario no programa fechas futuras.</p>
                <v-row align="start">
                    <v-col cols="12" sm="7" md="5">
                        <v-text-field
                            v-model="updatedPrice"
                            :label="currency ? `Nuevo precio ${currency}` : 'Nuevo precio (moneda no disponible)'"
                            placeholder="32,00"
                            inputmode="decimal"
                            :disabled="savingPrice"
                            hint="Máximo 16 enteros y 16 decimales."
                            persistent-hint
                        />
                        <v-checkbox
                            v-model="updatedExplicitFree"
                            label="Gratis explícitamente"
                            density="compact"
                            hide-details="auto"
                            :disabled="savingPrice"
                        />
                    </v-col>
                    <v-col cols="12" sm="5" md="3" class="d-flex align-center">
                        <v-btn color="primary" min-height="44" :loading="savingPrice" @click="savePrice">Actualizar precio</v-btn>
                    </v-col>
                </v-row>
                <v-alert v-if="priceMessage" :type="priceSucceeded ? 'success' : 'error'" variant="tonal" class="mb-5" role="status">
                    {{ priceMessage }}
                </v-alert>
                <price-history-panel :package-id="selectedPackage.id" :refresh-token="historyRefreshToken" />
            </v-card-text>
        </v-card>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref} from 'vue'
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import PriceHistoryPanel from '@/cuaderno/components/PriceHistoryPanel.vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError, decimalInput} from '@/cuaderno/forms'
import {
    optionalPackagePrice,
    packageSummaries,
    priceAmountLabel,
    priceVersionBody,
    priceWriteResponse,
    editionCurrency,
    type PackageSummary,
} from '@/cuaderno/priceHistoryUi'

type NativeChoice = {id: number; name?: string}

const food = ref<NativeChoice | null>(null)
const unit = ref<NativeChoice | null>(null)
const saving = ref(false)
const loading = ref(false)
const label = ref('')
const quantity = ref('')
const price = ref('')
const newPackageExplicitFree = ref(false)
const createMessage = ref('')
const createSucceeded = ref(false)
const loadError = ref('')
const currency = ref<string | null>(null)
const packages = ref<PackageSummary[]>([])
const selectedPackageId = ref<number | null>(null)
const updatedPrice = ref('')
const updatedExplicitFree = ref(false)
const savingPrice = ref(false)
const priceMessage = ref('')
const priceSucceeded = ref(false)
const historyRefreshToken = ref(0)
const selectedPackage = computed(() => packages.value.find(item => item.id === selectedPackageId.value) ?? null)

let loadGeneration = 0
let priceGeneration = 0
let createController: AbortController | null = null
let loadController: AbortController | null = null
let priceController: AbortController | null = null

async function load() {
    const generation = ++loadGeneration
    loadController?.abort()
    loadController = new AbortController()
    const controller = loadController
    loading.value = true
    loadError.value = ''
    currency.value = null
    const [result, editionResult] = await Promise.all([
        cuadernoFetch('/api/cuaderno/packages/', {signal: controller.signal}).then(readJson),
        cuadernoFetch('/api/cuaderno/edition/', {signal: controller.signal}).then(readJson),
    ])
    if (controller.signal.aborted || generation !== loadGeneration) return
    loading.value = false
    currency.value = editionResult.ok ? editionCurrency(editionResult.data) : null
    if (currency.value === null) {
        loadError.value = editionResult.ok
            ? 'El servidor no ha indicado una moneda válida. No se guardarán precios.'
            : apiError(editionResult.status, editionResult.data)
    }
    if (!result.ok) {
        loadError.value = apiError(result.status, result.data)
        return
    }
    const parsed = packageSummaries(result.data)
    if (parsed === null) {
        loadError.value = 'El servidor devolvió una lista de formatos incompleta. Conservamos la lista anterior.'
        return
    }
    packages.value = parsed
    if (selectedPackageId.value !== null && !parsed.some(item => item.id === selectedPackageId.value)) selectPackage(null)
}

async function save() {
    createMessage.value = ''
    createSucceeded.value = false
    if (saving.value) return
    const content = decimalInput(quantity.value)
    const packagePrice = optionalPackagePrice(price.value, newPackageExplicitFree.value)
    if (!food.value?.id || !unit.value?.id || !label.value.trim() || !content || packagePrice.error) {
        createMessage.value = packagePrice.error
            || 'Selecciona ingrediente y unidad; indica un formato, contenido positivo y un precio válido o desconocido.'
        return
    }
    if (packagePrice.value !== null && currency.value === null) {
        createMessage.value = 'No se puede guardar un precio hasta confirmar la moneda del espacio. El formulario se conserva.'
        return
    }
    createController?.abort()
    createController = new AbortController()
    const controller = createController
    saving.value = true
    const result = await readJson(await cuadernoFetch('/api/cuaderno/packages/', {
        method: 'POST',
        signal: controller.signal,
        body: JSON.stringify({
            food: food.value.id,
            unit: unit.value.id,
            label: label.value.trim(),
            quantity: content,
            price: packagePrice.value,
            explicit_free: packagePrice.explicit_free,
        }),
    }))
    if (controller.signal.aborted) return
    saving.value = false
    if (!result.ok) {
        createMessage.value = apiError(result.status, result.data)
        return
    }
    createSucceeded.value = true
    createMessage.value = 'Formato guardado.'
    await load()
}

function selectPackage(packageId: number | null) {
    if (savingPrice.value) return
    if (selectedPackageId.value === packageId) return
    ++priceGeneration
    priceController?.abort()
    savingPrice.value = false
    selectedPackageId.value = packageId
    updatedPrice.value = ''
    updatedExplicitFree.value = false
    priceMessage.value = ''
    priceSucceeded.value = false
}

async function savePrice() {
    priceMessage.value = ''
    priceSucceeded.value = false
    if (savingPrice.value || selectedPackage.value === null) return
    if (currency.value === null) {
        priceMessage.value = 'No se puede actualizar el precio hasta confirmar la moneda del espacio. El formulario se conserva.'
        return
    }
    const parsed = priceVersionBody(updatedPrice.value, updatedExplicitFree.value)
    if (parsed.body === null) {
        priceMessage.value = parsed.error
        return
    }
    const packageId = selectedPackage.value.id
    const generation = ++priceGeneration
    priceController?.abort()
    priceController = new AbortController()
    const controller = priceController
    savingPrice.value = true
    const result = await readJson(await cuadernoFetch(`/api/cuaderno/packages/${packageId}/prices/`, {
        method: 'POST',
        signal: controller.signal,
        body: JSON.stringify(parsed.body),
    }))
    if (controller.signal.aborted || generation !== priceGeneration || selectedPackageId.value !== packageId) return
    savingPrice.value = false
    if (!result.ok) {
        priceMessage.value = apiError(result.status, result.data)
        return
    }
    if (priceWriteResponse(result.data, parsed.body) === null) {
        priceMessage.value = 'El servidor no confirmó exactamente el precio guardado. Conservamos el formulario para verificarlo.'
        return
    }
    updatedPrice.value = ''
    updatedExplicitFree.value = false
    priceSucceeded.value = true
    priceMessage.value = 'Precio actualizado. El historial conserva las versiones anteriores.'
    historyRefreshToken.value += 1
    await load()
}

onMounted(load)
onBeforeUnmount(() => {
    ++loadGeneration
    ++priceGeneration
    createController?.abort()
    loadController?.abort()
    priceController?.abort()
})
</script>

<style scoped>
.package-row {
    min-height: 64px;
}
</style>
