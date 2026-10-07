<template>
    <v-container>
        <v-row>
            <v-col cols="12" md="6" offset-md="3">
                <v-text-field :label="$t('Search')"
                              v-model="query"
                              :loading="loading"
                              @keydown.enter="flushQuery()"
                              @click:clear="resetQuery()"
                              clearable hide-details>
                    <template v-slot:append>
                        <v-badge bordered :offset-x="5" :offset-y="5" color="secondary" v-model="hasFiltersApplied">
                            <v-btn @click="panel ='search' " v-if="panel == ''" color="primary" icon>
                                <i class="fa-solid fa-caret-down"></i></v-btn>
                            <v-btn @click="panel ='' " v-if="panel == 'search'" color="primary" icon><i class="fa-solid fa-caret-up"></i></v-btn>
                        </v-badge>
                    </template>
                </v-text-field>
            </v-col>
        </v-row>
        <v-row dense>
            <v-col>
                <v-expansion-panels v-model="panel">
                    <v-expansion-panel value="search">
                        <v-expansion-panel-text>
                            <v-form :disabled="loading" class="mt-4">

                                <div v-for="filter in Object.values(filters)" :key="filter.id">
                                    <template v-if="filter.enabled">
                                        <component :="getPropsFromFilter(filter)" :is="filter.is" density="compact" v-model:modelValue="filter.modelValue">
                                            <template #append>
                                                <v-btn icon="fa-solid fa-times" size="small" variant="plain"
                                                       @click="filter.enabled = false; filter.modelValue = filter.default"></v-btn>
                                            </template>
                                        </component>
                                    </template>
                                </div>

                                <v-divider class="mt-2 mb-2"></v-divider>

                                <v-autocomplete :items="availableFilters"
                                                @update:model-value="enableFilter" density="compact"
                                                :label="$t('AddFilter')" v-model="addFilterSelect"></v-autocomplete>

                                <v-model-select model="CustomFilter" v-model="selectedCustomFilter" density="compact">
                                    <template #append>
                                        <v-btn icon="fa-solid fa-upload" color="warning" :disabled="selectedCustomFilter == null"
                                               @click="loadSelectedCustomFilter()"></v-btn>
                                        <v-btn icon="$save" class="ms-1" color="save" @click="saveCustomFilter()"></v-btn>
                                    </template>
                                </v-model-select>
                            </v-form>
                            <v-row>
                                <v-col cols="6">
                                    <v-select :label="$t('View')" v-model="useUserPreferenceStore().deviceSettings.search_viewMode"
                                              :items="[{title: $t('Table'), value: 'table'}, {title: $t('Cards'), value: 'grid'},]" density="compact"></v-select>
                                </v-col>
                                <v-col cols="6">
                                    <v-select class="float-right" :label="$t('PerPage')" v-model="pageSize" :items="[10,25,50,100]" density="compact"
                                              width="100%"></v-select>
                                </v-col>
                            </v-row>

                        </v-expansion-panel-text>

                        <v-card-actions v-if="panel == 'search'">
                            <v-btn @click="reset()" prepend-icon="$reset">{{ $t('Reset') }}</v-btn>
                            <v-btn @click="searchRecipes({page: 1})" prepend-icon="$search">{{ $t('Search') }}</v-btn>
                        </v-card-actions>
                    </v-expansion-panel>
                </v-expansion-panels>

            </v-col>
        </v-row>

        <v-row v-if="recipes.length > 0 && useUserPreferenceStore().deviceSettings.search_viewMode == 'table'">
            <v-col>
                <v-card>
                    <v-data-table-server
                        v-model="selectedItems"
                        return-object
                        @update:options="searchRecipes"
                        :loading="loading"
                        :items="recipes"
                        :headers="tableHeaders"
                        :page="page"
                        :items-per-page="pageSize"
                        :items-length="tableItemCount"
                        @click:row="handleRowClick"
                        disable-sort
                        show-select
                        hide-default-footer
                    >
                        <template v-slot:header.action v-if="selectedItems.length > 0">
                            <v-btn icon="fa-solid fa-ellipsis-v" variant="plain" color="info">
                                <v-icon icon="fa-solid fa-ellipsis-v"></v-icon>
                                <v-menu activator="parent" close-on-content-click>
                                    <v-list density="compact" class="pt-1 pb-1" activatable>
                                        <v-list-item prepend-icon="$edit" @click="batchEditDialog = true">
                                            {{ $t('BatchEdit') }}
                                        </v-list-item>
                                        <v-list-item prepend-icon="$delete" @click="batchDeleteDialog = true">
                                            {{ $t('Delete_All') }}
                                        </v-list-item>
                                    </v-list>
                                </v-menu>
                            </v-btn>
                        </template>

                        <template #item.image="{item}">
                            <v-avatar :image="item.image" size="x-large" class="mt-1 mb-1" v-if="item.image"></v-avatar>
                            <v-avatar color="primary" variant="tonal" size="x-large" class="mt-1 mb-1" v-else>
                                <random-icon></random-icon>
                            </v-avatar>
                        </template>

                        <template #item.keywords="{item}">
                            <keywords-bar :keywords="item.keywords"></keywords-bar>
                        </template>

                        <template #item.action="{item}">
                            <recipe-context-menu :recipe="item"></recipe-context-menu>
                        </template>
                    </v-data-table-server>
                </v-card>
            </v-col>
        </v-row>

        <template v-if="recipes.length > 0 && useUserPreferenceStore().deviceSettings.search_viewMode == 'grid'">
            <v-row>
                <v-col cols="6" md="4" v-for="r in recipes" :key="r.id" class="pa-0">
                    <recipe-card :recipe="r"></recipe-card>
                </v-col>

            </v-row>

        </template>
        <v-row>
            <v-col cols="12" md="6" offset-md="3" class="text-center">
                <v-pagination v-model="page" :length="Math.ceil(tableItemCount/pageSize)"
                              @update:modelValue="searchRecipes({page: page})" class="ms-2 me-2" size="small"
                              v-if="filters['sortOrder'].modelValue != 'random'"
                ></v-pagination>
                <v-btn size="x-large" rounded="xl" prepend-icon="fa-solid fa-dice" variant="tonal" v-if="filters['sortOrder'].modelValue == 'random'"
                       @click="searchRecipes({page: 1})">
                    {{ $t('Random Recipes') }}
                </v-btn>
            </v-col>
        </v-row>


        <v-dialog v-model="dialog">
            <v-card>
                <v-closable-card-title :title="$t('SavedSearch')" v-model="dialog"></v-closable-card-title>
                <v-card-text>
                    <v-text-field :label="$t('Name')" v-model="newFilterName"></v-text-field>
                </v-card-text>
                <v-card-actions>
                    <v-btn prepend-icon="$create" color="create" @click="createCustomFilter()">{{ $t('Create') }}</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <batch-delete-dialog :items="selectedItems" model="Recipe" v-model="batchDeleteDialog" activator="model" @change="searchRecipes({page: 1})"></batch-delete-dialog>
        <batch-edit-recipe-dialog :items="selectedItems" v-model="batchEditDialog" activator="model" @change="searchRecipes({page: page})"></batch-edit-recipe-dialog>

    </v-container>
