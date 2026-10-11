<template>
    <v-container>
        <v-btn :to="{name: 'ShoppingListPage'}" variant="text" prepend-icon="fa-solid fa-arrow-left" min-height="44" class="mb-3">Lista de la compra</v-btn>
        <h1 class="text-h5 mb-3">Vista rápida de la lista</h1>
        <v-alert v-if="!canOperate" type="info" variant="tonal" class="mb-4">Modo Consulta: puedes revisar la lista, pero no modificarla.</v-alert>
        <p class="mb-4">
            Son las mismas listas de la compra del espacio. Aquí puedes añadir y marcar alimentos rápidamente.
            Necesitas conexión para guardar los cambios.
        </p>
        <v-btn variant="text" min-height="44" class="mb-3" :loading="loading" :disabled="busy || loading" @click="refreshList">Actualizar lista</v-btn>
        <v-row>
            <v-col cols="12" md="4">
                <v-text-field v-model="listName" label="Nueva lista" :disabled="!canOperate || busy" @keydown.enter.prevent="createList" />
                <v-btn color="primary" :loading="busy" :disabled="!canOperate" min-height="44" @click="createList">Crear</v-btn>
            </v-col>
            <v-col cols="12" md="8">
                <v-select v-model="listId" :items="lists" item-title="name" item-value="id" label="Lista" clearable :disabled="busy" @update:model-value="undo = null; loadEntries()" />
            </v-col>
            <v-col cols="12" md="4">
                <v-text-field v-model="foodName" label="Alimento" :disabled="!canOperate || busy || !listId || loading" @keydown.enter.prevent="addEntry" />
            </v-col>
            <v-col cols="12" md="4">
                <v-text-field v-model="amount" label="Cantidad" inputmode="decimal" :disabled="!canOperate || busy || !listId || loading" @keydown.enter.prevent="addEntry" />
            </v-col>
            <v-col cols="12" md="4" class="d-flex align-center">
                <v-btn color="primary" class="mr-2" :loading="busy" :disabled="!canOperate || !listId || loading" min-height="44" @click="addEntry">Añadir</v-btn>
                <v-btn variant="text" :disabled="!canOperate || !undo || busy || loading || loadFailed" min-height="44" @click="undoLast">Deshacer</v-btn>
            </v-col>
        </v-row>
        <p v-if="message" role="status" aria-live="polite">{{ message }}</p>
        <v-progress-linear v-if="loading" indeterminate aria-label="Cargando lista" />
        <p v-else-if="!entries.length && !loadFailed" class="my-4">{{ listId ? 'La lista está vacía. Añade el primer alimento.' : 'Crea una lista para empezar.' }}</p>
        <v-list class="cuaderno-quick-list">
            <v-list-subheader><h2 class="text-h6">Pendiente</h2><v-chip class="ms-3" size="small" color="secondary" variant="tonal">{{ pending.length }}</v-chip></v-list-subheader>
            <v-list-item v-for="entry in pending" :key="entry.id">
                <template #prepend>
                    <v-checkbox-btn :model-value="false" :disabled="!canOperate || busy || loading || loadFailed" :aria-label="`Marcar ${label(entry)}`" @update:model-value="toggle(entry, true)" />
                </template>
                <v-list-item-title>{{ label(entry) }}</v-list-item-title>
                <v-list-item-subtitle>{{ sourceLabel(entry) }} · {{ syncingEntry === entry.id ? 'Guardando…' : 'Sincronizado' }}</v-list-item-subtitle>
            </v-list-item>
            <v-btn v-if="done.length" variant="text" min-height="44" :aria-expanded="showDone" @click="showDone = !showDone">{{ showDone ? 'Ocultar completados' : `Mostrar completados (${done.length})` }}</v-btn>
            <v-list-subheader v-if="showDone || !done.length"><h2 class="text-h6">Hecho</h2><v-chip class="ms-3" size="small" variant="tonal">{{ done.length }}</v-chip></v-list-subheader>
            <v-list-item v-for="entry in visibleDone" :key="entry.id" class="cuaderno-completed-entry">
                <template #prepend>
                    <v-checkbox-btn :model-value="true" :disabled="!canOperate || busy || loading || loadFailed" :aria-label="`Desmarcar ${label(entry)}`" @update:model-value="toggle(entry, false)" />
                </template>
                <v-list-item-title>{{ label(entry) }}</v-list-item-title>
                <v-list-item-subtitle>{{ sourceLabel(entry) }} · {{ syncingEntry === entry.id ? 'Guardando…' : 'Sincronizado' }}</v-list-item-subtitle>
            </v-list-item>
        </v-list>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from "vue"
