<template>
    <v-container>
        <h1 class="text-h5 mb-3">Almacén</h1>
        <p class="mb-4">
            Pedir no cambia el saldo. Recibir, consumir y desperdiciar escriben el inventario nativo.
            Reintentar la misma clave no duplica el movimiento.
        </p>
        <v-alert v-if="editionError" type="info" class="mb-4" role="status">{{ editionError }}</v-alert>

        <v-row>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title>Pedido</v-card-title>
                    <v-card-text>
                        <v-text-field v-model="order.food" label="Id de alimento" type="number" />
                        <v-text-field v-model="order.unit" label="Id de unidad" type="number" />
                        <v-text-field v-model="order.quantity" label="Cantidad" />
                        <v-text-field v-model="order.supplier" label="Proveedor" />
                        <v-btn color="primary" @click="placeOrder">Registrar pedido</v-btn>
                        <p class="mt-2" role="status">{{ orderMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title>Movimiento</v-card-title>
                    <v-card-text>
                        <v-text-field v-model="move.entry" label="Id de existencia" type="number" />
                        <v-select v-model="move.kind" label="Tipo" :items="kinds" item-title="title" item-value="value" />
                        <v-text-field v-model="move.quantity" label="Cantidad" />
                        <v-text-field v-model="move.key" label="Clave de reintento" />
                        <v-btn color="primary" class="mr-2" @click="sendMove">Aplicar</v-btn>
                        <v-btn variant="text" @click="loadHistory">Actualizar historial</v-btn>
                        <p class="mt-2" role="status">{{ moveMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card>
                    <v-card-title>Reposición</v-card-title>
                    <v-card-text>
                        <v-text-field v-model="buy.required" label="Necesario" />
                        <v-text-field v-model="buy.stock" label="Stock útil" />
                        <v-text-field v-model="buy.pack" label="Tamaño de envase" />
                        <v-btn color="primary" @click="calcBuy">Calcular envases</v-btn>
                        <p class="mt-2" role="status">{{ buyMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card>
                    <v-card-title>Historial</v-card-title>
                    <v-card-text>
                        <v-list v-if="history.length">
                            <v-list-item v-for="row in history" :key="row.id">
                                <v-list-item-title>{{ row.kind }} · {{ row.quantity }}</v-list-item-title>
                                <v-list-item-subtitle>
                                    existencia {{ row.entry }} · saldo {{ row.balance }}
                                    <span v-if="row.reverses"> · revierte {{ row.reverses }}</span>
                                </v-list-item-subtitle>
                                <template #append>
                                    <v-btn size="small" variant="text" @click="reverse(row)">Revertir</v-btn>
                                </template>
                            </v-list-item>
                        </v-list>
                        <p v-else>Todavía no hay movimientos de esta sesión.</p>
                    </v-card-text>
                </v-card>
            </v-col>
        </v-row>
    </v-container>
</template>

<script setup lang="ts">
import {onMounted, reactive, ref} from "vue"
import {cuadernoFetch, readJson} from "@/cuaderno/api"

const kinds = [
    {title: "Recepción", value: "receipt"},
    {title: "Consumo", value: "consume"},
    {title: "Desperdicio", value: "waste"},
]
const editionError = ref("")
const orderMessage = ref("")
const moveMessage = ref("")
const buyMessage = ref("")
const history = ref<any[]>([])
const order = reactive({food: "", unit: "", quantity: "", supplier: ""})
const move = reactive({entry: "", kind: "receipt", quantity: "", key: ""})
const buy = reactive({required: "", stock: "", pack: ""})

function explain(status: number, data: any) {
    if (status === 403) {
        return "Esta pantalla es de la edición Integral."
    }
    if (status === 409) {
        return "La misma clave llegó con otra cantidad. El saldo no se ha duplicado."
    }
    return data?.detail || data?.idempotency_key || "No se ha podido guardar."
}

async function placeOrder() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/orders/", {
        method: "POST",
        body: JSON.stringify({
            food: Number(order.food),
            unit: Number(order.unit),
            quantity: order.quantity.replace(",", "."),
            supplier_name: order.supplier,
        }),
    }))
    orderMessage.value = ok
        ? `Pedido ${data.id}. El stock ${data.stock_unchanged ? "no ha cambiado" : "ha cambiado"}.`
        : explain(status, data)
    if (status === 403) editionError.value = orderMessage.value
}

async function sendMove() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/movements/", {
        method: "POST",
        body: JSON.stringify({
            entry: Number(move.entry),
            kind: move.kind,
            quantity: move.quantity.replace(",", "."),
            idempotency_key: move.key,
        }),
    }))
    moveMessage.value = ok ? `Saldo ${data.balance}.` : explain(status, data)
    if (ok) await loadHistory()
}

async function reverse(row: any) {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/movements/", {
        method: "POST",
        body: JSON.stringify({reverse_of: row.id, idempotency_key: `rev-${row.id}-${Date.now()}`}),
    }))
    moveMessage.value = ok ? `Revertido. Saldo ${data.balance}.` : explain(status, data)
    if (ok) await loadHistory()
}

async function calcBuy() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/replenishment/", {
        method: "POST",
        body: JSON.stringify({
            required: buy.required.replace(",", "."),
            usable_stock: buy.stock.replace(",", "."),
            pack_size: buy.pack.replace(",", "."),
        }),
    }))
    buyMessage.value = ok ? `${data.packs} envases (${data.quantity}).` : explain(status, data)
}

async function loadHistory() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/movements/"))
    if (ok) {
        history.value = data
        editionError.value = ""
    } else if (status === 403) {
        editionError.value = "El historial de almacén pertenece a Integral. Esencial sigue calculando costes."
    }
}

onMounted(loadHistory)
</script>

<style scoped>
@media print {
    .print-card { break-inside: avoid; }
}
</style>
