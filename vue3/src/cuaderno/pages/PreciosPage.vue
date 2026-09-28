<template>
    <v-container>
        <v-card>
            <v-card-title>Formatos y precios</v-card-title>
            <v-card-text>
                <p class="mb-4">
                    El precio es del envase, sin existencias. La moneda del espacio es EUR.
                    Un precio desconocido no se guarda como cero.
                </p>
                <v-row>
                    <v-col cols="12" md="4">
                        <v-text-field v-model="foodId" label="Id de ingrediente" type="number" />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-text-field v-model="unitId" label="Id de unidad" type="number" />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-text-field v-model="label" label="Formato" placeholder="Garrafa 5 L" />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-text-field v-model="quantity" label="Contenido" placeholder="5" />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-text-field v-model="price" label="Precio EUR" placeholder="32,00" />
                    </v-col>
                    <v-col cols="12" md="4" class="d-flex align-center">
                        <v-btn color="primary" @click="save">Guardar precio</v-btn>
                    </v-col>
                </v-row>
                <p v-if="message" class="mt-2">{{ message }}</p>
                <v-list v-if="packages.length">
                    <v-list-item v-for="item in packages" :key="item.id">
                        <v-list-item-title>{{ item.food_name }} — {{ item.label }}</v-list-item-title>
                        <v-list-item-subtitle>
                            {{ item.quantity }} {{ item.unit_name }}
                            <span v-if="item.current_price"> · {{ item.current_price.amount }} EUR</span>
                            <span v-else> · sin precio</span>
                        </v-list-item-subtitle>
                    </v-list-item>
                </v-list>
            </v-card-text>
        </v-card>
    </v-container>
</template>

<script setup lang="ts">
import {onMounted, ref} from "vue"
import {getCookie} from "@/utils/cookie"

const foodId = ref("")
const unitId = ref("")
const label = ref("")
const quantity = ref("")
const price = ref("")
const message = ref("")
const packages = ref<any[]>([])

async function load() {
    const response = await fetch("/api/cuaderno/packages/", {credentials: "same-origin"})
    if (response.ok) {
        packages.value = await response.json()
    }
}

async function save() {
    message.value = ""
    const response = await fetch("/api/cuaderno/packages/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
            food: Number(foodId.value),
            unit: Number(unitId.value),
            label: label.value,
            quantity: quantity.value.replace(",", "."),
            price: price.value.trim() === "" ? null : price.value.replace(",", "."),
        }),
    })
    if (!response.ok) {
        message.value = "No se ha guardado. Revisa ingrediente, unidad y precio."
        return
    }
    message.value = "Precio guardado."
    await load()
}

onMounted(load)
</script>