import {cuadernoFetch, readJson} from "@/cuaderno/api"
import {apiError, decimalInput, shoppingCheckBody} from '@/cuaderno/forms'
import {
    ifMatchRevision,
    shoppingEntries,
    shoppingEntryResponse,
    shoppingLists,
    shoppingSourceLabel,
    type ShoppingEntry,
    type ShoppingListSummary,
} from '@/cuaderno/shoppingUi'
import {editionOperationalRole} from '@/cuaderno/operationalRoleUi'

const lists = ref<ShoppingListSummary[]>([])
const entries = ref<ShoppingEntry[]>([])
const listId = ref<number | null>(null)
const listName = ref("")
const foodName = ref("")
const amount = ref("1")
const message = ref("")
const busy = ref(false)
const loading = ref(false)
const loadFailed = ref(false)
let entriesGeneration = 0
let loadedListId: number | null = null
const showDone = ref(true)
const undo = ref<{id: number; checked: boolean; revision: string} | null>(null)
const syncingEntry = ref<number | null>(null)
const canOperate = ref(false)

const pending = computed(() => entries.value.filter((entry) => !entry.checked))
const done = computed(() => entries.value.filter((entry) => entry.checked))

const visibleDone = computed(() => showDone.value ? done.value : [])

async function refreshList() {
    if (busy.value || loading.value) return
    await loadLists()
    if (listId.value) await loadEntries()
}

function label(entry: ShoppingEntry) {
    const unit = entry.unit?.name ? ` ${entry.unit.name}` : ''
    return `${entry.amount}${unit} · ${entry.food.name}`
}
function sourceLabel(entry: ShoppingEntry) { return shoppingSourceLabel(entry.list_recipe_data) }

async function loadLists() {
    const {ok, status, data} = await readJson(await cuadernoFetch("/api/shopping-list/"))
    if (!ok) {
        message.value = apiError(status, data)
        return
    }
    const parsed = shoppingLists(data)
    if (parsed === null) { message.value = 'El servidor devolvió listas incompletas. Conservamos la selección actual.'; return }
    lists.value = parsed
    const firstList = lists.value[0]
    if (!listId.value && firstList) {
        listId.value = firstList.id
        await loadEntries()
    }
}

async function loadRole() {
    const {ok, data} = await readJson(await cuadernoFetch('/api/cuaderno/edition/'))
    canOperate.value = ok && editionOperationalRole(data)?.can_operate_cuaderno === true
}

async function createList() {
    if (!canOperate.value) return
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
    const created = shoppingLists([data])
    if (created === null || created.length !== 1) {
        message.value = 'El servidor no confirmó la lista creada. Actualiza antes de continuar.'
        return
    }
    listName.value = ""
    listId.value = created[0]!.id
    await loadLists()
    await loadEntries()
    message.value = 'Lista creada.'
}