</template>

<script setup lang="ts">

import {computed, markRaw, nextTick, onMounted, ref, toRaw, watch} from "vue";
import {ApiApi, ApiRecipeListRequest, CustomFilter, RecipeOverview} from "@/openapi";
import {useI18n} from "vue-i18n";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {VDateInput} from 'vuetify/labs/VDateInput'
import RecipeContextMenu from "@/components/inputs/RecipeContextMenu.vue";
import {useRouter} from "vue-router";
import KeywordsBar from "@/components/display/KeywordsBar.vue";
import {VDataTableUpdateOptions} from "@/vuetify";
import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import RecipeCard from "@/components/display/RecipeCard.vue";
import {useDisplay} from "vuetify";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import {useRouteQuery} from "@vueuse/router";
import {boolOrUndefinedTransformer, numberOrUndefinedTransformer, routeQueryDateTransformer, stringToBool, toNumberArray} from "@/utils/utils";
import {useDebouncedSearch} from "@/composables/useDebouncedSearch";
import RandomIcon from "@/components/display/RandomIcon.vue";
import {VSelect, VTextField, VNumberInput, VDataTable} from "vuetify/components";
import RatingField from "@/components/inputs/RatingField.vue";
import BatchDeleteDialog from "@/components/dialogs/BatchDeleteDialog.vue";
import BatchEditRecipeDialog from "@/components/dialogs/BatchEditRecipeDialog.vue";
import VModelSelect from "@/components/inputs/VModelSelect.vue";

