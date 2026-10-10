<template>
    <v-tabs v-model="currentTab" class="cuaderno-shopping-tabs" show-arrows v-if="!selectEnabled && props.mealPlanId == undefined">
        <v-tab value="shopping"><i class="fas fa-fw"
                                   :class="{'fa-circle-notch fa-spin':useShoppingStore().currentlyUpdating, 'fa-shopping-cart ': !useShoppingStore().currentlyUpdating}"></i> <span
            class="ms-1">{{ $t('Shopping_list') }} ({{ useShoppingStore().totalFoods }})</span></v-tab>
        <v-tab value="recipes"><i class="fas fa-book fa-fw"></i> <span class="ms-1">{{
                $t('Recipes')
            }} ({{ useShoppingStore().getAssociatedRecipes().length }})</span></v-tab>
        <v-tab value="selected_supermarket" v-if="selectedSupermarket">
            <i class="fa-solid fa-store fa-fw"></i> <span class="d-none d-md-block ms-1">{{ selectedSupermarket.name }}</span>
        </v-tab>

        <v-menu :close-on-content-click="false">
            <template v-slot:activator="{ props }">
                <v-btn
                    class="me-4 float-right"
                    height="100%"
                    rounded="0"
                    variant="plain"
                    :aria-label="$t('Settings')"
                    :title="$t('Settings')"
                    v-bind="props"
                >
                    <i class="fa-solid fa-sliders"></i>
                </v-btn>
            </template>

            <v-list density="compact">
                <v-list-item>
                    <v-select hide-details :items="groupingOptionsItems" v-model="useUserPreferenceStore().deviceSettings.shopping_selected_grouping"
                              :label="$t('GroupBy')">
                    </v-select>
                </v-list-item>
                <v-list-item v-if="canManageShopping && useUserPreferenceStore().deviceSettings.shopping_selected_grouping == ShoppingGroupingOptions.CATEGORY">
                    <v-switch color="primary" hide-details :label="$t('SupermarketCategoriesOnly')"
                              v-model="useUserPreferenceStore().deviceSettings.shopping_show_selected_supermarket_only"></v-switch>
                </v-list-item>
                <v-list-item v-if="canManageShopping">
                    <v-model-select model="Supermarket" v-model="useUserPreferenceStore().deviceSettings.shopping_selected_supermarket"></v-model-select>
                </v-list-item>

                <v-list-item>
                    <v-switch color="primary" hide-details :label="$t('ShowDelayed')" v-model="useUserPreferenceStore().deviceSettings.shopping_show_delayed_entries"></v-switch>
                </v-list-item>
                <v-list-item>
                    <v-switch color="primary" hide-details :label="$t('ShowRecentlyCompleted')"
                              v-model="useUserPreferenceStore().deviceSettings.shopping_show_checked_entries"></v-switch>
                </v-list-item>
                <v-divider></v-divider>
                <v-list-item @click="exportDialog = true" link prepend-icon="fa-solid fa-download">
                    {{ $t('Export') }}
                </v-list-item>
                <v-list-subheader>{{ $t('Information') }}</v-list-subheader>
                <v-list-item>
                    <v-switch color="primary" hide-details :label="$t('Recipe')" v-model="useUserPreferenceStore().deviceSettings.shopping_item_info_recipe"></v-switch>
                </v-list-item>
                <v-list-item>
                    <v-switch color="primary" hide-details :label="$t('Meal_Plan')" v-model="useUserPreferenceStore().deviceSettings.shopping_item_info_mealplan"></v-switch>
                </v-list-item>
                <v-list-item>
                    <v-switch color="primary" hide-details :label="$t('CreatedBy')" v-model="useUserPreferenceStore().deviceSettings.shopping_item_info_created_by"></v-switch>
                </v-list-item>
                <v-list-item>
                    <v-switch color="primary" hide-details label="Entrada con autocompletado" v-model="useUserPreferenceStore().deviceSettings.shopping_input_autocomplete"></v-switch>
                </v-list-item>
                <v-list-item v-if="useUserPreferenceStore().serverSettings.debug">
                    <v-switch color="primary" hide-details label="Mostrar información de diagnóstico" v-model="useUserPreferenceStore().deviceSettings.shopping_show_debug"></v-switch>
                </v-list-item>

            </v-list>
        </v-menu>

        <!--        <v-btn height="100%" rounded="0" variant="plain">-->
        <!--            <i class="fa-solid fa-download"></i>-->
        <!--            <shopping-export-dialog></shopping-export-dialog>-->
        <!--        </v-btn>-->

        <!--        <v-btn height="100%" rounded="0" variant="plain" @click="useShoppingStore().undoChange()">-->
        <!--            <i class="fa-solid fa-arrow-rotate-left"></i>-->
        <!--        </v-btn>-->

    </v-tabs>
    <v-banner class="pt-0 pb-0 bg-info" v-if="selectEnabled">
        <template #prepend>
            <v-btn icon="$close" variant="plain" @click="selectEnabled = false; selectedLines = [];" lines="1"></v-btn>
        </template>

        <shopping-list-select-chip
            v-model="selectedShoppingLists"
            :shopping-lists="useShoppingStore().shoppingLists"
            :show-update="canManageShopping"
            hide-edit
            hide-create
            @refresh="useShoppingStore().loadShoppingLists()"
            @update="batchUpdateShoppingLists"
        ></shopping-list-select-chip>

        <category-select-chip v-if="canManageShopping"
            :categories="useShoppingStore().supermarketCategories"
            @update="batchUpdateCategories"
        ></category-select-chip>
    </v-banner>

    <shopping-export-dialog v-model="exportDialog" activator="model"></shopping-export-dialog>

    <v-window v-model="currentTab">
        <v-window-item value="shopping">
            <v-container :class="{'pa-1': props.mealPlanId != undefined}">
                <!--                <v-row class="pa-0" dense>-->
                <!--                    <v-col class="pa-0">-->
                <!--                        <v-chip-group v-model="useUserPreferenceStore().deviceSettings.shopping_selected_supermarket" v-if="supermarkets.length > 0">-->
                <!--                            <v-chip v-for="s in supermarkets" :value="s" :key="s.id" label density="compact" variant="outlined" color="primary">{{ s.name }}</v-chip>-->
                <!--                        </v-chip-group>-->
                <!--                    </v-col>-->
                <!--                </v-row>-->

                <v-row class="pa-0" dense>
                    <v-col class="pa-0">
                        <v-chip-group class="cuaderno-shopping-toolbar">
                            <!-- enable selection -->
                            <v-btn label size="small" variant="outlined" @click="selectEnabled = true;  selectedLines= []" v-if="!selectEnabled">
                                <v-icon icon="fa-solid fa-list-check"></v-icon>
                            </v-btn>

                            <!-- select all/none -->
                            <v-btn label size="small" variant="outlined" @click="selectAll(); " v-if="!isAllSelected() && selectEnabled">
                                <v-icon icon="fa-solid fa-square-check"></v-icon>
                            </v-btn>
                            <v-btn label size="small" variant="outlined" @click="selectedLines = []; " v-if="isAllSelected() && selectEnabled">
                                <v-icon icon="fa-regular fa-square"></v-icon>
                            </v-btn>

                            <!-- undo -->
                            <v-btn v-if="canManageShopping" label size="small" class="ms-1" variant="outlined" @click="undoShoppingChange()" :disabled="useShoppingStore().undoStack.length == 0">
                                <v-icon icon="fa-solid fa-rotate-left"></v-icon>
                            </v-btn>

                            <v-chip label size="small" variant="outlined" class="ms-1 me-0 mt-0 mb-0 h-100" style="max-width: 50%;" :prepend-icon="TSupermarket.icon"
                                    append-icon="fa-solid fa-caret-down" v-if="canManageShopping && props.mealPlanId == undefined">
                            <span v-if="selectedSupermarket">
                                {{ selectedSupermarket.name }}
                            </span>
                                <span v-else>{{ $t('Supermarket') }}</span>

                                <v-menu activator="parent">
                                    <v-list density="compact">
                                        <v-list-item
                                            @click="useUserPreferenceStore().deviceSettings.shopping_selected_supermarket = null; useShoppingStore().updateEntriesStructure()">
                                            {{ $t('SelectNone') }}
                                        </v-list-item>
                                        <v-list-item v-for="s in supermarkets" :key="s.id" @click="useUserPreferenceStore().deviceSettings.shopping_selected_supermarket = s">
                                            {{ s.name }}
                                        </v-list-item>
                                        <v-list-item prepend-icon="$create" :to="{name: 'ModelEditPage', params: {model: 'Supermarket'}}">
                                            {{ $t('Create') }}
                                        </v-list-item>
                                    </v-list>
                                </v-menu>
                            </v-chip>

                            <shopping-list-select-chip
                                class="ms-1 mt-0 mb-0 h-100"
                                v-model:ids="useUserPreferenceStore().deviceSettings.shopping_selected_shopping_lists"
                                :shopping-lists="useShoppingStore().shoppingLists"
                                :hide-edit="!canManageShopping"
                                :hide-create="!canManageShopping"
                                @refresh="useShoppingStore().loadShoppingLists()"
                            ></shopping-list-select-chip>
                        </v-chip-group>

                    </v-col>
                </v-row>

                <v-row class="mt-0">
                    <v-col>
                        <v-alert v-if="useShoppingStore().hasFailedItems()" color="warning" class="mb-2">
                            <template #prepend>
                                <v-icon icon="fa-solid fa-link-slash"></v-icon>
                            </template>
                            {{ $t('ShoppingBackgroundSyncWarning') }}
                            <template #append>
                                {{ useShoppingStore().itemCheckSyncQueue.length }}
                            </template>
                        </v-alert>

                        <shopping-list-entry-input :meal-plan-id="props.mealPlanId"></shopping-list-entry-input>
                        <v-card v-if="props.mealPlanId === undefined && useShoppingStore().initialized && !useShoppingStore().currentlyUpdating && !shoppingListItems.length"
                                class="cuaderno-shopping-empty mt-4" variant="outlined">
                            <v-card-title>{{ $t('ShoppingEmptyTitle') }}</v-card-title>
                            <v-card-text>{{ $t('ShoppingEmptyHelp') }}</v-card-text>
                            <v-card-actions>
                                <v-btn :to="{name: 'CuadernoListaPage'}" min-height="44" prepend-icon="$shopping">{{ $t('ShoppingQuickView') }}</v-btn>
                            </v-card-actions>
                        </v-card>

                        <v-list class="mt-3" density="compact" v-if="!useShoppingStore().initialized">
                            <v-skeleton-loader type="list-item"></v-skeleton-loader>
                            <v-skeleton-loader type="list-item"></v-skeleton-loader>
                            <v-skeleton-loader type="list-item"></v-skeleton-loader>
                            <v-skeleton-loader type="list-item"></v-skeleton-loader>
                        </v-list>
                        <v-list class="mt-3" density="compact" v-model:selected="selectedLines" select-strategy="leaf" v-else>
                            <template v-for="category in shoppingListItems" :key="category.name">


                                <v-list-subheader :style="subheaderStyle" v-if="category.name === useShoppingStore().UNDEFINED_CATEGORY">

                                    <v-btn color="secondary" variant="text" icon="fa-regular fa-square" @click="selectAll(category)"
                                           v-if="selectEnabled && !isAllSelected(category)"></v-btn>
                                    <v-btn color="secondary" variant="text" icon="fa-solid fa-square-check" @click="deselectCategory(category)"
                                           v-if="selectEnabled && isAllSelected(category)"></v-btn>
                                    <i>{{ $t('NoCategory') }}</i>

                                </v-list-subheader>

                                <v-list-subheader :style="subheaderStyle" v-else>
                                    <v-btn color="secondary" variant="text" icon="fa-regular fa-square" @click="selectAll(category)"
                                           v-if="selectEnabled && !isAllSelected(category)"></v-btn>
                                    <v-btn color="secondary" variant="text" icon="fa-solid fa-square-check" @click="deselectCategory(category)"
                                           v-if="selectEnabled && isAllSelected(category)"></v-btn>
                                    {{ category.name }}
                                </v-list-subheader>
                                <v-divider></v-divider>

                                <template v-for="[i, value] in category.foods" :key="value.food.id">
                                    <shopping-line-item :shopping-list-food="value" :select-enabled="selectEnabled"></shopping-line-item>
                                </template>

                            </template>
                        </v-list>

                        <!-- TODO remove once append to body for model select is working properly -->
                        <v-spacer style="margin-top: 120px;"></v-spacer>
                    </v-col>
                </v-row>

                <!-- DEBUG views -->
                <v-row v-if="useUserPreferenceStore().deviceSettings.shopping_show_debug">
                    <v-col cols="12" md="4">
                        <v-card>
                            <v-card-title>Diagnóstico de sincronización automática</v-card-title>
                            <v-btn @click="useShoppingStore().autoSync()">Sincronizar ahora</v-btn>
                            <v-card-text>
                                <v-list>
                                    <v-list-item>Actualizando: {{ useShoppingStore().currentlyUpdating }}</v-list-item>
                                    <v-list-item>Ventana activa: {{ useShoppingStore().autoSyncHasFocus }}</v-list-item>
                                    <v-list-item>Identificador del temporizador: {{ useShoppingStore().autoSyncTimeoutId }}</v-list-item>
                                    <v-list-item>Última sincronización: {{ useShoppingStore().autoSyncLastTimestamp }}</v-list-item>
                                </v-list>
                            </v-card-text>
                        </v-card>
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-card>
                            <v-card-title>Cola de sincronización</v-card-title>
                            <v-card-text>
                                Elementos: {{ useShoppingStore().itemCheckSyncQueue.length }} <br/>
                                Hay elementos fallidos: {{ useShoppingStore().hasFailedItems() }}
                                <v-list>
                                     <v-list-item v-for="i in useShoppingStore().itemCheckSyncQueue" :key="`${i.checked}:${i.ids.join(',')}`">{{ i }}</v-list-item>
                                </v-list>
                            </v-card-text>
                        </v-card>
                    </v-col>
                    <v-col cols="12" md="4">
                        <v-card>
                            <v-card-title>Historial para deshacer</v-card-title>
                            <v-card-text>
                                <v-list>
                                    <v-list-item v-for="(i, index) in useShoppingStore().undoStack" :key="`${i.type}:${index}`">{{ i.type }} {{
                                            i.entries.map((e: ShoppingListEntry) => e.food?.name ?? '')
                                        }}
                                    </v-list-item>
                                </v-list>
                            </v-card-text>
                        </v-card>
                    </v-col>
                </v-row>
            </v-container>
        </v-window-item>
        <v-window-item value="recipes">
            <v-container>
                <v-row>
                    <v-col>
                        <v-card>
                            <v-card-title>{{ $t('Recipes') }} / {{ $t('Meal_Plan') }}</v-card-title>
                            <v-card-text>
                                <v-model-select v-if="canManageShopping" model="Recipe" v-model="manualAddRecipe">
                                    <template #append>
                                        <v-btn icon="$create" color="create" :disabled="manualAddRecipe == undefined">
                                            <v-icon icon="$create"></v-icon>
                                            <add-to-shopping-dialog :recipe="manualAddRecipe" v-if="manualAddRecipe != undefined"
                                                                    @created="useShoppingStore().refreshFromAPI(undefined, canManageShopping); manualAddRecipe = undefined"></add-to-shopping-dialog>
                                        </v-btn>
                                    </template>
                                </v-model-select>

                                <v-list>
                                    <v-list-item v-for="r in useShoppingStore().getAssociatedRecipes()">
                                        <template #prepend>
                                            <v-btn color="edit" icon>
                                                {{ r.servings }}
                                                <number-scaler-dialog
                                                    v-if="r.mealplan == undefined"
                                                    :number="r.servings"
                                                    @confirm="(servings: number) => {updateRecipeServings(r, servings)}"
                                                ></number-scaler-dialog>
                                                <model-edit-dialog model="MealPlan" :item-id="r.mealplan" v-if="r.mealplan != undefined" activator="parent"></model-edit-dialog>
                                            </v-btn>

                                        </template>

                                        <div class="ms-2">
                                            <p v-if="r.recipe">{{ r.recipeData.name }}<br/></p>
                                            <p v-if="r.mealplan">
                                                {{ r.mealPlanData.mealType.name }} - {{ DateTime.fromJSDate(r.mealPlanData.fromDate).toLocaleString(DateTime.DATE_FULL) }}
                                                #{{ r.id }}
                                            </p>
                                        </div>

                                        <template #append>
                                            <v-btn icon color="delete">
                                                <v-icon icon="$delete"></v-icon>
                                                <delete-confirm-dialog :object-name="r.name" :model-name="$t('ShoppingListRecipe')"
                                                                       @delete="deleteListRecipe(r)"></delete-confirm-dialog>
                                            </v-btn>
                                        </template>
                                    </v-list-item>
                                </v-list>


                            </v-card-text>
                        </v-card>
                    </v-col>
                </v-row>
            </v-container>

        </v-window-item>
        <v-window-item v-if="canManageShopping" value="selected_supermarket">
            <v-container>
                <v-row>
                    <v-col>
                        <supermarket-editor :item="selectedSupermarket ?? undefined"
                                            @save="(args: Supermarket) => (useUserPreferenceStore().deviceSettings.shopping_selected_supermarket = args)"></supermarket-editor>
                    </v-col>
                </v-row>
            </v-container>

        </v-window-item>
    </v-window>

