<template>
    <v-card>
        <v-card-title class="d-flex align-center flex-wrap ga-2">
            <span>Existencias mínimas</span>
            <v-spacer />
            <v-btn variant="text" min-height="44" :loading="loading" :disabled="saving" @click="loadMinimums">
                Actualizar
            </v-btn>
        </v-card-title>
        <v-card-subtitle>
            Umbrales de {{ householdName || 'tu hogar activo' }}. Define uno global por alimento o varios para ubicaciones concretas; nunca cambian el saldo.
        </v-card-subtitle>
        <v-card-text>
            <v-alert v-if="loadError" type="error" variant="tonal" class="mb-3" role="alert">{{ loadError }}</v-alert>

            <form @submit.prevent="saveMinimum" class="mb-4">
                <v-row dense>
                    <v-col cols="12" md="4">
                        <v-model-select
                            v-model="draft.food"
                            model="Food"
                            label="Alimento"
                            search-on-load
                            :disabled="!props.canOperate || saving || editingId !== null"
                        />
                    </v-col>
                    <v-col cols="12" sm="6" md="3">
                        <v-model-select
                            v-model="draft.unit"
                            model="Unit"
                            label="Unidad"
                            search-on-load
                            :disabled="!props.canOperate || saving"
                        />
                    </v-col>
                    <v-col cols="12" sm="6" md="3">
                        <v-autocomplete
                            v-model="draft.location"
                            :items="locations"
                            item-title="name"
                            item-value="id"
                            return-object
                            label="Ubicación (opcional)"
                            clearable
                            no-data-text="No hay ubicaciones en el hogar activo"
                            :disabled="!props.canOperate || saving || editingId !== null"
                        />
                    </v-col>
                    <v-col cols="12" md="2">
                        <v-text-field
                            v-model="draft.quantity"
                            label="Cantidad mínima"
                            inputmode="decimal"
                            autocomplete="off"
                            :error-messages="formError"
                            :disabled="!props.canOperate || saving"
                        />
                    </v-col>
                </v-row>
                <p class="text-body-2 text-medium-emphasis mb-2">
                    Admite coma y hasta 16 decimales. Vacío elimina ese mínimo, no las existencias.
                </p>
                <p v-if="editingId !== null" class="text-body-2 mb-2">
                    El alimento y el alcance identifican este mínimo. Para cambiarlos, deja la cantidad vacía y guarda para retirar el anterior; después crea uno nuevo.
                </p>
                <div class="d-flex align-center flex-wrap ga-2">
                    <v-btn type="submit" color="primary" min-height="44" :loading="saving" :disabled="!props.canOperate">Guardar mínimo</v-btn>
                    <v-btn v-if="editingId !== null" variant="text" min-height="44" :disabled="saving" @click="clearDraft">
                        Cancelar edición
                    </v-btn>
                    <span v-if="saveMessage" role="status" aria-live="polite">{{ saveMessage }}</span>
                </div>
            </form>

            <v-progress-linear v-if="loading" indeterminate class="mb-3" />
            <v-list v-if="rows.length" lines="three">
                <v-list-item v-for="row in rows" :key="row.id" class="minimum-row px-0">
                    <v-list-item-title class="font-weight-medium">
                        {{ row.food_name }} · {{ row.quantity }} {{ row.unit_name }}
                    </v-list-item-title>
                    <v-list-item-subtitle class="text-wrap">
                        {{ minimumScopeLabel(row.location_name) }} · actualizado {{ dateLabel(row.updated_at) }}
                    </v-list-item-subtitle>
                    <template #append>
                        <v-btn variant="tonal" min-height="44" :disabled="!props.canOperate || saving" @click="editMinimum(row)">Editar</v-btn>
                    </template>
                </v-list-item>
            </v-list>
            <v-alert v-else-if="!loading && !loadError" type="info" variant="tonal">
                No hay mínimos definidos para este hogar.
            </v-alert>
        </v-card-text>
    </v-card>
</template>

<script setup lang="ts">
import {onBeforeUnmount, onMounted, reactive, ref} from 'vue'
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {minimumScopeLabel, stockMinimumBody, stockMinimumEnvelope} from '@/cuaderno/stockMinimumUi'
import type {StockMinimumRow} from '@/cuaderno/stockMinimumUi'

type SelectedModel = {id?: number; name?: string} | null

