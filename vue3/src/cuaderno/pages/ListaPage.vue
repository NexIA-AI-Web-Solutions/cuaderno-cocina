<template>
    <v-container>
        <v-btn :to="{name: 'ShoppingListPage'}" variant="text" prepend-icon="fa-solid fa-arrow-left" min-height="44" class="mb-3">Lista de la compra</v-btn>
        <h1 class="text-h5 mb-3">Vista rápida de la lista</h1>
        <p class="mb-4">
            Son las mismas listas de la compra del espacio. Aquí puedes añadir y marcar alimentos rápidamente.
            Necesitas conexión para guardar los cambios.
        </p>
        <v-row>
            <v-col cols="12" md="4">
                <v-text-field v-model="listName" label="Nueva lista" />
                <v-btn color="primary" :loading="busy" min-height="44" @click="createList">Crear</v-btn>
            </v-col>
            <v-col cols="12" md="8">
                <v-select v-model="listId" :items="lists" item-title="name" item-value="id" label="Lista" :disabled="busy" @update:model-value="undo = null; loadEntries()" />
            </v-col>
            <v-col cols="12" md="4">
                <v-text-field v-model="foodName" label="Alimento" />
            </v-col>
            <v-col cols="12" md="4">
                <v-text-field v-model="amount" label="Cantidad" inputmode="decimal" />
            </v-col>
            <v-col cols="12" md="4" class="d-flex align-center">
                <v-btn color="primary" class="mr-2" :loading="busy" :disabled="!listId" min-height="44" @click="addEntry">Añadir</v-btn>
                <v-btn variant="text" :disabled="!undo || busy" min-height="44" @click="undoLast">Deshacer</v-btn>
            </v-col>
        </v-row>
        <p v-if="message" role="status">{{ message }}</p>
        <v-progress-linear v-if="loading" indeterminate aria-label="Cargando lista" />
        <p v-else-if="!entries.length" class="my-4">{{ listId ? 'La lista está vacía. Añade el primer alimento.' : 'Crea una lista para empezar.' }}</p>
        <v-list>
            <v-list-subheader>Pendiente</v-list-subheader>
            <v-list-item v-for="entry in pending" :key="entry.id">
                <template #prepend>
                    <v-checkbox-btn :model-value="false" :disabled="busy" :aria-label="`Marcar ${label(entry)}`" @update:model-value="toggle(entry, true)" />
                </template>
                <v-list-item-title>{{ label(entry) }}</v-list-item-title>
            </v-list-item>
            <v-list-subheader>Hecho</v-list-subheader>
            <v-list-item v-for="entry in done" :key="entry.id">
                <template #prepend>
                    <v-checkbox-btn :model-value="true" :disabled="busy" :aria-label="`Desmarcar ${label(entry)}`" @update:model-value="toggle(entry, false)" />
                </template>
                <v-list-item-title>{{ label(entry) }}</v-list-item-title>
            </v-list-item>
        </v-list>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from "vue"
import {cuadernoFetch, readJson} from "@/cuaderno/api"
import {apiError, decimalInput, shoppingCheckBody} from '@/cuaderno/forms'

const lists = ref<any[]>([])
const entries = ref<any[]>([])
const listId = ref<number | null>(null)
const listName = ref("")
const foodName = ref("")
const amount = ref("1")
const message = ref("")
const busy = ref(false)
const loading = ref(false)
const undo = ref<{id: number; checked: boolean} | null>(null)

const pending = computed(() => entries.value.filter((entry) => !entry.checked))
const done = computed(() => entries.value.filter((entry) => entry.checked))

function label(entry: any) {
    const name = entry.food?.name || `alimento ${entry.food?.id || ""}`
    return `${entry.amount} ${name}`
}

async function loadLists() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/shopping-list/"))
    if (!ok) {
        message.value = apiError(status, data)
        return
    }
    lists.value = Array.isArray(data) ? data : data.results || []
    if (!listId.value && lists.value.length) {
        listId.value = lists.value[0].id
        await loadEntries()
    }
}

async function createList() {
    const name = listName.value.trim()
    if (busy.value) return
    if (!name) { message.value = 'Indica un nombre para la lista.'; return }
    busy.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/shopping-list/", {
        method: "POST",
        body: JSON.stringify({name}),
    }))
    busy.value = false
    if (!ok) {
        message.value = apiError(status, data)
        return
    }
    listName.value = ""
    listId.value = data.id
    await loadLists()
    await loadEntries()
    message.value = 'Lista creada.'
}

async function loadEntries() {
    if (!listId.value) return
    const selected = listId.value
    loading.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/?shoppinglist=${selected}`))
    if (selected !== listId.value) return
    loading.value = false
    if (!ok) {
        entries.value = []
        message.value = apiError(status, data)
        return
    }
    const rows = Array.isArray(data) ? data : data.results || []
    entries.value = rows.filter((entry: any) => {
        const ids = (entry.shopping_lists || []).map((item: any) => item.id ?? item)
        return ids.includes(selected)
    })
}

async function addEntry() {
    if (busy.value) return
    if (!listId.value || !foodName.value.trim()) {
        message.value = "Elige lista y alimento."
        return
    }
    const quantity = decimalInput(amount.value)
    if (!quantity) { message.value = 'Indica una cantidad positiva, por ejemplo 1,5.'; return }
    busy.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/shopping-list-entry/", {
        method: "POST",
        body: JSON.stringify({
            food: {name: foodName.value.trim()},
            amount: quantity,
            shopping_lists: [lists.value.find(list => list.id === listId.value)],
            checked: false,
        }),
    }))
    busy.value = false
    message.value = ok ? "Línea añadida." : apiError(status, data)
    if (ok) { foodName.value = ''; await loadEntries() }
}

async function toggle(entry: any, checked: boolean) {
    if (busy.value) return
    busy.value = true
    const previous = entry.checked
    const seen = entry.updated_at
    const {ok, status, data} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/${entry.id}/?autosync=1`, {
        method: "PATCH",
        body: JSON.stringify(shoppingCheckBody(checked)),
    }))
    busy.value = false
    if (!ok) {
        message.value = apiError(status, data)
        return
    }
    if (seen && data.updated_at && seen !== data.updated_at && data.checked !== checked) {
        message.value = "Otra sesión cambió esta línea."
    }
    undo.value = {id: entry.id, checked: previous}
    await loadEntries()
}

async function undoLast() {
    if (!undo.value || busy.value) return
    const target = undo.value
    busy.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/${target.id}/?autosync=1`, {
        method: "PATCH",
        body: JSON.stringify(shoppingCheckBody(target.checked)),
    }))
    busy.value = false
    if (ok) undo.value = null
    message.value = ok ? "Cambio deshecho." : apiError(status, data)
    await loadEntries()
}

onMounted(loadLists)
</script>