</template>

<script setup lang="ts">

import {computed, onMounted, onUnmounted, ref, shallowRef, toRef, watch} from "vue";
import {useShoppingStore} from "@/stores/ShoppingStore";
import {ApiApi, Recipe, ResponseError, ShoppingList, ShoppingListEntry, ShoppingListRecipe, Supermarket, SupermarketCategory} from "@/openapi";
import {ErrorMessageType, PreparedMessage, useMessageStore} from "@/stores/MessageStore";
import ShoppingLineItem from "@/components/display/ShoppingLineItem.vue";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {IShoppingListCategory, IShoppingListFood, ShoppingGroupingOptions} from "@/types/Shopping";
import {useI18n} from "vue-i18n";
import NumberScalerDialog from "@/components/inputs/NumberScalerDialog.vue";
import SupermarketEditor from "@/components/model_editors/SupermarketEditor.vue";
import DeleteConfirmDialog from "@/components/dialogs/DeleteConfirmDialog.vue";
import ShoppingListEntryInput from "@/components/inputs/ShoppingListEntryInput.vue";
import {DateTime} from "luxon";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";
import {onBeforeRouteLeave} from "vue-router";
import ShoppingExportDialog from "@/components/dialogs/ShoppingExportDialog.vue";
import AddToShoppingDialog from "@/components/dialogs/AddToShoppingDialog.vue";
import {TSupermarket} from "@/types/Models.ts";
import ShoppingListSelectChip from "@/components/inputs/ShoppingListSelectChip.vue";
import CategorySelectChip from "@/components/inputs/CategorySelectChip.vue";
import VModelSelect from "@/components/inputs/VModelSelect.vue";