const props = withDefaults(defineProps<{canOperate?: boolean}>(), {canOperate: true})
const emit = defineEmits<{loaded: [foods: Record<number, string>]}>()
const rows = ref<StockMinimumRow[]>([])
const householdName = ref('')
const locations = ref<{id: number; name: string}[]>([])
const draft = reactive({
    food: null as SelectedModel,
    unit: null as SelectedModel,
    location: null as SelectedModel,
    quantity: '',
})
const editingId = ref<number | null>(null)
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const formError = ref('')
const saveMessage = ref('')
let generation = 0
let loadController: AbortController | null = null
let saveController: AbortController | null = null
let mounted = true

function dateLabel(value: string) {
    const date = new Date(value)
    return Number.isFinite(date.getTime()) ? date.toLocaleString('es-ES') : value
}

function clearDraft() {
    draft.food = null
    draft.unit = null
    draft.location = null
    draft.quantity = ''
    editingId.value = null
    formError.value = ''
    saveMessage.value = ''
}

function editMinimum(row: StockMinimumRow) {
    if (!props.canOperate) return
    editingId.value = row.id
    draft.food = {id: row.food, name: row.food_name}
    draft.unit = {id: row.unit, name: row.unit_name}
    draft.location = row.location === null
        ? null
        : locations.value.find(location => location.id === row.location) || {id: row.location, name: row.location_name || `Ubicación ${row.location}`}
    draft.quantity = row.quantity
    formError.value = ''
    saveMessage.value = ''
}

async function loadMinimums() {
    const current = ++generation
    loadController?.abort()
    saveController?.abort()
    saving.value = false
    loading.value = true
    loadError.value = ''
    loadController = new AbortController()
    const controller = loadController
    try {
        const result = await readJson(await cuadernoFetch('/api/cuaderno/stock-minimums/', {signal: controller.signal}))
        if (!mounted || controller.signal.aborted || current !== generation) return
        const envelope = stockMinimumEnvelope(result.data)
        if (result.ok && envelope !== null) {
            rows.value = envelope.items
            householdName.value = envelope.household.name
            locations.value = envelope.locations
            emit('loaded', Object.fromEntries(rows.value.map(row => [row.food, row.food_name])))
        } else {
            loadError.value = result.ok
                ? 'El servidor devolvió una lista de mínimos incompleta. No sustituimos los datos mostrados.'
                : apiError(result.status, result.data)
        }
    } finally {
        if (mounted && !controller.signal.aborted && current === generation) loading.value = false
    }
}

async function saveMinimum() {
    if (!props.canOperate) return
    if (saving.value) return
    const parsed = stockMinimumBody(draft.food?.id, draft.unit?.id, draft.quantity, draft.location?.id ?? null)
    formError.value = parsed.error
    saveMessage.value = ''
    if (!parsed.body) return

    const current = generation
    saveController?.abort()
    saveController = new AbortController()
    const controller = saveController
    saving.value = true
    try {
        const result = await readJson(await cuadernoFetch('/api/cuaderno/stock-minimums/', {
            method: 'PUT', body: JSON.stringify(parsed.body), signal: controller.signal,
        }))
        if (!mounted || controller.signal.aborted || current !== generation) return
        if (!result.ok) {
            saveMessage.value = result.status === 409
                ? 'Ya existe un mínimo para ese alimento y alcance. Conservamos el formulario: retira primero el mínimo anterior antes de cambiar entre el alcance global y una ubicación.'
                : apiError(result.status, result.data)
            return
        }
        const envelope = stockMinimumEnvelope(result.data)
        if (envelope === null) {
            saveMessage.value = 'El servidor devolvió una lista de mínimos incompleta. Conservamos el formulario y los datos mostrados.'
            return
        }
        rows.value = envelope.items
        householdName.value = envelope.household.name
        locations.value = envelope.locations
        emit('loaded', Object.fromEntries(rows.value.map(row => [row.food, row.food_name])))
        clearDraft()
        saveMessage.value = parsed.body.quantity === null ? 'Mínimo eliminado; el saldo no ha cambiado.' : 'Mínimo guardado.'
    } finally {
        if (mounted && !controller.signal.aborted && current === generation) saving.value = false
    }
}

onMounted(loadMinimums)
onBeforeUnmount(() => {
    mounted = false
    ++generation
    loadController?.abort()
    saveController?.abort()
})
</script>

<style scoped>
.minimum-row { border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
@media (max-width: 700px) {
    .minimum-row :deep(.v-list-item__append) { align-self: center; margin-inline-start: 0.5rem; }
}
</style>