async function loadEntries() {
    const generation = ++entriesGeneration
    if (!listId.value) { entries.value = []; loadedListId = null; undo.value = null; loading.value = false; loadFailed.value = false; return }
    loadFailed.value = false
    const selected = listId.value
    if (selected !== loadedListId) { entries.value = []; undo.value = null }
    loading.value = true
    const {ok, status, data} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/?shoppinglist=${selected}`))
    if (generation !== entriesGeneration || selected !== listId.value) return
    loading.value = false
    if (!ok) {
        loadFailed.value = true
        message.value = apiError(status, data)
        return
    }
    const rows = shoppingEntries(data)
    if (rows === null) {
        loadFailed.value = true
        message.value = 'El servidor devolvió líneas incompletas. Conservamos la lista anterior.'
        return
    }
    loadedListId = selected
    entries.value = rows.filter(entry => {
        const ids = entry.shopping_lists.map(item => typeof item === 'number' ? item : item.id)
        return ids.includes(selected)
    })
}

async function addEntry() {
    if (!canOperate.value) return
    if (busy.value || loading.value) return
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
    if (!ok) { message.value = apiError(status, data); return }
    const saved = shoppingEntryResponse(data, Number(data?.id), false)
    if (saved === null) {
        message.value = 'El servidor no confirmó la línea creada. Conservamos el formulario.'
        return
    }
    message.value = "Línea añadida."
    foodName.value = ''
    await loadEntries()
}

async function toggle(entry: ShoppingEntry, checked: boolean) {
    if (!canOperate.value) return
    if (busy.value || loading.value || loadFailed.value) return
    const revision = ifMatchRevision(entry.updated_at)
    if (revision === null) {
        message.value = 'Esta línea no tiene una revisión válida. Actualiza la lista antes de cambiarla.'
        return
    }
    busy.value = true
    syncingEntry.value = entry.id
    const previous = entry.checked
    const {ok, status, data} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/${entry.id}/`, {
        method: "PATCH",
        headers: {'If-Match': revision},
        body: JSON.stringify(shoppingCheckBody(checked)),
    }))
    busy.value = false
    syncingEntry.value = null
    if (!ok) {
        message.value = apiError(status, data)
        if (status === 409) await loadEntries()
        return
    }
    const saved = shoppingEntryResponse(data, entry.id, checked)
    if (saved === null) {
        message.value = 'El servidor no confirmó el cambio con una revisión válida. Actualiza la lista.'
        return
    }
    undo.value = {id: entry.id, checked: previous, revision: saved.updated_at}
    await loadEntries()
}

async function undoLast() {
    if (!canOperate.value) return
    if (!undo.value || busy.value || loading.value || loadFailed.value) return
    const target = undo.value
    const revision = ifMatchRevision(target.revision)
    if (revision === null) { message.value = 'No se puede deshacer sin una revisión válida. Actualiza la lista.'; return }
    busy.value = true
    syncingEntry.value = target.id
    const {ok, status, data} = await readJson(await cuadernoFetch(`/api/shopping-list-entry/${target.id}/`, {
        method: "PATCH",
        headers: {'If-Match': revision},
        body: JSON.stringify(shoppingCheckBody(target.checked)),
    }))
    busy.value = false
    syncingEntry.value = null
    const saved = ok ? shoppingEntryResponse(data, target.id, target.checked) : null
    if (saved) undo.value = null
    message.value = saved ? "Cambio deshecho." : ok
        ? 'El servidor no confirmó el cambio deshecho. Actualiza la lista.'
        : apiError(status, data)
    await loadEntries()
}

onMounted(() => Promise.all([loadRole(), loadLists()]))
</script>

<style scoped>
@media screen {
    .cuaderno-quick-list { border-radius: 16px; padding: 12px; border: 1px solid rgba(var(--v-theme-on-surface), .14); }
    .cuaderno-quick-list :deep(.v-list-subheader) { min-height: 56px; margin-top: 8px; }
    .cuaderno-quick-list :deep(.v-list-item) { min-height: 68px; margin-block: 8px; border-radius: 10px; background: rgba(var(--v-theme-secondary), .06); }
    .cuaderno-quick-list :deep(.v-list-item-title), .cuaderno-quick-list :deep(.v-list-item-subtitle) { white-space: normal; overflow-wrap: anywhere; }
    .cuaderno-completed-entry :deep(.v-list-item-title) { text-decoration: line-through; }
}
</style>