const {t} = useI18n()

const props = defineProps({
    mealPlanId: {type: Number, required: false}
})

const exportDialog = ref(false)
const currentTab = ref("shopping")
const supermarkets = ref([] as Supermarket[])
const canManageShopping = computed(() => {
    const membership = useUserPreferenceStore().activeUserSpace
    return membership?.active !== false && membership?.groups.some(group => ['user', 'admin'].includes(group.name)) === true
})
const selectedSupermarket = computed(() => canManageShopping.value ? useUserPreferenceStore().deviceSettings.shopping_selected_supermarket ?? null : null)
const manualAddRecipe = ref<undefined | Recipe>(undefined)

const selectEnabled = ref(false)
const selectedLines = shallowRef([] as IShoppingListFood[])
const selectedShoppingLists = ref([] as ShoppingList[])

/**
 * VSelect items for shopping list grouping options with localized names
 */
const groupingOptionsItems = computed(() => {
    let items: any[] = []
    Object.values(ShoppingGroupingOptions).forEach(x => {
        items.push({'title': t(x), 'value': x})
    })
    return items
})

/**
 * return the correct pre-cached entries structure depending on where the shopping lsit view is shown
 */
const shoppingListItems = computed(() => {
    if (props.mealPlanId != undefined) {
        return useShoppingStore().entriesByGroupMealPlan
    } else {
        return useShoppingStore().entriesByGroup
    }
})

