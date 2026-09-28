<template>
    <v-container>
        <h1 class="text-h5 mb-3">Producción</h1>
        <p class="mb-4">
            El servicio anota comensales en el menú nativo y no descuenta stock.
            Un alérgeno sin declarar no se trata como ausente.
        </p>
        <v-alert v-if="notice" type="info" class="mb-4" role="status">{{ notice }}</v-alert>
        <v-row>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title>Servicio</v-card-title>
                    <v-card-text>
                        <v-text-field v-model="service.title" label="Nombre" />
                        <v-text-field v-model="service.base" label="Comensales previstos" />
                        <v-text-field v-model="service.extra" label="Añadidos" />
                        <v-text-field v-model="service.cancelled" label="Cancelados" />
                        <v-btn color="primary" @click="saveService">Anotar servicio</v-btn>
                        <p class="mt-2" role="status">{{ serviceMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card class="print-card">
                    <v-card-title>Ficha</v-card-title>
                    <v-card-text>
                        <v-text-field v-model="sheet.component" label="Componente" />
                        <v-text-field v-model="sheet.quantity" label="Cantidad" />
                        <v-btn variant="text" @click="addUsage">Añadir línea</v-btn>
                        <v-btn color="primary" @click="consolidate">Consolidar</v-btn>
                        <ul>
                            <li v-for="(line, index) in usages" :key="index">{{ line.component }} · {{ line.quantity }}</li>
                        </ul>
                        <p role="status">{{ sheetMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
            <v-col cols="12" md="6">
                <v-card>
                    <v-card-title>Alérgeno</v-card-title>
                    <v-card-text>
                        <v-text-field v-model="allergen.food" label="Id de alimento" type="number" />
                        <v-text-field v-model="allergen.name" label="Nombre" />
                        <v-select v-model="allergen.state" label="Estado" :items="states" item-title="title" item-value="value" />
                        <v-btn color="primary" @click="saveAllergen">Declarar</v-btn>
                        <p class="mt-2" role="status">{{ allergenMessage }}</p>
                    </v-card-text>
                </v-card>
            </v-col>
        </v-row>
    </v-container>
</template>

<script setup lang="ts">
import {reactive, ref} from "vue"
import {cuadernoFetch, readJson} from "@/cuaderno/api"

const states = [
    {title: "Desconocido", value: "unknown"},
    {title: "Declarado", value: "declared"},
]
const notice = ref("")
const serviceMessage = ref("")
const sheetMessage = ref("")
const allergenMessage = ref("")
const usages = ref<{component: string; quantity: string}[]>([])
const service = reactive({title: "Servicio", base: "40", extra: "5", cancelled: "0"})
const sheet = reactive({component: "", quantity: ""})
const allergen = reactive({food: "", name: "", state: "unknown"})

function explain(status: number) {
    if (status === 403) {
        notice.value = "Producción pertenece a la edición Profesional o superior."
        return notice.value
    }
    return "No se ha podido guardar."
}

function addUsage() {
    if (!sheet.component.trim()) return
    usages.value.push({component: sheet.component.trim(), quantity: sheet.quantity.replace(",", ".") || "0"})
    sheet.component = ""
    sheet.quantity = ""
}

async function saveService() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/services/", {
        method: "POST",
        body: JSON.stringify({
            title: service.title,
            base_covers: service.base.replace(",", "."),
            extra: service.extra.replace(",", "."),
            cancelled: service.cancelled.replace(",", "."),
        }),
    }))
    serviceMessage.value = ok
        ? `${data.covers} comensales. Stock ${data.stock_changed ? "alterado" : "sin cambios"}. Menú ${data.meal_plan}.`
        : explain(status)
}

async function consolidate() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/production/", {
        method: "POST",
        body: JSON.stringify({usages: usages.value}),
    }))
    if (!ok) {
        sheetMessage.value = explain(status)
        return
    }
    const lines = Object.entries(data.needs as Record<string, string>).map(([name, qty]) => `${name}: ${qty}`)
    sheetMessage.value = lines.length ? lines.join(" · ") : "Sin necesidades."
    if (data.stock_changed) sheetMessage.value += " El stock ha cambiado."
}

async function saveAllergen() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/cuaderno/allergens/", {
        method: "POST",
        body: JSON.stringify({
            food: Number(allergen.food),
            name: allergen.name,
            state: allergen.state,
        }),
    }))
    allergenMessage.value = ok
        ? `${data.state}. No declarar no significa que el alérgeno esté ausente.`
        : explain(status)
}
</script>

<style scoped>
@media print {
    .print-card { break-inside: avoid; }
}
</style>