const {t} = useI18n()
const router = useRouter()
const {mdAndUp} = useDisplay()

const {inputValue: query, debouncedValue: debouncedQuery, signal, flush: flushQuery, reset: resetQuery} = useDebouncedSearch({routeQueryKey: 'query'})
const page = useRouteQuery('page', 1, {transform: Number})
const pageSize = useRouteQuery('pageSize', useUserPreferenceStore().deviceSettings.search_itemsPerPage, {transform: Number})

/**
 * filters that are not yet enabled
 */
const availableFilters = computed(() => {
    let f: Array<{ value: string, title: string }> = []
    useUserPreferenceStore().deviceSettings.search_visibleFilters = []
    Object.entries(filters.value).forEach((entry) => {
        let [key, filter] = entry
        if (!filter.enabled) {
            f.push({value: filter.id, title: filter.label})
        } else {
            useUserPreferenceStore().deviceSettings.search_visibleFilters.push(filter.id)
        }
    })
    return f
})

const loading = ref(false)
const dialog = ref(false)
const panel = ref('')
const addFilterSelect = ref<string | null>(null)
const hasFiltersApplied = ref(false)

const tableHeaders = computed(() => {
    let headers: NonNullable<InstanceType<typeof VDataTable>['$props']['headers']>[number][] = [
        {title: t('Image'), width: '1%',  key: 'image',},
        {title: t('Name'), key: 'name',},
    ]
    if (mdAndUp.value) {
        headers.push({title: t('Keywords'), key: 'keywords',},)
    }
    headers.push({title: t('Actions'), key: 'action', width: '1%',  align: 'end'},)

    return headers
})

const tableItemCount = ref(0)

const recipes = ref([] as RecipeOverview[])
const selectedCustomFilter = ref<null | CustomFilter>(null)
const newFilterName = ref('')

const selectedItems = ref<RecipeOverview[]>([])
const batchDeleteDialog = ref(false)
const batchEditDialog = ref(false)
let searchRevision = 0

/**
 * handle query updates when using the GlobalSearchDialog on the search page directly
 */
watch(debouncedQuery, () => {
    searchRecipes({page: 1})
})

/**
 * perform initial search on mounted
 */
onMounted(() => {
    // load filters that were previously enabled
    useUserPreferenceStore().deviceSettings.search_visibleFilters.forEach(f => {
        const filter = filterByName.value.get(String(f))
        if (filter) {
            filter.enabled = true
        } else {
            useUserPreferenceStore().deviceSettings.search_visibleFilters.splice(useUserPreferenceStore().deviceSettings.search_visibleFilters.indexOf(f), 1)
        }
    })

    enableFiltersWithValues()
    searchRecipes({page: page.value})
})

/**
 * perform the recipe search with the given options
 * @param options
 */