/**
 * change style of subheaders depending on select mode
 */
const subheaderStyle = computed(() => {
    if (selectEnabled.value) {
        return 'padding-inline-start: 0!important'
    }
    return ''
})

watch(() => useUserPreferenceStore().deviceSettings, () => {
    useShoppingStore().updateEntriesStructure()
}, {deep: true})

watch(() => useShoppingStore().entriesByGroup, () => {
    selectedLines.value = []
})

let stopInitializationWatch: (() => void) | undefined
let shoppingViewActive = false

onMounted(() => {
    shoppingViewActive = true
    addEventListener("visibilitychange", (event) => {
        useShoppingStore().autoSyncHasFocus = (document.visibilityState === 'visible')
    });

    if (useUserPreferenceStore().initCompleted) {
        initializeShopping()
    } else {
        stopInitializationWatch = watch(() => useUserPreferenceStore().initCompleted, initialized => {
            if (initialized) initializeShopping()
        })
    }
})

function initializeShopping() {
    if (!shoppingViewActive) return
    stopInitializationWatch?.()
    stopInitializationWatch = undefined

    if (useUserPreferenceStore().activeUserSpace && !canManageShopping.value) {
        // This filter depends on supermarket data that this membership cannot read.
        // Keep grouping and selected shopping lists while showing all permitted entries.
        useUserPreferenceStore().deviceSettings.shopping_selected_supermarket = null
        useUserPreferenceStore().deviceSettings.shopping_show_selected_supermarket_only = false
    }
    useShoppingStore().refreshFromAPI(undefined, canManageShopping.value)

    autoSyncLoop()

    // refresh selected supermarket since category ordering might have changed
    if (canManageShopping.value && useUserPreferenceStore().deviceSettings.shopping_selected_supermarket != null) {
        new ApiApi().apiSupermarketRetrieve({id: useUserPreferenceStore().deviceSettings.shopping_selected_supermarket!.id!}).then(r => {
            useUserPreferenceStore().deviceSettings.shopping_selected_supermarket = r
        }).catch(err => {
            if (err instanceof ResponseError && err.response.status == 404) {
                useUserPreferenceStore().deviceSettings.shopping_selected_supermarket = null
            }
        })
    }

    if (canManageShopping.value) loadSupermarkets()
    useShoppingStore().loadShoppingLists()
}

