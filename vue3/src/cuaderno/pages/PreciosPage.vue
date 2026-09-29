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
                        <v-model-select v-model="food" model="Food" label="Ingrediente" search-on-load />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-model-select v-model="unit" model="Unit" label="Unidad del contenido" search-on-load />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-text-field v-model="label" label="Formato" placeholder="Garrafa 5 L" />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-text-field v-model="quantity" label="Contenido" placeholder="5" inputmode="decimal" />
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-text-field v-model="price" label="Precio EUR" placeholder="32,00" inputmode="decimal" hint="Déjalo vacío si todavía no conoces el precio." persistent-hint />
                    </v-col>
                    <v-col cols="12" md="4" class="d-flex align-center">
                        <v-btn color="primary" :loading="saving" min-height="44" @click="save">Guardar precio</v-btn>
                    </v-col>
                </v-row>
                <p v-if="message" class="mt-2" role="status">{{ message }}</p>
                <v-progress-linear v-if="loading" indeterminate aria-label="Cargando precios" />
                <p v-else-if="!packages.length" class="my-4">Todavía no hay formatos. Selecciona un ingrediente y su unidad para guardar el primero.</p>
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
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError, decimalInput} from '@/cuaderno/forms'

const food = ref<any>(null)
const unit = ref<any>(null)
const saving = ref(false)
const loading = ref(false)
const label = ref("")
const quantity = ref("")
const price = ref("")
const message = ref("")
const packages = ref<any[]>([])

async function load() {
    loading.value = true
    const response = await cuadernoFetch("/api/cuaderno/packages/")
    if (response.ok) {
        packages.value = await response.json()
    } else {
        const result = await readJson(response)
        message.value = apiError(result.status, result.data)
    }
    loading.value = false
}

async function save() {
    message.value = ""
    if (saving.value) return
    const content = decimalInput(quantity.value)
    const amount = price.value.trim() === '' ? null : decimalInput(price.value, true)
    if (!food.value?.id || !unit.value?.id || !label.value.trim() || !content || (price.value.trim() !== '' && amount === null)) {
        message.value = 'Selecciona ingrediente y unidad; indica un formato, contenido positivo y un precio válido o vacío.'
        return
    }
    saving.value = true
    const response = await cuadernoFetch("/api/cuaderno/packages/", {
        method: "POST",
        body: JSON.stringify({
            food: food.value.id,
            unit: unit.value.id,
            label: label.value.trim(),
            quantity: content,
            price: amount,
        }),
    })
    saving.value = false
    if (!response.ok) {
        const result = await readJson(response)
        message.value = apiError(result.status, result.data)
        return
    }
    message.value = "Precio guardado."
    await load()
}

onMounted(load)
</script>
