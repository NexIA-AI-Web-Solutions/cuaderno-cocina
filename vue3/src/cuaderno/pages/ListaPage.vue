<template>
    <v-container>
        <h1 class="text-h5 mb-3">Lista de la compra</h1>
        <p class="mb-4">
            Usa la lista nativa del espacio. No hay cola sin conexión: si la red falla, la marca no se guarda.
        </p>
        <v-row>
            <v-col cols="12" md="4">
                <v-text-field v-model="listName" label="Nueva lista" />
                <v-btn color="primary" @click="createList">Crear</v-btn>
            </v-col>
            <v-col cols="12" md="8">
                <v-select v-model="listId" :items="lists" item-title="name" item-value="id" label="Lista" @update:model-value="loadEntries" />
            </v-col>
            <v-col cols="12" md="4">
                <v-text-field v-model="foodName" label="Alimento" />
            </v-col>
            <v-col cols="12" md="4">
                <v-text-field v-model="amount" label="Cantidad" />
            </v-col>
            <v-col cols="12" md="4" class="d-flex align-center">
                <v-btn color="primary" class="mr-2" @click="addEntry">Añadir</v-btn>
                <v-btn variant="text" :disabled="!undo" @click="undoLast">Deshacer</v-btn>
            </v-col>
        </v-row>
        <p v-if="message" role="status">{{ message }}</p>
        <v-list>
            <v-list-subheader>Pendiente</v-list-subheader>
            <v-list-item v-for="entry in pending" :key="entry.id">
                <template #prepend>
                    <v-checkbox-btn :model-value="false" :aria-label="`Marcar ${label(entry)}`" @update:model-value="toggle(entry, true)" />
                </template>
                <v-list-item-title>{{ label(entry) }}</v-list-item-title>
            </v-list-item>
            <v-list-subheader>Hecho</v-list-subheader>
            <v-list-item v-for="entry in done" :key="entry.id">
                <template #prepend>
                    <v-checkbox-btn :model-value="true" :aria-label="`Desmarcar ${label(entry)}`" @update:model-value="toggle(entry, false)" />
                </template>
                <v-list-item-title>{{ label(entry) }}</v-list-item-title>
            </v-list-item>
        </v-list>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from "vue"
import {cuadernoFetch, readJson} from "@/cuaderno/api"

const lists = ref<any[]>([])
const entries = ref<any[]>([])
const listId = ref<number | null>(null)
const listName = ref("")
const foodName = ref("")
const amount = ref("1")
const message = ref("")
const undo = ref<{id: number; checked: boolean} | null>(null)

const pending = computed(() => entries.value.filter((entry) => !entry.checked))
const done = computed(() => entries.value.filter((entry) => entry.checked))

function label(entry: any) {
    const name = entry.food?.name || `alimento ${entry.food?.id || ""}`
    return `${entry.amount} ${name}`
}

async function loadLists() {
    const {ok, data} = await readJson(await cuadernoFetch("/api/shopping-list/"))
    if (!ok) {
        message.value = "No se ha podido leer la lista nativa."
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
    if (!name) return
    const {ok, data} = await readJson(await cuadernoFetch("/api/shopping-list/", {
        method: "POST",
        body: JSON.stringify({name}),
    }))
    if (!ok) {
        message.value = "No se ha creado la lista."
        return
    }
    listName.value = ""
    listId.value = data.id
    await loadLists()
    await loadEntries()
}

async function loadEntries() {
    if (!listId.value) return
    const {ok, data} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/?shoppinglist=${listId.value}`))
    if (!ok) {
        message.value = "No se han podido leer las líneas."
        return
    }
    const rows = Array.isArray(data) ? data : data.results || []
    entries.value = rows.filter((entry: any) => {
        const ids = (entry.shopping_lists || []).map((item: any) => item.id ?? item)
        return ids.length === 0 || ids.includes(listId.value)
    })
}

async function addEntry() {
    if (!listId.value || !foodName.value.trim()) {
        message.value = "Elige lista y alimento."
        return
    }
    const {ok} = await readJson(await cuadernoFetch("/api/shopping-list-entry/", {
        method: "POST",
        body: JSON.stringify({
            food: {name: foodName.value.trim()},
            amount: amount.value.replace(",", "."),
            shopping_lists: [{id: listId.value}],
            checked: false,
        }),
    }))
    message.value = ok ? "Línea añadida." : "No se ha añadido la línea."
    if (ok) await loadEntries()
}

async function toggle(entry: any, checked: boolean) {
    const previous = entry.checked
    const seen = entry.updated_at
    const {ok, data} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/${entry.id}/`, {
        method: "PATCH",
        body: JSON.stringify({checked}),
    }))
    if (!ok) {
        message.value = "Sin red o sin permiso: la marca no se ha guardado."
        return
    }
    if (seen && data.updated_at && seen !== data.updated_at && data.checked !== checked) {
        message.value = "Otra sesión cambió esta línea."
    }
    undo.value = {id: entry.id, checked: previous}
    await loadEntries()
}

async function undoLast() {
    if (!undo.value) return
    const target = undo.value
    undo.value = null
    const {ok} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/${target.id}/`, {
        method: "PATCH",
        body: JSON.stringify({checked: target.checked}),
    }))
    message.value = ok ? "Cambio deshecho." : "No se ha podido deshacer."
    await loadEntries()
}

onMounted(loadLists)
</script>