/**
 * update the number of servings for an embedded recipe and with it the ShoppingListEntry amounts
 * @param recipe ShoppingListRecipe to update
 * @param servings number of servings to set the recipe to
 */
function updateRecipeServings(recipe: ShoppingListRecipe, servings: number) {
    let api = new ApiApi()
    useShoppingStore().currentlyUpdating = true

    recipe.servings = servings
    api.apiShoppingListRecipeUpdate({id: recipe.id!, shoppingListRecipe: recipe}).then(r => {
        useShoppingStore().currentlyUpdating = false
        useShoppingStore().refreshFromAPI(undefined, canManageShopping.value)
        useMessageStore().addPreparedMessage(PreparedMessage.UPDATE_SUCCESS)
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
        useShoppingStore().currentlyUpdating = false
    })
}

/**
 * run the autosync function in a loop
 */
function autoSyncLoop() {
    // this should not happen in production but sometimes in development with HMR
    clearTimeout(useShoppingStore().autoSyncTimeoutId)

    let timeout = Math.max(useUserPreferenceStore().userSettings.shoppingAutoSync!, 1) * 1000 // if disabled (shopping_auto_sync=0) check again after 1 second if enabled

    useShoppingStore().autoSyncTimeoutId = window.setTimeout(() => {
        if (useUserPreferenceStore().userSettings.shoppingAutoSync! > 0) {
            useShoppingStore().autoSync()
        }
        autoSyncLoop()
    }, timeout)
}

