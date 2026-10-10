<template>
    <v-alert v-if="!props.canOperate" type="info" variant="tonal" class="mb-4">Modo Consulta: las compras están disponibles solo para lectura.</v-alert>
    <div>
    <v-row>
        <v-col cols="12" lg="5">
            <v-card class="h-100">
                <v-card-title>Oferta de proveedor</v-card-title>
                <v-card-subtitle>El precio queda en el historial del proveedor y no cambia el precio de referencia.</v-card-subtitle>
                <v-card-text>
                    <v-select
                        v-model="offer.package"
                        :items="packages"
                        :item-title="packageLabel"
                        return-object
                        label="Formato de compra"
                        :loading="loadingCatalog"
                        :disabled="!props.canOperate"
                        no-data-text="Crea primero un formato en Ingredientes y precios"
                    />
                    <v-model-select v-model="offer.supplier" model="Supermarket" label="Proveedor" :search-on-load="props.canOperate" create :disabled="!props.canOperate" />
                    <v-text-field
                        v-model="offer.amount"
                        label="Precio por envase"
                        suffix="€"
                        inputmode="decimal"
                        :disabled="offer.explicitFree || !props.canOperate"
                    />
                    <v-checkbox v-model="offer.explicitFree" label="Oferta expresamente gratuita" hide-details :disabled="!props.canOperate" />
                    <v-btn color="primary" min-height="44" :loading="savingOffer" :disabled="!props.canOperate" @click="saveOffer">Guardar oferta</v-btn>
                    <p class="mt-2" role="status" aria-live="polite">{{ offerMessage }}</p>
                </v-card-text>
            </v-card>
        </v-col>

        <v-col cols="12" lg="7">
            <v-card class="h-100">
                <v-card-title>Nuevo pedido</v-card-title>
                <v-card-subtitle>Un pedido no aumenta las existencias. Recíbelo cuando llegue.</v-card-subtitle>
                <v-card-text>
                    <v-select
                        v-model="draft.package"
                        :items="packages"
                        :item-title="packageLabel"
                        return-object
                        label="Formato"
                        :loading="loadingCatalog"
                        :disabled="!props.canOperate"
                    />
                    <v-model-select v-model="draft.supplier" model="Supermarket" label="Proveedor" :search-on-load="props.canOperate" :disabled="!props.canOperate" />
                    <v-select
                        v-model="draft.offer"
                        :items="matchingOffers"
                        :item-title="offerLabel"
                        return-object
                        clearable
                        label="Oferta (opcional)"
                        :disabled="!props.canOperate"
                        no-data-text="No hay ofertas para este formato y proveedor"
                    />
                    <v-text-field v-model="draft.packageCount" label="Número de envases" inputmode="decimal" :disabled="!props.canOperate" />
                    <v-alert v-if="draft.package" type="info" variant="tonal" class="mb-3">
                        Cantidad del pedido: {{ draftQuantity || '—' }} {{ draft.package.unit_name }}.
                    </v-alert>
                    <v-btn color="primary" min-height="44" :loading="savingOrder" :disabled="!props.canOperate" @click="saveOrder">Crear borrador</v-btn>
                    <p class="mt-2" role="status" aria-live="polite">{{ orderMessage }}</p>
                </v-card-text>
            </v-card>
        </v-col>

        <v-col cols="12">
            <StockMinimumPanel :can-operate="props.canOperate" @loaded="rememberFoods" />
        </v-col>

        <v-col cols="12">
            <v-card>
                <v-card-title class="d-flex align-center flex-wrap ga-2">
                    <span>Pedidos</span>
                    <v-spacer />
                    <v-btn variant="text" min-height="44" :loading="loadingOrders" @click="loadOrders">Actualizar</v-btn>
                </v-card-title>
                <v-card-text>
                    <v-alert v-if="ordersMessage" type="error" variant="tonal" class="mb-3" role="alert">{{ ordersMessage }}</v-alert>
                    <v-list v-if="orders.length" lines="three">
                        <v-list-item v-for="order in orders" :key="order.id" class="order-row px-0">
                            <v-list-item-title class="font-weight-medium">
                                {{ order.supplier_name || 'Sin proveedor' }} · {{ order.quantity }} {{ unitName(order) }}
                            </v-list-item-title>
                            <v-list-item-subtitle class="text-wrap">
                                {{ stateLabel(order.state) }} · recibido {{ order.received_quantity }}
                                <span v-if="order.state !== 'cancelled'"> · pendiente {{ remaining(order) }}</span>
                                <span v-else> · resto cancelado {{ remaining(order) }}</span>
                                <span v-if="order.price_snapshot !== null"> · {{ order.price_snapshot }} {{ order.currency_snapshot }}</span>
                                <span v-else> · precio desconocido</span>
                            </v-list-item-subtitle>
                            <template #append>
                                <div class="d-flex flex-wrap justify-end ga-1 order-actions">
                                    <v-btn
                                        v-if="order.state === 'draft'"
                                        size="small"
                                        variant="tonal"
                                        min-height="44"
                                        :loading="busyOrder === order.id"
                                        :disabled="!props.canOperate"
                                        @click="changeOrder(order, 'order')"
                                    >Enviar pedido</v-btn>
                                    <v-btn
                                        v-if="['draft', 'ordered', 'part_received'].includes(order.state)"
                                        size="small"
                                        variant="text"
                                        min-height="44"
                                        :loading="busyOrder === order.id"
                                        :disabled="!props.canOperate"
                                        @click="changeOrder(order, 'cancel')"
                                    >Cancelar</v-btn>
                                    <v-btn
                                        v-if="['ordered', 'part_received'].includes(order.state)"
                                        size="small"
                                        color="primary"
                                        variant="tonal"
                                        min-height="44"
                                        :disabled="receiving || !props.canOperate"
                                        @click="openReceipt(order)"
                                    >Recibir</v-btn>
                                    <v-btn size="small" variant="text" min-height="44" @click="toggleReceipts(order)">
                                        Recepciones
                                    </v-btn>
                                </div>
                            </template>

                            <div v-if="receiptOrder?.id === order.id" class="receipt-form mt-3 pa-3 rounded border">
                                <p class="font-weight-medium mb-2">Recibir {{ order.supplier_name || `pedido ${order.id}` }}</p>
                                <v-model-select
                                    v-model="receipt.entry"
                                    model="InventoryEntry"
                                    label="Existencia de destino"
                                    hint="Debe ser el mismo alimento y hogar del pedido"
                                    persistent-hint
                                    search-on-load
                                    :disabled="receiving || !props.canOperate"
                                />
                                <v-text-field
                                    v-model="receipt.quantity"
                                    :label="`Cantidad recibida (${unitName(order)})`"
                                    inputmode="decimal"
                                    :disabled="receiving || !props.canOperate"
                                />
                                <div class="d-flex flex-wrap ga-2">
                                    <v-btn color="primary" min-height="44" :loading="receiving" :disabled="!props.canOperate" @click="receive(order)">Confirmar recepción</v-btn>
                                    <v-btn variant="text" min-height="44" :disabled="receiving" @click="closeReceipt">Cerrar</v-btn>
                                </div>
                                <p class="mt-2" role="status" aria-live="polite">{{ receiptMessage }}</p>
                            </div>

                            <div v-if="expandedReceipts === order.id" class="mt-3 pa-3 rounded border">
                                <v-progress-linear v-if="loadingReceipts" indeterminate class="mb-2" />
                                <v-list v-if="receiptsByOrder[order.id]?.length" density="compact">
                                    <v-list-item v-for="document in receiptsByOrder[order.id]" :key="document.id">
                                        <v-list-item-title>{{ document.quantity }} {{ unitName(order) }}</v-list-item-title>
                                        <v-list-item-subtitle>
                                            Movimiento {{ document.movement }}
                                            <span v-if="document.reversed_by"> · revertido por {{ document.reversed_by }}</span>
                                        </v-list-item-subtitle>
                                        <template #append>
                                            <v-btn
                                                v-if="!document.reversed_by"
                                                variant="text"
                                                min-height="44"
                                                :loading="reversingReceipt === document.id"
                                                :disabled="!props.canOperate"
                                                @click="reverseReceipt(order, document)"
                                            >Revertir recepción</v-btn>
                                        </template>
                                    </v-list-item>
                                </v-list>
                                <p v-else-if="!loadingReceipts && !receiptsErrors[order.id]">No hay recepciones en este pedido.</p>
                                <v-alert v-if="receiptsErrors[order.id]" type="error" variant="tonal" role="alert">{{ receiptsErrors[order.id] }}</v-alert>
                            </div>
                        </v-list-item>
                    </v-list>
                    <v-alert v-else-if="!loadingOrders && !ordersMessage" type="info" variant="tonal">
                        Todavía no hay pedidos. Guarda una oferta si quieres congelar proveedor y precio, y crea el primer borrador.
                    </v-alert>
                </v-card-text>
            </v-card>
        </v-col>

        <v-col cols="12">
            <v-card>
                <v-card-title class="d-flex align-center flex-wrap ga-2">
                    <span>Propuesta de reposición</span>
                    <v-spacer />
                    <v-btn color="primary" variant="tonal" min-height="44" :disabled="!canOperate" :loading="loadingReplenishment" @click="loadReplenishment">
                        Calcular desde servicios confirmados
                    </v-btn>
                </v-card-title>
                <v-card-subtitle>Incluye reservas y otros servicios confirmados, menos stock utilizable del hogar; no crea pedidos.</v-card-subtitle>
                <v-card-text>
                    <div class="d-flex flex-wrap ga-3 mb-3">
                        <v-text-field v-model="replenishmentFrom" type="date" label="Necesidades desde" :disabled="loadingReplenishment" hide-details />
                        <v-text-field v-model="replenishmentTo" type="date" label="Necesidades hasta" :disabled="loadingReplenishment" hide-details />
                    </div>
                    <v-alert v-if="replenishmentMessage" type="error" variant="tonal" class="mb-3">{{ replenishmentMessage }}</v-alert>
                    <v-table v-if="replenishment.length" density="comfortable" class="replenishment-table">
                        <thead><tr><th>Alimento</th><th>Necesario</th><th>Disponible</th><th>Mínimo</th><th>Objetivo</th><th>Falta</th><th>Compra propuesta</th><th>Exceso</th><th>Precio ref.</th></tr></thead>
                        <tbody>
                            <tr v-for="item in replenishment" :key="`${item.food}-${item.unit}`">
                                <td>{{ foodName(item.food) }}</td>
                                <td>{{ item.required }}</td>
                                <td>{{ item.usable_stock }}</td>
                                <td>
                                    {{ minimumLabel(item.minimum_stock) }}
                                    <ul v-if="item.location_shortfalls.length" class="location-shortfalls">
                                        <li v-for="shortfall in item.location_shortfalls" :key="shortfall.location">
                                            {{ shortfall.location_name }}: mín. {{ shortfall.minimum_stock }}, disponible {{ shortfall.usable_stock }}, falta {{ shortfall.missing }}
                                        </li>
                                    </ul>
                                </td>
                                <td>{{ minimumLabel(item.target_stock) }}</td>
                                <td>{{ item.missing }}</td>
                                <td>{{ item.packages === null ? 'Sin formato' : `${item.packages} envases · ${item.purchase_quantity}` }}</td>
                                <td>{{ excessLabel(item) }}</td>
                                <td>{{ item.reference_price === null ? 'Desconocido' : `${item.reference_price} ${item.currency}` }}</td>
                            </tr>
                        </tbody>
                    </v-table>
                    <div v-if="replenishment.length" class="replenishment-cards">
                        <v-card v-for="item in replenishment" :key="`mobile-${item.food}-${item.unit}`" variant="outlined" class="mb-2">
                            <v-card-title class="text-body-1">{{ foodName(item.food) }}</v-card-title>
                            <v-card-text>
                                <dl class="compact-values">
                                    <div><dt>Necesario</dt><dd>{{ item.required }}</dd></div>
                                    <div><dt>Disponible</dt><dd>{{ item.usable_stock }}</dd></div>
                                    <div><dt>Mínimo</dt><dd>{{ minimumLabel(item.minimum_stock) }}</dd></div>
                                    <div><dt>Objetivo</dt><dd>{{ minimumLabel(item.target_stock) }}</dd></div>
                                    <div><dt>Falta</dt><dd>{{ item.missing }}</dd></div>
                                    <div><dt>Compra</dt><dd>{{ item.packages === null ? 'Sin formato' : `${item.packages} envases · ${item.purchase_quantity}` }}</dd></div>
                                    <div><dt>Exceso por envases</dt><dd>{{ excessLabel(item) }}</dd></div>
                                    <div><dt>Precio ref.</dt><dd>{{ item.reference_price === null ? 'Desconocido' : `${item.reference_price} ${item.currency}` }}</dd></div>
                                </dl>
                                <ul v-if="item.location_shortfalls.length" class="mt-3 pl-4">
                                    <li v-for="shortfall in item.location_shortfalls" :key="`mobile-location-${shortfall.location}`">
                                        {{ shortfall.location_name }}: mínimo {{ shortfall.minimum_stock }}, disponible {{ shortfall.usable_stock }}, falta {{ shortfall.missing }}
                                    </li>
                                </ul>
                            </v-card-text>
                        </v-card>
                    </div>
                    <p v-else-if="!loadingReplenishment && !replenishmentMessage">No hay necesidades confirmadas pendientes de mostrar.</p>
                </v-card-text>
            </v-card>
        </v-col>
    </v-row>
    </div>