function searchRecipes(options: Pick<VDataTableUpdateOptions, 'page'>) {
    const revision = ++searchRevision
    let api = new ApiApi()
    loading.value = true
    hasFiltersApplied.value = false
    selectedItems.value = []

    page.value = options.page
    let searchParameters = {
        query: debouncedQuery.value,
        page: options.page,
        pageSize: pageSize.value,
    } as ApiRecipeListRequest

    useUserPreferenceStore().deviceSettings.search_itemsPerPage = pageSize.value

    Object.values(filters.value).forEach((filter) => {
        if (!isFilterDefaultValue(filter)) {
            Object.assign(searchParameters, {[filter.id]: filter.modelValue})
            hasFiltersApplied.value = true
        }
    })

    return api.apiRecipeList(searchParameters, {signal: signal.value}).then((r) => {
        if (revision !== searchRevision) return
        recipes.value = r.results
        tableItemCount.value = r.count
    }).catch(err => {
        if (revision !== searchRevision) return
        if (err.name !== 'AbortError' && err.cause?.name !== 'AbortError') {
            useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        }
    }).finally(() => {
        if (revision !== searchRevision) return
        loading.value = false
        window.scrollTo({top: 0, behavior: 'smooth'})
    })
}

/**
 * reset all search parameters and perform emtpy search
 */
function reset() {
    page.value = 1
    resetQuery()
    Object.values(filters.value).forEach((filter) => {
        //filter.enabled = false
        filter.modelValue = filter.default
    })
    selectedCustomFilter.value = null
    recipes.value = []
    searchRecipes({page: 1})
}

/**
 * handle clicking a table row by opening the selected recipe
 * @param event
 * @param data
 */
function handleRowClick(event: PointerEvent, data: any) {
    const recipe = recipes.value[data.index]
    if (recipe) router.push({name: 'RecipeViewPage', params: {id: recipe.id}})
}

/**
 * enable UI of filters that have a value that is not the default for the given filter
 */
function enableFiltersWithValues() {
    Object.values(filters.value).forEach((filter) => {
        if (!isFilterDefaultValue(filter)) {
            filter.enabled = true
        }
    })
}

/**
 * determines if the current value of a filter is its default value
 * @param filter
 */
function isFilterDefaultValue(filter: any) {
    if (Array.isArray(filter.default) && Array.isArray(filter.modelValue)) {
        return filter.default.length == filter.modelValue.length
    } else if (Number.isNaN(filter.default) && Number.isNaN(filter.modelValue)) {
        return true
    } else {
        return toRaw(filter.default) === filter.modelValue
    }
}

/**
 * to prevent browser warnings from unused/wrong props on the target component
 * @param filter
 */
function getPropsFromFilter(filter: any){
    const {
        id,
        enabled,
        is,
        default: defaultValue,
        ...props
    } = filter

    return props
}

// -------------------------------------------
// --------- Logic for saved filters ---------
// -------------------------------------------

/**
 * triggered by save button, if filter exists update it, if not open dialog to create a new filter
 */
function saveCustomFilter() {
    let api = new ApiApi()

    if (selectedCustomFilter.value != null) {
        loading.value = true
        selectedCustomFilter.value.search = JSON.stringify(filtersToCustomFilterFormat())
        api.apiCustomFilterUpdate({id: selectedCustomFilter.value.id!, customFilter: selectedCustomFilter.value}).then((r) => {
            selectedCustomFilter.value = r
        }).catch(err => {
            useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
        }).finally(() => {
            loading.value = false
        })
    } else {
        newFilterName.value = ''
        dialog.value = true
    }
}

/**
 * create a new saved search filter in the database via api
 */
function createCustomFilter() {
    let api = new ApiApi()

    dialog.value = false
    loading.value = true
    api.apiCustomFilterCreate({customFilter: {name: newFilterName.value, search: JSON.stringify(filtersToCustomFilterFormat())} as CustomFilter}).then((r) => {
        selectedCustomFilter.value = r
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
    }).finally(() => {
        loading.value = false
    })
}

/**
 * load selected custom filter into the filters system
 */