/**
 * cancel auto sync loop before leaving to another page
 */
function stopShoppingView() {
    shoppingViewActive = false
    stopInitializationWatch?.()
    stopInitializationWatch = undefined
    clearTimeout(useShoppingStore().autoSyncTimeoutId)
}

onBeforeRouteLeave(stopShoppingView)
onUnmounted(stopShoppingView)

/**
 * delete shopping list recipe
 */
function deleteListRecipe(slr: ShoppingListRecipe) {
    let api = new ApiApi()

    api.apiShoppingListRecipeDestroy({id: slr.id!}).then(r => {
        useShoppingStore().refreshFromAPI(undefined, canManageShopping.value)
        useMessageStore().addPreparedMessage(PreparedMessage.DELETE_SUCCESS)
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.DELETE_ERROR, err)
    })
}

/**
 * load a list of supermarkets
 */
function loadSupermarkets() {
    if (!canManageShopping.value) return
    let api = new ApiApi()

    api.apiSupermarketList().then(r => {
        supermarkets.value = r.results
        // TODO either recursive or add a "favorite" attribute to supermarkets for them to display at all
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    })
}


function batchUpdateShoppingLists() {
    if (!canManageShopping.value) return
    const selectedEntries = selectedLines.value.flatMap(slf => Array.from(slf.entries.values()))
    useShoppingStore().updateEntryShoppingLists(selectedEntries, selectedShoppingLists.value)
    selectedLines.value = []
}

