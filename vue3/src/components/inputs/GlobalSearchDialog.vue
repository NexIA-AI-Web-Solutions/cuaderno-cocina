<template>
    <slot name="activator" >
        <v-btn @click="dialog = true" variant="plain" icon="fa-solid fa-search" class="mr-1 fa-fw d-print-none" :aria-label="$t('Search')" :title="$t('Search')" v-if="mobile"></v-btn>
        <v-btn @click="dialog = true" variant="plain" class="d-print-none"  v-else>
            <v-icon icon="fa-solid fa-search" class="mr-1 fa-fw"></v-icon>
            <span class="d-none d-sm-block">{{ $t('Search') }}</span>
            <v-chip size="x-small" variant="tonal" class="d-none d-md-flex ml-1" label>{{ $t('Ctrl+K') }}</v-chip>
        </v-btn>
    </slot>

    <v-dialog v-model="dialog"
              location-strategy="connected"
              :max-width="(mobile) ? '100vw': '800px'"
              :fullscreen="mobile"
    >

        <v-card>
            <v-closable-card-title :title="$t('Search')" v-model="dialog"></v-closable-card-title>
            <!-- search input -->
            <v-card-text class="pt-0 pt-md-2">
                <v-text-field
                    id="id_global_search_input"
                    v-model="searchQuery"
                    autocomplete="off"
                    clearable
                    :label="$t('Search')"
                    :placeholder="$t('Search')"
                    role="combobox"
                    aria-autocomplete="list"
                    aria-controls="cuaderno-search-results"
                    :aria-expanded="dialog"
                    :aria-busy="searchPending"
                    :aria-activedescendant="searchResults[selectedResult] ? `cuaderno-search-result-${selectedResult}` : undefined"
                    prepend-inner-icon="fas fa-search"
                    variant="solo"
                ></v-text-field>

                <p v-if="searchPending" role="status" aria-live="polite" class="text-body-2 mb-2">{{ $t('Loading') }}</p>
                <p v-else-if="searchQuery && !searchPending && !searchResults.some(item => item.recipeId !== undefined)" role="status" class="text-body-2 mb-2">{{ $t('SearchNoMatches') }}</p>
                <div id="cuaderno-search-results" role="listbox" :aria-label="$t('Recipes')">
                <v-card :variant="cardVariant(index)" v-for="(item, index) in searchResults" hover class="mt-2 cuaderno-search-result"
                        :class="{'cuaderno-search-result-selected': selectedResult === index}"
                        role="option" :aria-selected="selectedResult === index" :id="`cuaderno-search-result-${index}`"
                        @click="selectedResult = index" :key="index">
                    <v-card-title @click="goToSelectedRecipe(index)">
                        <v-avatar v-if="item.image" :image="item.image"></v-avatar>
                        <v-avatar v-else-if="item.recipeId !== undefined" color="tandoor">{{ item.name.charAt(0) }}</v-avatar>
                        <v-icon :icon="item.icon" v-if="item.icon"></v-icon>
                        {{ item.name }}
                    </v-card-title>
                </v-card>
                </div>
            </v-card-text>

            <v-divider class="d-none d-sm-block"></v-divider>
            <!-- keybind info shown on screens at least sm -->
            <v-card-text class="d-none d-sm-block pt-2">
                <v-chip size="x-small" class="mr-1" label><i class="fas fa-arrow-up"></i></v-chip>
                <v-chip size="x-small" class="mr-1" label><i class="fas fa-arrow-down"></i></v-chip>
                <small class="mr-2">{{ $t('to_navigate') }}</small>
                <v-chip size="x-small" class="mr-1" label><i class="fas fa-level-down-alt fa-rotate-90"></i></v-chip>
                <small class="mr-2">{{ $t('to_select') }}</small>
                <v-chip size="x-small" class="mr-1" label> esc</v-chip>
                <small>{{ $t('to_close') }}</small>

            </v-card-text>
            <v-card-actions>
                <v-btn @click="dialog=false"  :to="{name: 'SearchPage'}" variant="plain" prepend-icon="$search">{{ $t('Advanced') }}</v-btn>
                <v-btn @click="dialog=false" variant="plain">{{ $t('Close') }}</v-btn>
            </v-card-actions>
        </v-card>


    </v-dialog>
</template>

<script setup lang="ts">

import {computed, onMounted, onUnmounted, ref, watch} from 'vue'
import {SearchResult} from "@/types/SearchTypes";
import {ApiApi, Recipe, RecipeFlat, RecipeOverview} from "@/openapi";
import {useRouter} from "vue-router";
import {useDisplay} from "vuetify";
import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import {useI18n} from "vue-i18n";
import {useDebouncedSearch} from "@/composables/useDebouncedSearch";

const router = useRouter()
const {mobile} = useDisplay()
const {t} = useI18n()

const dialog = ref(false)
const recipes = ref([] as Recipe[])
const flatRecipes = ref([] as RecipeFlat[])
const {inputValue: searchQuery, debouncedValue: debouncedSearchQuery, signal, reset: resetSearch} = useDebouncedSearch()
const selectedResult = ref(0)
const asyncSearchResults = ref([] as RecipeOverview[])

const flatListLoading = ref(false)
const asyncLoading = ref(false)
const asyncResultQuery = ref('')
let searchGeneration = 0
const searchPending = computed(() => flatListLoading.value || Boolean(searchQuery.value &&
    (asyncLoading.value || searchQuery.value !== debouncedSearchQuery.value)))

