<template>


    <v-container class="pantry-page">
        <div class="d-flex flex-wrap ga-2 mb-3">
            <v-btn :to="{name: 'CuadernoAlmacenPage'}" variant="text" prepend-icon="fa-solid fa-boxes-stacked" min-height="44">
                Pedidos y movimientos
            </v-btn>
        </div>
        <v-row dense>
            <v-col>
                <v-card prepend-icon="$pantry" :title="$t('Pantry')">
                    <template #subtitle>
                        <div class="text-wrap">
                            {{ $t('PantryHelp') }}
                        </div>
                    </template>
                    <template #append>
                        <v-btn class="float-right" icon="$create" color="create" aria-label="Añadir existencia" min-height="44" @click="bookingEntry = null; bookingMode = 'add'; bookingDialog = true">
                        </v-btn>

                    </template>
                </v-card>
            </v-col>
        </v-row>
        <v-row>
            <v-col cols="12">
                <v-card>
                    <v-card-text>
                        <v-row>
                            <v-col cols="12" md="6">
                                <v-model-select model="Food" v-model="food" hide-details></v-model-select>
                            </v-col>

                            <v-col cols="12" md="6">
                                <v-model-select model="InventoryLocation" v-model="inventoryLocation" hide-details></v-model-select>
                            </v-col>
                        </v-row>


                        <v-data-table-server v-if="!smAndDown"
                            return-object
                            @update:options="loadItems"
                            :items="items"
                            :items-length="itemCount"
                            :loading="tableLoading"
                            :headers="tableHeaders"
                            :page="page"
                            :items-per-page="pageSize"
                            disable-sort
                        >
                            <template #item.code="{item}">
                                <v-chip size="small" label color="warning" class="me-2" prepend-icon="fa-solid fa-barcode">{{ item.code }}</v-chip>
                            </template>
                            <template #item.food="{item}">
                                {{ ingredientToString({food: item.food, unit: item.unit, amount: item.amount}) }}
                            </template>
                            <template #item.expires="{item}">
                                <template v-if="item.expires ">
                                    <v-chip size="small" label :color="DateTime.fromJSDate(item.expires) < DateTime.now() ? 'error' : 'success'">
                                        {{ DateTime.fromJSDate(item.expires).toLocaleString(DateTime.DATE_MED) }}
                                    </v-chip>
                                </template>
                            </template>
                            <template #item.inventoryLocation="{ item }">
                                {{ item.inventoryLocation.name }} <i class="fa-solid fa-snowflake" v-if="item.inventoryLocation.isFreezer"></i>
                                <span class="text-body-2 text-disabled">
                                    <br/>
                                {{ item.subLocation }}
                                </span>
                            </template>
                            <template #item.action="{item}">
                                <v-btn-group divided border density="comfortable">
                                    <v-btn icon="fa-solid fa-clock-rotate-left" min-height="44" min-width="44" :aria-label="'Ver historial de ' + item.food.name" @click="entryLogDialog = true; entryLogEntry = item"></v-btn>
                                    <v-btn icon="fa-solid fa-minus" min-height="44" min-width="44" :aria-label="'Retirar cantidad de ' + item.food.name" @click="bookingDialog = true; bookingMode = 'remove'; bookingEntry = item"></v-btn>
                                    <v-btn icon="fa-solid fa-arrow-right" min-height="44" min-width="44" :aria-label="'Mover ' + item.food.name" @click="bookingDialog = true; bookingMode = 'move'; bookingEntry = item"></v-btn>
                                </v-btn-group>

                            </template>
                        </v-data-table-server>

                        <v-row v-else class="pantry-cards" dense>
                            <v-col v-for="item in items" :key="item.id" cols="12"><v-card variant="outlined"><v-card-title class="text-wrap">{{ ingredientToString({food: item.food, unit: item.unit, amount: item.amount}) }}</v-card-title><v-card-text><p>{{ item.inventoryLocation.name }}<span v-if="item.subLocation"> · {{ item.subLocation }}</span></p><p v-if="item.code">Código: {{ item.code }}</p><p v-if="item.expires">Caduca: {{ DateTime.fromJSDate(item.expires).toLocaleString(DateTime.DATE_MED) }}</p></v-card-text><v-card-actions class="flex-wrap ga-2"><v-btn min-height="44" :aria-label="'Ver historial de ' + item.food.name" @click="entryLogDialog = true; entryLogEntry = item">Historial</v-btn><v-btn min-height="44" :aria-label="'Retirar cantidad de ' + item.food.name" @click="bookingMode = 'remove'; bookingEntry = item; bookingDialog = true">Retirar</v-btn><v-btn min-height="44" :aria-label="'Mover ' + item.food.name" @click="bookingMode = 'move'; bookingEntry = item; bookingDialog = true">Mover</v-btn></v-card-actions></v-card></v-col>
                            <v-col v-if="tableLoading" cols="12"><v-progress-linear indeterminate aria-label="Cargando despensa" /></v-col><v-col v-if="!tableLoading && !items.length" cols="12">No hay existencias con estos filtros.</v-col>
                            <v-col v-if="pageSize > 0 && itemCount > pageSize" cols="12" class="d-flex flex-wrap ga-2 align-center"><v-btn :disabled="tableLoading || page <= 1" @click="loadItems({page: page - 1, itemsPerPage: pageSize})">Anterior</v-btn><span>{{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize,itemCount) }} de {{ itemCount }}</span><v-btn :disabled="tableLoading || page * pageSize >= itemCount" @click="loadItems({page: page + 1, itemsPerPage: pageSize})">Siguiente</v-btn></v-col>
                        </v-row>
                        <inventory-entry-log-dialog v-model="entryLogDialog" :inventory-entry="entryLogEntry ?? undefined"></inventory-entry-log-dialog>

                        <pantry-booking-dialog v-model="bookingDialog" :bookingMode="bookingMode" :inventoryEntryId="bookingEntry?.id"
                                               @update="loadItems({page: page, itemsPerPage: pageSize})"></pantry-booking-dialog>
                    </v-card-text>
                </v-card>
            </v-col>
        </v-row>
    </v-container>