function undoShoppingChange() {
    if (!canManageShopping.value) return
    useShoppingStore().undoChange()
}

function batchUpdateCategories(category: SupermarketCategory) {
    if (!canManageShopping.value) return
    useShoppingStore().updateCategories(selectedLines.value, category)
    selectedLines.value = []
}

/**
 * select all entries or all entries of a given category
 * @param category
 */
function selectAll(category: IShoppingListCategory | undefined = undefined) {
    shoppingListItems.value.forEach(sLC => {
        if (category != undefined && sLC.name !== category.name) return
        selectedLines.value = selectedLines.value.concat(Array.from(sLC.foods.values()))
    })
}

/**
 * remove the foods that are within a given category from the selected lines array
 * @param category
 */
function deselectCategory(category: IShoppingListCategory) {
    const categoryFoodIds = new Set(Array.from(category.foods.values()).map(f => f.food.id));
    selectedLines.value = selectedLines.value.filter(f => !categoryFoodIds.has(f.food.id));
}

/**
 * check if all foods of a certain category are included in the selected lines array
 * @param category
 */
function isAllSelected(category: IShoppingListCategory | undefined = undefined) {
    let selected = true
    if (category) {
        category.foods.forEach(f => {
            if (!selectedLines.value.includes(f)) {
                selected = false
                return selected
            }
        })
    } else {
        let count = 0
        shoppingListItems.value.forEach(category => {
            count += category.foods.size
        })
        selected = selectedLines.value.length === count
    }
    return selected
}

</script>

<style scoped>
.cuaderno-shopping-tabs { background: rgb(var(--v-theme-surface)); border-bottom: 1px solid rgba(var(--v-theme-on-surface), .14); }
.cuaderno-shopping-tabs :deep(.v-tab) { text-transform: none; letter-spacing: normal; font-weight: 600; min-height: 48px; }
.cuaderno-shopping-tabs :deep(.v-tab--selected) { color: rgb(var(--v-theme-primary)); background: rgba(var(--v-theme-primary), .08); border-radius: 10px 10px 0 0; }
.cuaderno-shopping-toolbar { padding: 10px; border: 1px solid rgba(var(--v-theme-on-surface), .14); border-radius: 12px; background: rgb(var(--v-theme-surface)); }
.cuaderno-shopping-toolbar :deep(.v-slide-group__content) { flex-wrap: wrap; gap: 6px; }
.cuaderno-shopping-toolbar :deep(.v-btn), .cuaderno-shopping-toolbar :deep(.v-chip) { min-height: 44px; }
.cuaderno-shopping-empty { max-width: 640px; }


</style>