/**
 * build array of search results
 * uses custom type to be able to incorporate recent items, plans, books, ... at a later stage
 */
const searchResults = computed(() => {
    let searchResults = [] as Array<SearchResult>

    if (searchQuery.value != '' && searchQuery.value != null) {
        flatRecipes.value.filter(fr => fr.name.toLowerCase().includes(searchQuery.value.toLowerCase())).slice(0, 10).forEach(r => {
            searchResults.push({name: r.name, image: r.image, recipeId: r.id, type: "recipe"} as SearchResult)
        })

        if (searchResults.length < 3 && asyncResultQuery.value === searchQuery.value) {
            asyncSearchResults.value.slice(0, 5).forEach(r => {
                if (searchResults.findIndex(x => x.recipeId == r.id) == -1) {
                    searchResults.push({name: r.name, image: r.image, recipeId: r.id, type: "recipe"})
                }
            })
        }

        searchResults.push({name: searchQuery.value, icon: 'fas fa-search', type: "link_advanced_search"} as SearchResult)

    } else {
        // show first 5 recipes by default

        // TODO special "quick links" if applicable
        // searchResults.push({name: 'Recent 1', icon: 'fas fa-history',} as SearchResult)
        // searchResults.push({name: 'Recent 2', icon: 'fas fa-history',} as SearchResult)
        // searchResults.push({name: 'Recent 3', icon: 'fas fa-history',} as SearchResult)

        searchResults.push({name: t('AllRecipes'), icon: 'fas fa-search', type: "link_advanced_search"} as SearchResult)

        flatRecipes.value.slice(0, 5).forEach(r => {
            searchResults.push({name: r.name, image: r.image, recipeId: r.id} as SearchResult)
        })
    }

    return searchResults
})

watch(dialog, (newValue) => {
    /**
     * since dialog has no opened event watch the variable and focus input after delay (nextTick/directly does not work)
     */
    resetSearch()
    asyncSearchResults.value = []
    setTimeout(() => {
        if (newValue) {
            let search = document.getElementById('id_global_search_input')
            if (search != null) {
                search.focus()
            }
        }
    }, 20)
})

watch(searchQuery, () => {
    /**
     * update selected result if search result length changes due to search_query changes
     */
    if (selectedResult.value >= searchResults.value.length) {
        selectedResult.value = searchResults.value.length - 1
    }
})

function handleKeydown(e: KeyboardEvent) {
    if (dialog.value) {
        if (e.key == 'ArrowUp') {
            selectedResult.value = Math.max(0, selectedResult.value - 1)
        }
        if (e.key == 'ArrowDown') {
            selectedResult.value = Math.min(Math.max(0, searchResults.value.length - 1), selectedResult.value + 1)
        }
        if (e.key == 'Enter') {
            goToSelectedRecipe(selectedResult.value)
        }
    } else {
        if (e.key == 'k' && e.ctrlKey) {
            e.preventDefault();
            dialog.value = true
        }
    }
}

onMounted(() => {
    window.addEventListener('keydown', handleKeydown)

    flatListLoading.value = true
    const api = new ApiApi()
    api.apiRecipeFlatList().then(r => {
        flatRecipes.value = r
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        flatListLoading.value = false
    })
})

/**
 * search for query on server after debounce
 */
watch(debouncedSearchQuery, (val) => {
    const generation = ++searchGeneration
    if (val != null && val != '') {
        let api = new ApiApi()
        const requestSignal = signal.value
        asyncLoading.value = true
        api.apiRecipeList({query: val}, {signal: requestSignal}).then(r => {
            if (generation === searchGeneration && !requestSignal?.aborted && searchQuery.value === val) {
                asyncSearchResults.value = r.results
                asyncResultQuery.value = val
            }
        }).catch(err => {
            if (err?.name !== 'AbortError' && err?.cause?.name !== 'AbortError') {
                useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
            }
        }).finally(() => {
            if (generation === searchGeneration) asyncLoading.value = false
        })
    } else {
        asyncLoading.value = false
        asyncSearchResults.value = []
        asyncResultQuery.value = ''
    }
})

onUnmounted(() => {
    window.removeEventListener('keydown', handleKeydown)
})

/**
 * determines the style for selected elements
 * @param index index of card to determine style for
 */
function cardVariant(index: number) {
    if (selectedResult.value == index) {
        return 'tonal'
    } else {
        return 'elevated'
    }
}

/**
 * open selected recipe
 */
function goToSelectedRecipe(index: number) {
    dialog.value = false
    const searchResult = searchResults.value[index]
    if (!searchResult) return

    if (searchResult.type == 'link_advanced_search') {
        router.push({name: 'SearchPage', query: {'query': searchQuery.value}})
    } else {
        console.log('going to', searchResult.recipeId)
        if (searchResult.recipeId != null) {
            router.push({name: 'RecipeViewPage', params: {'id': searchResult.recipeId}})
        }
    }


}
</script>


<style scoped>
.cuaderno-search-result { border-inline-start: 4px solid transparent; }
.cuaderno-search-result-selected { border-inline-start-color: rgb(var(--v-theme-primary)); }
.cuaderno-search-result :deep(.v-card-title) {
    font-size: 1rem;
    line-height: 1.5;
    white-space: normal;
    display: flex;
    align-items: center;
    gap: 12px;
}
</style>
