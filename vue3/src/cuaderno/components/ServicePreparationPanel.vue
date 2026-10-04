<template>
    <section :aria-labelledby="titleId">
        <div class="d-flex flex-wrap align-center justify-space-between ga-2">
            <div>
                <h4 :id="titleId" class="text-subtitle-1 font-weight-bold mb-0">Preparación del servicio</h4>
                <p class="text-body-2 text-medium-emphasis mb-0">
                    Pasos congelados al confirmar este servicio.
                </p>
            </div>
            <v-btn
                v-if="!opened"
                variant="tonal"
                min-height="44"
                prepend-icon="mdi-format-list-checks"
                @click="openPreparation"
            >
                Ver preparación
            </v-btn>
            <v-btn
                v-else
                variant="text"
                min-height="44"
                :disabled="loading || savingItem !== null"
                @click="load"
            >
                Recargar
            </v-btn>
        </div>

        <template v-if="opened">
            <v-progress-linear
                v-if="loading && !payload"
                indeterminate
                class="mt-3"
                aria-label="Cargando preparación del servicio"
            />
            <v-alert
                v-if="message"
                :type="messageVariant"
                variant="tonal"
                :role="messageVariant === 'success' ? 'status' : 'alert'"
                class="mt-3"
            >
                {{ message }}
                <template v-if="conflict" #append>
                    <v-btn variant="text" min-height="44" :disabled="loading || savingItem !== null" @click="load">
                        Recargar
                    </v-btn>
                </template>
            </v-alert>

            <template v-if="payload">
                <v-alert v-if="!payload.can_edit && payload.items.length" type="info" variant="tonal" class="mt-3">
                    Esta preparación es de solo lectura porque el servicio está {{ stateLabel(payload.state) }}.
                </v-alert>
                <v-alert v-if="!payload.items.length" type="info" variant="tonal" class="mt-3">
                    Este servicio no tiene checklist congelado.
                    <template v-if="payload.state === 'confirmed'">Los servicios históricos permanecen sin reconstrucción automática.</template>
                </v-alert>

                <v-row v-else dense class="mt-1">
                    <v-col v-for="item in payload.items" :key="item.id" cols="12" md="6">
                        <v-card variant="outlined" class="h-100 preparation-item">
                            <v-card-text>
                                <div class="d-flex align-start ga-2">
                                    <v-checkbox-btn
                                        :model-value="item.checked"
                                        :aria-label="`${item.checked ? 'Desmarcar' : 'Marcar'} ${item.name || 'paso de preparación'}`"
                                        class="preparation-check flex-shrink-0"
                                        :disabled="!props.canOperate || !payload.can_edit || conflict || loading || savingItem !== null"
                                        @update:model-value="value => updateItem(item, value)"
                                    />
                                    <div class="min-width-0">
                                        <p :class="['font-weight-bold mb-1', {'text-decoration-line-through': item.checked}]">
                                            {{ item.name || `Paso ${item.position + 1}` }}
                                        </p>
                                        <p class="text-body-2 preserve-lines mb-2">{{ item.instruction }}</p>
                                        <p v-if="item.checked_at" class="text-caption text-medium-emphasis mb-0">
                                            Completado {{ dateLabel(item.checked_at) }}
                                        </p>
                                        <p v-if="savingItem === item.id" class="text-caption mb-0" role="status">
                                            Guardando cambio…
                                        </p>
                                    </div>
                                </div>
                            </v-card-text>
                        </v-card>
                    </v-col>
                </v-row>
            </template>
        </template>
    </section>
</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, ref, watch} from 'vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {
    servicePreparationConflictMessage,
    servicePreparationEnvelope,
    servicePreparationSaveEnvelope,
    servicePreparationWrite,
    type ServicePreparationEnvelope,
    type ServicePreparationItem,
    type ServicePreparationState,
} from '@/cuaderno/servicePreparationUi'