</template>

<script setup lang="ts">

import {useDisplay} from "vuetify";
import {DateTime} from "luxon";
import {ingredientToString} from "@/utils/model_utils.ts";
import {ApiApi, ApiInventoryEntryListRequest, Food, InventoryEntry, InventoryLocation} from "@/openapi";
import {onBeforeUnmount, onMounted, ref, watch} from "vue";
import {useI18n} from "vue-i18n";
import InventoryEntryLogDialog from "@/components/dialogs/InventoryEntryLogDialog.vue";
import {VDataTableUpdateOptions} from "@/vuetify.ts";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore.ts";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";
import PantryBookingDialog from "@/components/dialogs/PantryBookingDialog.vue";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import VModelSelect from "@/components/inputs/VModelSelect.vue";

const {t} = useI18n()
const {smAndDown} = useDisplay()
let requestGeneration = 0
onMounted(() => loadItems({page: page.value, itemsPerPage: pageSize.value}))
onBeforeUnmount(() => {requestGeneration++})

// table
const tableLoading = ref(false)

const items = ref([] as InventoryEntry[])
const itemCount = ref(0)
const page = ref(1)
const pageSize = ref(useUserPreferenceStore().deviceSettings.general_tableItemsPerPage)

const tableHeaders = [
    {title: t('Code'), key: 'code'},
    {title: t('Food'), key: 'food'},
    {title: t('Expires'), key: 'expires',},
    {title: t('InventoryLocation'), key: 'inventoryLocation',},
    {title: t('Actions'), key: 'action', align: 'end' as const},
]

const entryLogDialog = ref(false)
const entryLogEntry = ref<InventoryEntry | null>(null)

const bookingDialog = ref(false)
const bookingMode = ref('move')
const bookingEntry = ref<InventoryEntry | null>(null)

const food = ref<Food | undefined>(undefined)
const inventoryLocation = ref<InventoryLocation | undefined>(undefined)

watch(food, () => {
    loadItems({page: 1, itemsPerPage: pageSize.value})
})

watch(inventoryLocation, () => {
    loadItems({page: 1, itemsPerPage: pageSize.value})
})

/**
 * load inventory data based on current props
 */
function loadItems(options: VDataTableUpdateOptions) {
    const generation = ++requestGeneration
    let api = new ApiApi()

    let parameters = {} as ApiInventoryEntryListRequest

    if (food.value) {
        parameters.foodId = food.value.id!
    }
    if (inventoryLocation.value) {
        parameters.inventoryLocationId = inventoryLocation.value.id!
    }

    tableLoading.value = true

    page.value = options.page
    pageSize.value = options.itemsPerPage

    parameters.page = options.page
    parameters.pageSize = options.itemsPerPage

    return api.apiInventoryEntryList(parameters).then(r => {
        if (generation !== requestGeneration) return
        items.value = r.results
        itemCount.value = r.count
    }).catch(err => {
        if (generation !== requestGeneration) return
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        if (generation !== requestGeneration) return
        tableLoading.value = false
    })

}

</script>

<style scoped>.pantry-page :deep(.v-card-title){white-space:normal;overflow-wrap:anywhere}.pantry-page :deep(.v-card-actions){flex-wrap:wrap}.pantry-cards .v-card{min-width:0;overflow-wrap:anywhere}</style>