</template>

<script setup lang="ts">
import {computed, onMounted, reactive, ref, watch} from 'vue'
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import StockMinimumPanel from '@/cuaderno/components/StockMinimumPanel.vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError, decimalInput} from '@/cuaderno/forms'
import {inventoryRequests, sameReceiptDraft} from '@/cuaderno/inventoryRequests'
import {replenishmentEnvelope, replenishmentExcess} from '@/cuaderno/stockMinimumUi'
import type {ReplenishmentRow} from '@/cuaderno/stockMinimumUi'
import {packageSummaries} from '@/cuaderno/priceHistoryUi'
import {purchaseOffers, purchaseOrders, purchaseReceipts} from '@/cuaderno/purchasingUi'
import type {PurchaseOfferRow as Offer, PurchaseOrderRow as Order, PurchaseReceiptRow as ReceiptDocument} from '@/cuaderno/purchasingUi'

const props = withDefaults(defineProps<{canOperate?: boolean}>(), {canOperate: true})

type Package = {id: number; food: number; food_name: string; unit: number; unit_name: string; label: string; quantity: string}
const packages = ref<Package[]>([])
const offers = ref<Offer[]>([])
const orders = ref<Order[]>([])
const replenishment = ref<ReplenishmentRow[]>([])
const replenishmentFrom = ref('')
const replenishmentTo = ref('')
const receiptsByOrder = reactive<Record<number, ReceiptDocument[]>>({})
const foods = reactive<Record<number, string>>({})
const offer = reactive({package: null as Package | null, supplier: null as any, amount: '', explicitFree: false})
const draft = reactive({package: null as Package | null, supplier: null as any, offer: null as Offer | null, packageCount: ''})
const receipt = reactive({entry: null as any, quantity: ''})
const receiptOrder = ref<Order | null>(null)
const expandedReceipts = ref<number | null>(null)
const receiptRequests = inventoryRequests()
const receiptsErrors = reactive<Record<number, string>>({})
const loadingCatalog = ref(false)
const savingOffer = ref(false)
const savingOrder = ref(false)
const loadingOrders = ref(false)
const busyOrder = ref<number | null>(null)
const receiving = ref(false)
const loadingReceipts = ref(false)
const reversingReceipt = ref<number | null>(null)
const loadingReplenishment = ref(false)
const offerMessage = ref('')
const orderMessage = ref('')
const ordersMessage = ref('')
const receiptMessage = ref('')
const replenishmentMessage = ref('')