function loadSelectedCustomFilter() {
    if (!selectedCustomFilter.value) return
    let customFilterParams: Record<string, any>
    try {
        customFilterParams = JSON.parse(selectedCustomFilter.value.search)
        if (!customFilterParams || typeof customFilterParams !== 'object' || Array.isArray(customFilterParams)) {
            throw new Error('Invalid saved filter')
        }
        if (customFilterParams['query'] != null && typeof customFilterParams['query'] !== 'string') throw new Error('Invalid saved query')
        if (customFilterParams['version'] == null) customFilterParams = transformTandoor1Filter(customFilterParams)
    } catch (err) {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        return
    }

    resetQuery()
    query.value = customFilterParams['query'] ?? ''

    Object.values(filters.value).forEach((filter) => {
        filter.modelValue = Array.isArray(filter.default) ? [...filter.default] : filter.default
        filter.enabled = false
        let filterName = filter.id.replace(/([a-z])([A-Z])/g, '$1_$2').toLowerCase()
        if (customFilterParams[filterName] != null) {
            filter.modelValue = customFilterParams[filterName]
            filter.enabled = true
        }
    })

}

/**
 * convert filters to custom filter format
 */
function filtersToCustomFilterFormat() {
    let customFilterParams: any = {};

    if (query.value != '') {
        customFilterParams['query'] = query.value;
    }

    Object.values(filters.value).forEach((filter) => {
        if (!isFilterDefaultValue(filter)) {
            let filterName = filter.id.replace(/([a-z])([A-Z])/g, '$1_$2').toLowerCase()
            customFilterParams[filterName] = filter.modelValue
        }
    })

    customFilterParams['version'] = '2'

    return customFilterParams
}

/**
 * transform a filter that is in the tandoor 1 format into the tandoor 2 format
 * @param customFilterParams
 */
function transformTandoor1Filter(customFilterParams: any) {

    // _or was basically an alias to the standard filter which behaves like an or filter
    for (const [legacy, current] of [['books_or', 'books'], ['foods_or', 'foods'], ['keywords_or', 'keywords']] as const) {
        if (Array.isArray(customFilterParams[legacy])) {
            customFilterParams[current] = [...(customFilterParams[current] ?? []), ...customFilterParams[legacy]]
        }
    }

    if (customFilterParams['cookedon'] != null) {
        if (customFilterParams['cookedon'].startsWith('-')) {
            customFilterParams['cookedon_lte'] = customFilterParams['cookedon'].substring(1)
        } else {
            customFilterParams['cookedon_gte'] = customFilterParams['cookedon']
        }
    }

    if (customFilterParams['viewedon'] != null) {
        if (customFilterParams['viewedon'].startsWith('-')) {
            customFilterParams['viewedon_lte'] = customFilterParams['viewedon'].substring(1)
        } else {
            customFilterParams['viewedon_gte'] = customFilterParams['viewedon']
        }
    }

    if (customFilterParams['updatedon'] != null) {
        if (customFilterParams['updatedon'].startsWith('-')) {
            customFilterParams['updatedon_lte'] = customFilterParams['updatedon'].substring(1)
        } else {
            customFilterParams['updatedon_gte'] = customFilterParams['updatedon']
        }
    }

    if (customFilterParams['createdon'] != null) {
        if (customFilterParams['createdon'].startsWith('-')) {
            customFilterParams['createdon_lte'] = customFilterParams['createdon'].substring(1)
        } else {
            customFilterParams['createdon_gte'] = customFilterParams['createdon']
        }
    }

    if (customFilterParams['rating'] != null) {
        if (customFilterParams['rating'].startsWith('-')) {
            customFilterParams['rating_lte'] = customFilterParams['rating'].substring(1)
        } else {
            customFilterParams['rating_gte'] = customFilterParams['rating']
        }
    }

    if (customFilterParams['timescooked'] != null) {
        if (customFilterParams['timescooked'].startsWith('-')) {
            customFilterParams['timescooked_lte'] = customFilterParams['timescooked'].substring(1)
        } else {
            customFilterParams['timescooked_gte'] = customFilterParams['timescooked']
        }
    }

    customFilterParams['version'] = '2'

    return customFilterParams
}

