<template>
    <v-container>
        <v-btn :to="{name: 'PantryPage'}" variant="text" prepend-icon="fa-solid fa-arrow-left" min-height="44" class="mb-3">Despensa y existencias</v-btn>
        <h1 class="text-h5 mb-3">Compras y movimientos</h1>
        <p class="mb-4">Los pedidos no cambian el saldo. Una recepción confirmada sí actualiza la existencia nativa y conserva su documento.</p>
        <v-alert v-if="editionError" type="info" class="mb-4" role="status">{{ editionError }}</v-alert>

        <purchasing-panel class="mb-6" />

        <v-row>
            <v-col cols="12" md="6">
                <v-card class="print-card h-100">
                    <v-card-title>Movimiento manual</v-card-title>
                    <v-card-subtitle>Para recepciones de pedidos usa el flujo de compra superior.</v-card-subtitle>
                    <v-card-text>
                        <v-model-select v-model="move.entry" model="InventoryEntry" label="Existencia del inventario" search-on-load />
                        <v-btn :to="{name: 'PantryPage'}" variant="text" min-height="44" class="mb-3">Crear o consultar existencias en la despensa</v-btn>
                        <v-select v-model="move.kind" label="Tipo" :items="kinds" item-title="title" item-value="value" />
                        <v-text-field v-model="move.quantity" label="Cantidad" inputmode="decimal" />
                        <v-btn color="primary" class="mr-2" :loading="moving" min-height="44" @click="requestMove">Aplicar movimiento</v-btn>
                        <v-btn variant="text" :loading="loadingHistory" min-height="44" @click="loadHistory">Actualizar historial</v-btn>
                        <p class="mt-2" role="status" aria-live="polite">{{ moveMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card class="h-100">
                    <v-card-title>Historial de existencias</v-card-title>
                    <v-card-text>
                        <v-list v-if="history.length">
                            <v-list-item v-for="row in history" :key="row.id">
                                <v-list-item-title>{{ kindLabel(row.kind) }} · {{ row.quantity }}</v-list-item-title>
                                <v-list-item-subtitle class="text-wrap">
                                    existencia {{ row.entry }} · saldo {{ row.balance }}
                                    <span v-if="row.reverses"> · revierte {{ row.reverses }}</span>
                                    <span v-if="isPurchaseMovement(row)"> · recepción de pedido {{ row.metadata_snapshot.origin.id }}</span>
                                    <span v-if="replacementValuationLabel(row)" class="d-block mt-1">{{ replacementValuationLabel(row) }}</span>
                                    <span v-if="isServiceProductionMovement(row)" class="d-block mt-1">
                                        Movimiento de producción: la reversión completa del servicio aún no está disponible.
                                    </span>
                                </v-list-item-subtitle>
                                <template #append>
                                    <v-btn v-if="canReverseGeneric(row, history)" variant="text" min-height="44" :disabled="moving" @click="reversal = row; confirmation = 'reverse'">Revertir</v-btn>
                                </template>
                            </v-list-item>
                        </v-list>
                        <p v-if="history.some(hasReplacementValuation)" class="text-caption mt-3">
                            Estas cifras son estimaciones de reposición; no son valoración FIFO, coste medio ni beneficio.
                        </p>
                        <p v-if="!history.length && !loadingHistory && !editionError">Todavía no hay movimientos registrados.</p>
                    </v-card-text>
                </v-card>
            </v-col>
        </v-row>

        <v-dialog :model-value="!!confirmation" max-width="480" @update:model-value="confirmation = null">
            <v-card>
                <v-card-title>{{ confirmation === 'reverse' ? 'Revertir movimiento' : 'Registrar desperdicio' }}</v-card-title>
                <v-card-text>{{ confirmation === 'reverse' ? 'Se registrará un movimiento compensatorio. El original seguirá en el historial.' : `Se descontarán ${move.quantity} de la existencia seleccionada. Comprueba la cantidad antes de confirmar.` }}</v-card-text>
                <v-card-actions>
                    <v-btn min-height="44" @click="confirmation = null">Cancelar</v-btn>
                    <v-btn color="primary" min-height="44" @click="confirmMovement">Confirmar</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </v-container>
</template>

<script setup lang="ts">
import {onMounted, reactive, ref} from 'vue'
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import PurchasingPanel from '@/cuaderno/components/PurchasingPanel.vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError, decimalInput} from '@/cuaderno/forms'
import {inventoryRequests} from '@/cuaderno/inventoryRequests'
import {
    canReverseGeneric,
    hasReplacementValuation,
    isPurchaseMovement,
    isServiceProductionMovement,
    replacementValuationLabel,
} from '@/cuaderno/stockMovementUi'

const kinds = [
    {title: 'Recepción sin pedido', value: 'receipt'},
    {title: 'Consumo', value: 'consume'},
    {title: 'Desperdicio', value: 'waste'},
]
const editionError = ref('')
const moveMessage = ref('')
const history = ref<any[]>([])
const move = reactive({entry: null as any, kind: 'receipt', quantity: ''})
const moving = ref(false)
const loadingHistory = ref(false)
const confirmation = ref<'waste' | 'reverse' | null>(null)
const reversal = ref<any>(null)
const pendingMovement = inventoryRequests()

function movementKey(payload: unknown) {
    return pendingMovement.key('cuaderno-stock', payload)
}
function kindLabel(kind: string) { return kinds.find(item => item.value === kind)?.title || (kind === 'reversal' ? 'Reversión' : kind) }

function requestMove() {
    if (moving.value) return
    if (!move.entry?.id || !decimalInput(move.quantity)) { moveMessage.value = 'Selecciona una existencia e indica una cantidad positiva.'; return }
    if (move.kind === 'waste') confirmation.value = 'waste'
    else sendMove()
}
function confirmMovement() {
    const action = confirmation.value
    confirmation.value = null
    if (action === 'reverse') reverse(reversal.value)
    else sendMove()
}
async function sendMove() {
    if (moving.value) return
    moving.value = true
    const payload = {entry: move.entry.id, kind: move.kind, quantity: decimalInput(move.quantity)}
    const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/movements/', {
        method: 'POST', body: JSON.stringify({...payload, idempotency_key: movementKey(payload)}),
    }))
    moving.value = false
    moveMessage.value = ok ? `Saldo ${data.balance}.` : apiError(status, data)
    if (ok) { move.quantity = ''; pendingMovement.complete('cuaderno-stock', payload); await loadHistory() }
}
async function reverse(row: any) {
    if (moving.value || !canReverseGeneric(row, history.value)) return
    moving.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/movements/', {
        method: 'POST', body: JSON.stringify({reverse_of: row.id, idempotency_key: `cuaderno-ui-reverse-${row.id}`}),
    }))
    moving.value = false
    moveMessage.value = ok ? `Revertido. Saldo ${data.balance}.` : apiError(status, data)
    if (ok) await loadHistory()
}
async function loadHistory() {
    loadingHistory.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/movements/'))
    loadingHistory.value = false
    if (ok) { history.value = data; editionError.value = '' }
    else editionError.value = apiError(status, data)
}

onMounted(loadHistory)
</script>

<style scoped>
@media print { .print-card { break-inside: avoid; } }
</style>