function packageLabel(item: Package) { return `${item.food_name} · ${item.label} (${item.quantity} ${item.unit_name})` }
function offerLabel(item: Offer) { return `${item.amount} ${item.currency} · ${new Date(item.valid_from).toLocaleDateString('es-ES')}` }
function unitName(order: Order) { return packages.value.find(item => item.id === order.package)?.unit_name || `unidad ${order.unit}` }
function foodName(id: number) { return foods[id] || `Alimento ${id}` }
function rememberFoods(values: Record<number, string>) { Object.assign(foods, values) }
function minimumLabel(value: string | null) { return value === null ? '—' : value }
function excessLabel(item: ReplenishmentRow) { return replenishmentExcess(item.purchase_quantity, item.missing) ?? '—' }
function stateLabel(state: string) { return ({draft: 'Borrador', ordered: 'Pedido', part_received: 'Recibido parcialmente', received: 'Recibido', cancelled: 'Cancelado'} as Record<string, string>)[state] || state }
function decimalParts(value: string) {
    const normalized = decimalInput(value, true)
    if (normalized === null) return null
    const [whole, fraction = ''] = normalized.split('.')
    return {integer: BigInt(`${whole}${fraction}`), scale: fraction.length}
}
function decimalText(integer: bigint, scale: number) {
    const negative = integer < 0n
    let digits = (negative ? -integer : integer).toString().padStart(scale + 1, '0')
    let value = scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}` : digits
    if (scale) value = value.replace(/0+$/, '').replace(/\.$/, '')
    return `${negative ? '-' : ''}${value}`
}
function multiplyDecimal(left: string, right: string) {
    const a = decimalParts(left); const b = decimalParts(right)
    return a && b ? decimalText(a.integer * b.integer, a.scale + b.scale) : null
}
function subtractDecimal(left: string, right: string) {
    const a = decimalParts(left); const b = decimalParts(right)
    if (!a || !b) return '—'
    const scale = Math.max(a.scale, b.scale)
    const result = a.integer * 10n ** BigInt(scale - a.scale) - b.integer * 10n ** BigInt(scale - b.scale)
    return decimalText(result < 0n ? 0n : result, scale)
}

const draftQuantity = computed(() => draft.package ? multiplyDecimal(draft.package.quantity, draft.packageCount) : null)
const matchingOffers = computed(() => offers.value.filter(item => item.package === draft.package?.id && (!draft.supplier?.id || item.supplier === draft.supplier.id)))
watch(() => [draft.package?.id, draft.supplier?.id], () => { draft.offer = null })
watch(() => offer.explicitFree, value => { if (value) offer.amount = '0' })
function remaining(order: Order) { return subtractDecimal(order.quantity, order.received_quantity) }

async function loadCatalog() {
    loadingCatalog.value = true
    const [packageResponse, offerResponse] = await Promise.all([
        readJson(await cuadernoFetch('/api/cuaderno/packages/')),
        readJson(await cuadernoFetch('/api/cuaderno/purchase-offers/')),
    ])
    loadingCatalog.value = false
    if (packageResponse.ok) {
        const parsed = packageSummaries(packageResponse.data)
        if (parsed === null) offerMessage.value = 'El servidor devolvió formatos incompletos. Conservamos el catálogo anterior.'
        else {
            packages.value = parsed
            packages.value.forEach(item => { foods[item.food] = item.food_name })
        }
    } else offerMessage.value = apiError(packageResponse.status, packageResponse.data)
    if (offerResponse.ok) {
        const parsed = purchaseOffers(offerResponse.data)
        if (parsed === null) offerMessage.value = 'El servidor devolvió ofertas incompletas. Conservamos las ofertas anteriores.'
        else offers.value = parsed
    }
    else offerMessage.value = apiError(offerResponse.status, offerResponse.data)
}

async function saveOffer() {
    if (!props.canOperate) return
    if (savingOffer.value) return
    const amount = decimalInput(offer.amount, offer.explicitFree)
    if (!offer.package?.id || !offer.supplier?.id || amount === null) {
        offerMessage.value = 'Selecciona formato y proveedor e indica un precio válido.'; return
    }
    savingOffer.value = true
    const result = await readJson(await cuadernoFetch('/api/cuaderno/purchase-offers/', {method: 'POST', body: JSON.stringify({
        package: offer.package.id, supplier: offer.supplier.id, amount, explicit_free: offer.explicitFree,
    })}))
    savingOffer.value = false
    if (!result.ok) { offerMessage.value = apiError(result.status, result.data); return }
    const saved = purchaseOffers([result.data])
    if (saved === null) { offerMessage.value = 'El servidor no confirmó la oferta guardada. Conservamos el formulario.'; return }
    offerMessage.value = 'Oferta guardada en el historial.'
    offer.amount = ''; offer.explicitFree = false; offers.value.unshift(saved[0]!)
}

async function saveOrder() {
    if (!props.canOperate) return
    if (savingOrder.value) return
    const count = decimalInput(draft.packageCount)
    const quantity = draftQuantity.value
    if (!draft.package?.id || !draft.supplier?.id || !count || !quantity) {
        orderMessage.value = 'Selecciona formato y proveedor e indica un número de envases positivo.'; return
    }
    savingOrder.value = true
    const result = await readJson(await cuadernoFetch('/api/cuaderno/purchase-orders/', {method: 'POST', body: JSON.stringify({
        package: draft.package.id, supplier: draft.supplier.id, offer: draft.offer?.id ?? null,
        package_count: count, quantity,
    })}))
    savingOrder.value = false
    if (!result.ok) { orderMessage.value = apiError(result.status, result.data); return }
    const saved = purchaseOrders([result.data])
    if (saved === null) { orderMessage.value = 'El servidor no confirmó el pedido creado. Conservamos el formulario.'; return }
    orderMessage.value = `Borrador ${saved[0]!.id} creado sin cambiar existencias.`
    draft.packageCount = ''; draft.offer = null; await loadOrders()
}

async function loadOrders() {
    loadingOrders.value = true; ordersMessage.value = ''
    const result = await readJson(await cuadernoFetch('/api/cuaderno/purchase-orders/'))
    loadingOrders.value = false
    if (result.ok) {
        const parsed = purchaseOrders(result.data)
        if (parsed === null) ordersMessage.value = 'El servidor devolvió pedidos incompletos. Conservamos la lista anterior.'
        else orders.value = parsed
    }
    else ordersMessage.value = apiError(result.status, result.data)
}
async function changeOrder(order: Order, action: 'order' | 'cancel') {
    if (!props.canOperate) return
    if (busyOrder.value !== null) return
    busyOrder.value = order.id
    const result = await readJson(await cuadernoFetch(`/api/cuaderno/purchase-orders/${order.id}/`, {method: 'POST', body: JSON.stringify({action})}))
    busyOrder.value = null
    if (result.ok) {
        const saved = purchaseOrders([result.data])
        if (saved === null || saved[0]?.id !== order.id) ordersMessage.value = 'El servidor no confirmó el estado del pedido. Actualiza la lista.'
        else { Object.assign(order, saved[0]); ordersMessage.value = '' }
    }
    else ordersMessage.value = apiError(result.status, result.data)
}

function openReceipt(order: Order) {
    if (!props.canOperate) return
    if (receiving.value) return
    receiptOrder.value = order; receiptMessage.value = ''; receipt.entry = null; receipt.quantity = ''
}
function closeReceipt() {
    if (receiving.value) return
    receiptOrder.value = null; receiptMessage.value = ''; receipt.entry = null; receipt.quantity = ''
}
function receiptKey(orderId: number, payload: object) {
    return receiptRequests.key(`purchase-receipt:${orderId}`, payload)
}
async function receive(order: Order) {
    if (!props.canOperate) return
    if (receiving.value) return
    const quantity = decimalInput(receipt.quantity)
    if (!receipt.entry?.id || !quantity) { receiptMessage.value = 'Selecciona la existencia de destino e indica la cantidad recibida.'; return }
    const payload = {entry: receipt.entry.id, quantity}
    const submittedDraft = {order: order.id, entry: receipt.entry.id as number, quantity: receipt.quantity}
    receiving.value = true
    const result = await readJson(await cuadernoFetch(`/api/cuaderno/purchase-orders/${order.id}/receipts/`, {method: 'POST', body: JSON.stringify({...payload, idempotency_key: receiptKey(order.id, payload)})}))
    receiving.value = false
    const sameContext = receiptOrder.value?.id === order.id
    const saved = result.ok ? purchaseReceipts([result.data]) : null
    if (sameContext) receiptMessage.value = saved ? 'Recepción confirmada. Las existencias se han actualizado una vez.'
        : result.ok ? 'El servidor no confirmó la recepción. Conservamos el formulario.' : apiError(result.status, result.data)
    if (saved) {
        receiptRequests.complete(`purchase-receipt:${order.id}`, payload)
        if (sameReceiptDraft(receiptOrder.value?.id ?? null, receipt.entry?.id ?? null, receipt.quantity, submittedDraft)) receipt.quantity = ''
        await Promise.all([loadOrders(), loadReceipts(order.id)])
    }
}
async function loadReceipts(orderId: number) {
    loadingReceipts.value = true
    receiptsErrors[orderId] = ''
    const result = await readJson(await cuadernoFetch(`/api/cuaderno/purchase-orders/${orderId}/receipts/`))
    loadingReceipts.value = false
    if (result.ok) {
        const parsed = purchaseReceipts(result.data)
        if (parsed === null) receiptsErrors[orderId] = 'El servidor devolvió recepciones incompletas. Conservamos el historial anterior.'
        else receiptsByOrder[orderId] = parsed
    }
    else receiptsErrors[orderId] = apiError(result.status, result.data)
}
async function toggleReceipts(order: Order) {
    expandedReceipts.value = expandedReceipts.value === order.id ? null : order.id
    if (expandedReceipts.value === order.id) await loadReceipts(order.id)
}
async function reverseReceipt(order: Order, document: ReceiptDocument) {
    if (!props.canOperate) return
    if (reversingReceipt.value !== null) return
    reversingReceipt.value = document.id
    const result = await readJson(await cuadernoFetch(`/api/cuaderno/purchase-receipts/${document.id}/reverse/`, {method: 'POST', body: JSON.stringify({idempotency_key: `cuaderno-ui-purchase-reversal-${document.id}`})}))
    reversingReceipt.value = null
    if (result.ok) await Promise.all([loadOrders(), loadReceipts(order.id)])
    else ordersMessage.value = apiError(result.status, result.data)
}

async function loadReplenishment() {
    if (!props.canOperate) return
    if (replenishmentFrom.value && replenishmentTo.value && replenishmentTo.value < replenishmentFrom.value) {
        replenishmentMessage.value = 'El final del periodo no puede ser anterior al inicio.'
        return
    }
    loadingReplenishment.value = true; replenishmentMessage.value = ''
    const range = {
        ...(replenishmentFrom.value ? {from_date: replenishmentFrom.value} : {}),
        ...(replenishmentTo.value ? {to_date: replenishmentTo.value} : {}),
    }
    const result = await readJson(await cuadernoFetch('/api/cuaderno/replenishment/', {method: 'POST', body: JSON.stringify(range)}))
    loadingReplenishment.value = false
    if (!result.ok) {
        replenishmentMessage.value = apiError(result.status, result.data)
        return
    }
    const envelope = replenishmentEnvelope(result.data)
    if (envelope === null) {
        replenishmentMessage.value = 'El servidor devolvió una propuesta de reposición incompleta. Conservamos los datos mostrados.'
        return
    }
    replenishment.value = envelope.items
}

onMounted(async () => { await Promise.all([loadCatalog(), loadOrders()]) })
</script>

<style scoped>
.order-row { border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.order-actions { max-width: 32rem; }
.replenishment-cards { display: none; }
.compact-values > div { display: flex; justify-content: space-between; gap: 1rem; }
.compact-values dt { font-weight: 600; }
.location-shortfalls { min-width: 16rem; padding-inline-start: 1rem; font-size: 0.8rem; }
@media (max-width: 700px) {
    .order-row :deep(.v-list-item__append) { align-self: stretch; margin-inline-start: 0; margin-top: 0.75rem; }
    .order-actions { justify-content: flex-start !important; }
    .receipt-form { width: 100%; }
    .replenishment-table { display: none; }
    .replenishment-cards { display: block; }
}
</style>
