<template>
    <section aria-labelledby="price-history-title">
        <div class="d-flex flex-wrap align-center justify-space-between ga-2 mb-2">
            <div>
                <h3 id="price-history-title" class="text-subtitle-1 font-weight-bold mb-0">Historial del formato</h3>
                <p class="text-body-2 text-medium-emphasis mb-0">Incluye precios futuros, que todavía no son actuales.</p>
            </div>
            <v-btn variant="text" min-height="44" :disabled="loading" @click="load(offset)">Actualizar historial</v-btn>
        </div>

        <v-progress-linear v-if="loading && !payload" indeterminate aria-label="Cargando historial de precios" />
        <v-alert v-if="error" type="error" variant="tonal" role="alert" class="mb-3">
            {{ error }}
        </v-alert>
        <template v-if="payload">
            <p v-if="payload.items.length" class="text-body-2 mb-3">
                {{ payload.count }} versiones · página {{ offset + 1 }}–{{ offset + payload.items.length }}
            </p>
            <p v-if="!payload.items.length" class="text-medium-emphasis">Este formato todavía no tiene precios.</p>
            <v-list v-else lines="three" class="pa-0">
                <v-list-item v-for="item in payload.items" :key="item.id" class="price-row px-0">
                    <template #prepend>
                        <v-icon :icon="item.is_current ? 'mdi-check-circle' : 'mdi-history'" class="me-3" />
                    </template>
                    <v-list-item-title>{{ priceAmountLabel(item.amount, payload.currency) }}</v-list-item-title>
                    <v-list-item-subtitle>
                        Vigencia: {{ dateLabel(item.valid_from) }} · creado: {{ dateLabel(item.created_at) }}
                    </v-list-item-subtitle>
                    <v-list-item-subtitle v-if="item.note">{{ item.note }}</v-list-item-subtitle>
                    <template #append>
                        <div class="d-flex flex-column align-end ga-1 ms-2">
                            <v-chip size="small" :color="item.is_current ? 'success' : undefined" variant="tonal">
                                {{ priceTimingLabel(item, payload.as_of) }}
                            </v-chip>
                            <v-chip v-if="item.explicit_free" size="small" variant="outlined">Gratis explícitamente</v-chip>
                        </div>
                    </template>
                </v-list-item>
            </v-list>
            <div class="d-flex flex-wrap justify-space-between ga-2 mt-3">
                <v-btn
                    variant="outlined"
                    min-height="44"
                    :disabled="loading || offset === 0"
                    @click="loadPrevious"
                >
                    Anteriores
                </v-btn>
                <v-btn
                    variant="outlined"
                    min-height="44"
                    :disabled="loading || payload.next_offset === null"
                    @click="payload.next_offset !== null && load(payload.next_offset)"
                >
                    Siguientes
                </v-btn>
            </div>
        </template>
    </section>
</template>

<script setup lang="ts">
import {onBeforeUnmount, ref, watch} from 'vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {
    PRICE_HISTORY_PAGE_SIZE,
    priceAmountLabel,
    priceHistoryEnvelope,
    priceHistoryRequest,
    priceTimingLabel,
    type PriceHistoryEnvelope,
} from '@/cuaderno/priceHistoryUi'

const props = defineProps<{packageId: number; refreshToken: number}>()
const payload = ref<PriceHistoryEnvelope | null>(null)
const loading = ref(false)
const error = ref('')
const offset = ref(0)
let requestGeneration = 0
let controller: AbortController | null = null

function contextKey() {
    return `${props.packageId}:${props.refreshToken}`
}

function dateLabel(value: string) {
    return new Intl.DateTimeFormat('es-ES', {dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value))
}

function loadPrevious() {
    void load(Math.max(0, offset.value - PRICE_HISTORY_PAGE_SIZE))
}

async function load(requestedOffset: number) {
    if (loading.value && requestedOffset === offset.value) return
    const packageId = props.packageId
    const key = contextKey()
    const generation = ++requestGeneration
    controller?.abort()
    controller = new AbortController()
    const currentController = controller
    loading.value = true
    error.value = ''
    const {ok, status, data} = await readJson(await cuadernoFetch(
        priceHistoryRequest(packageId, requestedOffset),
        {signal: currentController.signal},
    ))
    if (
        currentController.signal.aborted
        || generation !== requestGeneration
        || packageId !== props.packageId
        || key !== contextKey()
    ) return
    loading.value = false
    if (!ok) {
        error.value = apiError(status, data)
        return
    }
    const parsed = priceHistoryEnvelope(data, packageId, requestedOffset)
    if (parsed === null) {
        error.value = 'El servidor devolvió un historial incompleto. Conservamos la página anterior.'
        return
    }
    payload.value = parsed
    offset.value = requestedOffset
}

watch(
    () => [props.packageId, props.refreshToken] as const,
    () => {
        ++requestGeneration
        controller?.abort()
        payload.value = null
        offset.value = 0
        loading.value = false
        error.value = ''
        void load(0)
    },
    {immediate: true},
)

onBeforeUnmount(() => {
    ++requestGeneration
    controller?.abort()
})
</script>

<style scoped>
.price-row {
    min-height: 64px;
}
</style>