/*
[this.$t("search_rank"), "score", "1-9", "9-1"],
[this.$t("Name"), "name", "A-z", "Z-a"],
[this.$t("last_cooked"), "lastcooked", "↑", "↓"],
[this.$t("Rating"), "rating", "1-5", "5-1"],
[this.$t("times_cooked"), "favorite", "x-X", "X-x"],
[this.$t("date_created"), "created_at", "↑", "↓"],
[this.$t("date_viewed"), "lastviewed", "↑", "↓"],
*/
/**
 * all filters available to enable
 */
const filters = ref({
    sortOrder: {
        id: 'sortOrder',
        label: `${t('sort_by')}`,
        hint: '',
        enabled: false,
        default: "",
        is: VSelect,
        items: [
            {value: "random", title: `${t('RandomOrder')}`},
            {value: "score", title: `${t('search_rank')} (1-9)`},
            {value: "-score", title: `${t('search_rank')} (9-1)`},
            {value: "name", title: `${t('Name')} (A-z)`},
            {value: "-name", title: `${t('Name')} (Z-a)`},
            {value: "lastcooked", title: `${t('last_cooked')} (↑)`},
            {value: "-lastcooked", title: `${t('last_cooked')} (↓)`},
            {value: "rating", title: `${t('Rating')} (1-5)`},
            {value: "-rating", title: `${t('Rating')} (5-1)`},
            {value: "times_cooked", title: `${t('favorite')} (↑)`},
            {value: "-times_cooked", title: `${t('favorite')} (↓)`},
            {value: "created_at", title: `${t('date_created')} (↑)`},
            {value: "-created_at", title: `${t('date_created')} (↓)`},
            {value: "lastviewed", title: `${t('date_viewed')} (↑)`},
            {value: "-lastviewed", title: `${t('date_viewed')} (↓)`},
        ],
        modelValue: useRouteQuery<string>('sortOrder', "")
    },
    keywords: {
        id: 'keywords',
        label: `${t('Keywords')} (${t('any')})`,
        hint: t('searchFilterObjectsHelp', {type: t('Keywords')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Keyword',
        modelValue: useRouteQuery('keywords', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    keywordsAnd: {
        id: 'keywordsAnd',
        label: `${t('Keywords')} (${t('all')})`,
        hint: t('searchFilterObjectsAndHelp', {type: t('Keywords')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Keyword',
        modelValue: useRouteQuery('keywordsAnd', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    keywordsOrNot: {
        id: 'keywordsOrNot',
        label: `${t('Keywords')} ${'exclude'} (${t('any')})`,
        hint: t('searchFilterObjectsOrNotHelp', {type: t('Keywords')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Keyword',
        modelValue: useRouteQuery('keywordsOrNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    keywordsAndNot: {
        id: 'keywordsAndNot',
        label: `${t('Keywords')} ${'exclude'} (${t('all')})`,
        hint: t('searchFilterObjectsAndNotHelp', {type: t('Keywords')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Keyword',
        modelValue: useRouteQuery('keywordsAndNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    foods: {
        id: 'foods',
        label: `${t('Foods')} (${t('any')})`,
        hint: t('searchFilterObjectsHelp', {type: t('Foods')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Food',
        modelValue: useRouteQuery('foods', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    foodsAnd: {
        id: 'foodsAnd',
        label: `${t('Foods')} (${t('all')})`,
        hint: t('searchFilterObjectsAndHelp', {type: t('Foods')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Food',
        modelValue: useRouteQuery('foodsAnd', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    foodsOrNot: {
        id: 'foodsOrNot',
        label: `${t('Foods')} ${'exclude'} (${t('any')})`,
        hint: t('searchFilterObjectsOrNotHelp', {type: t('Foods')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Food',
        modelValue:  useRouteQuery('foodsOrNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    foodsAndNot: {
        id: 'foodsAndNot',
        label: `${t('Foods')} ${'exclude'} (${t('all')})`,
        hint: t('searchFilterObjectsAndNotHelp', {type: t('Foods')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Food',
        modelValue: useRouteQuery('foodsAndNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    books: {
        id: 'books',
        label: `${t('Books')} (${t('any')})`,
        hint: t('searchFilterObjectsHelp', {type: t('Books')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'RecipeBook',
        modelValue: useRouteQuery('books', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    booksAnd: {
        id: 'booksAnd',
        label: `${t('Books')} (${t('all')})`,
        hint: t('searchFilterObjectsAndHelp', {type: t('Books')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'RecipeBook',
        modelValue: useRouteQuery('booksAnd', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    booksOrNot: {
        id: 'booksOrNot',
        label: `${t('Books')} ${'exclude'} (${t('any')})`,
        hint: t('searchFilterObjectsOrNotHelp', {type: t('Books')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'RecipeBook',
        modelValue: useRouteQuery('booksOrNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    booksAndNot: {
        id: 'booksAndNot',
        label: `${t('Books')} ${'exclude'} (${t('all')})`,
        hint: t('searchFilterObjectsAndNotHelp', {type: t('Books')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'RecipeBook',
        modelValue: useRouteQuery('booksAndNot', [], {transform: toNumberArray}),
        returnObject: false,
        multiple: true,
        chips: true,
    },
    createdby: {
        id: 'createdby',
        label: t('CreatedBy'),
        hint: t('searchFilterCreatedByHelp'),
        enabled: false,
        default: undefined,
        is: markRaw(VModelSelect),
        model: 'User',
        modelValue: useRouteQuery<string | undefined, number | undefined>('createdby', undefined, {transform: numberOrUndefinedTransformer}),
        returnObject: false,
    },
    units: {
        id: 'units',
        label: `${t('Units')} (${t('any')})`,
        hint: t('searchFilterObjectsHelp', {type: t('Units')}),
        enabled: false,
        default: [],
        is: markRaw(VModelSelect),
        model: 'Unit',
        modelValue: [],
        modelValueId: useRouteQuery('units', [], {transform: toNumberArray}),
        multiple: true,
        chips: true,
    },
    internal: {
        id: 'internal',
        label: t('Hide_External'),
        hint: t('searchFilterHideExternalHelp'),
        enabled: false,
        default: undefined,
        is: markRaw(VSelect),
        items: [{value: true, title: 'Yes'}, {value: false, title: 'No'}],
        modelValue: useRouteQuery('internal', undefined, {transform: boolOrUndefinedTransformer})
    },
    // random: {
    //     id: 'random',
    //     label: t('RandomOrder'),
    //     hint: t('searchFilterRandomHelp'),
    //     enabled: false,
    //     default: "false",
    //     is: VSelect,
    //     items: [{value: "true", title: 'Yes'}, {value: "false", title: 'No'}],
    //     modelValue: useRouteQuery('random', "false")
    // },
    rating: {
        id: 'rating',
        label: `${t('Rating')} (${t('exact')})`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(RatingField),
        modelValue: useRouteQuery<string | undefined, number | undefined>('rating', undefined, {transform: numberOrUndefinedTransformer}),
    },
    ratingGte: {
        id: 'ratingGte',
        label: `${t('Rating')} (>=)`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(RatingField),
        modelValue: useRouteQuery<string | undefined, number | undefined>('ratingGte', undefined, {transform: numberOrUndefinedTransformer}),
    },
    ratingLte: {
        id: 'ratingLte',
        label: `${t('Rating')} (<=)`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(RatingField),
        modelValue: useRouteQuery<string | undefined, number | undefined>('ratingLte', undefined, {transform: numberOrUndefinedTransformer}),
    },
    timescooked: {
        id: 'timescooked',
        label: `${t('times_cooked')} (${t('exact')})`,
        hint: 'Recipes that were cooked at least X times',
        enabled: false,
        default: undefined,
        clearable: true,
        is: markRaw(VNumberInput),
        modelValue: useRouteQuery<string | undefined, number | undefined>('timescooked', undefined, {transform: numberOrUndefinedTransformer}),
    },
    timescookedGte: {
        id: 'timescookedGte',
        label: `${t('times_cooked')} (>=)`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(VNumberInput),
        modelValue: useRouteQuery<string | undefined, number | undefined>('timescookedGte', undefined, {transform: numberOrUndefinedTransformer}),
    },
    timescookedLte: {
        id: 'timescookedLte',
        label: `${t('times_cooked')} (<=)`,
        hint: '',
        enabled: false,
        clearable: true,
        default: undefined,
        is: markRaw(VNumberInput),
        modelValue: useRouteQuery<string | undefined, number | undefined>('timescookedLte', undefined, {transform: numberOrUndefinedTransformer}),
    },
    makenow: {
        id: 'makenow',
        label: t('OnHand'),
        hint: t('searchFilterOnHandHelp'),
        enabled: false,
        default: "false",
        is: markRaw(VSelect),
        items: [{value: "true", title: 'Yes'}, {value: "false", title: 'No'}],
        modelValue: useRouteQuery<string>('makenow', "false"),
    },
    cookedonGte: {
        id: 'cookedonGte',
        label: `${t('Cooked')} ${t('after')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('cookedonGte', null, {transform: routeQueryDateTransformer}),
    },
    cookedonLte: {
        id: 'cookedonLte',
        label: `${t('Cooked')} ${t('before')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('cookedonLte', null, {transform: routeQueryDateTransformer}),
    },
    viewedonGte: {
        id: 'viewedonGte',
        label: `${t('Viewed')} ${t('after')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('viewedonGte', null, {transform: routeQueryDateTransformer}),
    },
    viewedonLte: {
        id: 'viewedonLte',
        label: `${t('Viewed')} ${t('before')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('viewedonLte', null, {transform: routeQueryDateTransformer}),
    },
    createdon: {
        id: 'createdon',
        label: `${t('Created')} ${t('on')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('createdon', null, {transform: routeQueryDateTransformer}),
    },
    createdonGte: {
        id: 'createdonGte',
        label: `${t('Created')} ${t('on')}/${t('after')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('createdonGte', null, {transform: routeQueryDateTransformer}),
    },
    createdonLte: {
        id: 'createdonLte',
        label: `${t('Created')} ${t('on')}/${t('before')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('createdonLte', null, {transform: routeQueryDateTransformer}),
    },
    updatedon: {
        id: 'updatedon',
        label: `${t('Updated')} ${t('on')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('updatedon', null, {transform: routeQueryDateTransformer}),
    },
    updatedonGte: {
        id: 'updatedonGte',
        label: `${t('Updated')} ${t('on')}/${t('after')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('updatedonGte', null, {transform: routeQueryDateTransformer}),
    },
    updatedonLte: {
        id: 'updatedonLte',
        label: `${t('Updated')} ${t('on')}/${t('before')}`,
        hint: '',
        enabled: false,
        default: null,
        is: markRaw(VDateInput),
        modelValue: useRouteQuery('updatedonLte', null, {transform: routeQueryDateTransformer}),
    },
    includeChildren: {
        id: 'includeChildren',
        label: t('Include Children'),
        hint: t('Include child keywords and foods in search results'),
        enabled: false,
        default: "true",  // Default enabled like v1
        is: markRaw(VSelect),
        items: [{value: "true", title: 'Yes'}, {value: "false", title: 'No'}],
        modelValue: useRouteQuery('includeChildren', 'true')
    },
})

const filterByName = computed(() => new Map(Object.entries(filters.value)))
function enableFilter(name: string | null) {
    if (!name) return
    const filter = filterByName.value.get(name)
    if (!filter) return
    filter.enabled = true
    nextTick(() => {addFilterSelect.value = null})
}

</script>

<style scoped>

</style>