const props = withDefaults(defineProps<{serviceId: number; serviceState: string; canOperate?: boolean}>(), {canOperate: true})
const opened = ref(false)
const payload = ref<ServicePreparationEnvelope | null>(null)
const loading = ref(false)
const message = ref('')
const messageVariant = ref<'error' | 'warning' | 'success'>('error')
const conflict = ref(false)
const savingItem = ref<number | null>(null)
const titleId = computed(() => `service-preparation-${props.serviceId}`)
let contextGeneration = 0
let loadGeneration = 0
let loadController: AbortController | null = null
let alive = true

function stateLabel(state: ServicePreparationState) {
    return ({draft: 'en borrador', confirmed: 'confirmado', produced: 'producido', cancelled: 'cancelado'} as const)[state]
}

function dateLabel(value: string) {
    return new Intl.DateTimeFormat('es-ES', {dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value))
}

function openPreparation() {
    opened.value = true
    void load()
}

async function load() {
    if (!opened.value || loading.value || savingItem.value !== null) return
    const serviceId = props.serviceId
    const context = contextGeneration
    const generation = ++loadGeneration
    loadController?.abort()
    loadController = new AbortController()
    const controller = loadController
    loading.value = true
    message.value = ''
    messageVariant.value = 'error'
    const {ok, status, data} = await readJson(await cuadernoFetch(
        `/api/cuaderno/services/${serviceId}/preparation/`,
        {signal: controller.signal},
    ))
    if (!alive || controller.signal.aborted || context !== contextGeneration
        || generation !== loadGeneration || serviceId !== props.serviceId) return
    loading.value = false
    if (!ok) {
        message.value = apiError(status, data)
        return
    }
    const parsed = servicePreparationEnvelope(data, serviceId)
    if (parsed === null) {
        message.value = 'El servidor devolvió una preparación incompleta. Conservamos la vista anterior.'
        return
    }
    payload.value = parsed
    conflict.value = false
    message.value = ''
}

async function updateItem(item: ServicePreparationItem, value: unknown) {
    if (!props.canOperate || !payload.value?.can_edit || conflict.value || loading.value
        || savingItem.value !== null || typeof value !== 'boolean') return
    if (value === item.checked) return
    const parsed = servicePreparationWrite(item.id, value, payload.value.revision)
    if (parsed.body === null) {
        messageVariant.value = 'error'
        message.value = parsed.error
        return
    }
    const serviceId = props.serviceId
    const context = contextGeneration
    const revision = payload.value.revision
    savingItem.value = item.id
    message.value = ''
    messageVariant.value = 'error'
    const {ok, status, data} = await readJson(await cuadernoFetch(
        `/api/cuaderno/services/${serviceId}/preparation/`,
        {method: 'PUT', body: JSON.stringify(parsed.body)},
    ))
    if (!alive || context !== contextGeneration || serviceId !== props.serviceId
        || payload.value?.service_id !== serviceId || payload.value.revision !== revision) return
    savingItem.value = null
    if (!ok) {
        const conflictMessage = servicePreparationConflictMessage(status)
        if (conflictMessage) {
            conflict.value = true
            messageVariant.value = 'warning'
            message.value = conflictMessage
            return
        }
        message.value = apiError(status, data)
        return
    }
    const confirmed = servicePreparationSaveEnvelope(data, serviceId, item.id, value, payload.value)
    if (confirmed === null) {
        message.value = 'El servidor no confirmó la tarea guardada. Conservamos la vista anterior; comprueba el estado antes de volver a intentarlo.'
        return
    }
    payload.value = confirmed
    messageVariant.value = 'success'
    message.value = 'Cambio guardado.'
}

watch(
    () => [props.serviceId, props.serviceState] as const,
    () => {
        contextGeneration += 1
        loadGeneration += 1
        loadController?.abort()
        opened.value = false
        payload.value = null
        loading.value = false
        savingItem.value = null
        conflict.value = false
        message.value = ''
        messageVariant.value = 'error'
    },
)

onBeforeUnmount(() => {
    alive = false
    contextGeneration += 1
    loadGeneration += 1
    loadController?.abort()
})
</script>

<style scoped>
.preparation-item {
    min-width: 0;
}

.preparation-check {
    min-width: 44px;
    min-height: 44px;
}

.min-width-0 {
    min-width: 0;
}

.preserve-lines {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}
</style>
