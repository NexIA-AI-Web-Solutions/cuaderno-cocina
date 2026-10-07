<template>
    <v-container>
        <v-row>
            <v-col>
                <v-card>
                    <v-card-title>{{ book.name }}
                        <v-btn class="float-right" variant="flat" :to="{name: 'BooksPage'}" prepend-icon="$books" v-if="mdAndUp">{{ $t('Books') }}</v-btn>
                    </v-card-title>
                    <v-card-text v-if="book.shared && book.shared.length > 0">
                        <v-chip-group>
                            <v-label class="me-2">{{ $t('shared_with') }}</v-label>
                            <v-chip v-for="u in book.shared">{{ u.displayName }}</v-chip>
                        </v-chip-group>
                    </v-card-text>
                    <v-card-text class="text-disabled">
                        {{ book.description }}
                    </v-card-text>
                    <v-expansion-panels v-model="toc">
                        <v-expansion-panel>
                            <v-expansion-panel-title>{{ $t('Table_of_Contents') }}</v-expansion-panel-title>
                            <v-expansion-panel-text>
                                <v-list>
                                    <v-list-item v-for="(entry, i) in recipes" :key="entry.id" @click="setPage(i); toc = false">
                                        {{ entry.name }}
                                    </v-list-item>
                                </v-list>
                            </v-expansion-panel-text>
                        </v-expansion-panel>
                    </v-expansion-panels>
                </v-card>
            </v-col>
        </v-row>

        <v-row>
            <v-col class="text-center">
                <v-pagination :model-value="currentPageNumber"
                              @update:model-value="value => setPage((value - 1) * recipesPerPage)"
                              :length="totalPages"
                ></v-pagination>
            </v-col>
        </v-row>

        <v-row>
            <v-col cols="12">
                <v-window v-model="page" show-arrows>
                    <template #next>
                        <v-btn icon="fa-solid fa-chevron-right" variant="plain" @click="movePage(1)" :disabled="page >= lastPage"></v-btn>
                    </template>
                    <template #prev>
                        <v-btn icon="fa-solid fa-chevron-left" variant="plain" @click="movePage(-1)" :disabled="page <= 0"></v-btn>
                    </template>

                    <v-window-item v-for="(entry, i) in recipes" :key="entry.id">
                        <v-row>
                            <v-col cols="12" md="6">
                                <book-entry-card :recipe-overview="entry"></book-entry-card>
                                <div class="text-center mt-1">
                                    <span class="text-disabled">{{ i + 1 }}</span>
                                </div>
                            </v-col>
                            <v-col cols="6" v-for="nextRecipe in (mdAndUp ? recipes.slice(i + 1, i + 2) : [])" :key="nextRecipe.id">
                                <book-entry-card :recipe-overview="nextRecipe"></book-entry-card>
                                <div class="text-center mt-1">
                                    <span class="text-disabled">{{ i + 2 }}</span>
                                </div>
                            </v-col>
                        </v-row>
                    </v-window-item>
                </v-window>
            </v-col>
        </v-row>
    </v-container>
</template>

<script setup lang="ts">


import {computed, ref, watch} from "vue";
import {ApiApi, RecipeBook, RecipeBookEntry, RecipeOverview} from "@/openapi";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import {useRouter} from "vue-router";
import RecipeImage from "@/components/display/RecipeImage.vue";
import {useDisplay} from "vuetify";
import BookEntryCard from "@/components/display/BookEntryCard.vue";

const props = defineProps({
    bookId: {type: String, required: true},
})

const {mdAndUp} = useDisplay()
const router = useRouter()

const loading = ref(false)
const loadingEntries = ref(false)
const toc = ref(false)
const page = ref(0)

const manualItems = ref(0)
const filterItems = ref(0)

const recipesPerPage = computed(() => mdAndUp.value ? 2 : 1)
const totalRecipes = computed(() => manualItems.value + filterItems.value)
const totalPages = computed(() => Math.ceil(totalRecipes.value / recipesPerPage.value))
const currentPageNumber = computed(() => Math.floor(page.value / recipesPerPage.value) + 1)

const book = ref({} as RecipeBook)
const entries = ref([] as RecipeBookEntry[])
const recipes = ref([] as RecipeOverview[])

let bookRevision = 0
const lastPage = computed(() => Math.max(0, Math.floor((recipes.value.length - 1) / recipesPerPage.value) * recipesPerPage.value))

function setPage(index: number) {
    page.value = Math.max(0, Math.min(lastPage.value, Math.floor(index / recipesPerPage.value) * recipesPerPage.value))
}
function movePage(direction: number) {
    setPage(page.value + direction * recipesPerPage.value)
}
watch(() => props.bookId, () => { void loadBook() }, {immediate: true})
watch(recipesPerPage, () => setPage(page.value))

/** Load a route's book; obsolete responses cannot append into the next book. */
async function loadBook() {
    const revision = ++bookRevision
    const api = new ApiApi()
    const bookId = Number(props.bookId)
    book.value = {} as RecipeBook
    entries.value = []
    recipes.value = []
    manualItems.value = 0
    filterItems.value = 0
    page.value = 0
    loadingEntries.value = false
    loading.value = true
    if (!Number.isInteger(bookId) || bookId <= 0) {
        loading.value = false
        return
    }
    try {
        const result = await api.apiRecipeBookRetrieve({id: bookId})
        if (revision !== bookRevision) return
        book.value = result
        await recLoadEntries(1, revision, bookId)
    } catch (err) {
        if (revision === bookRevision) useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    } finally {
        if (revision === bookRevision) loading.value = false
    }
}

async function recLoadEntries(pageNumber: number, revision = bookRevision, bookId = Number(props.bookId)): Promise<void> {
    const api = new ApiApi()
    loadingEntries.value = true
    try {
        const result = await api.apiRecipeBookEntryList({book: bookId, page: pageNumber, pageSize: 50})
        if (revision !== bookRevision) return
        entries.value.push(...result.results)
        recipes.value.push(...result.results.map(entry => entry.recipeContent))
        manualItems.value = result.count
        if (result.next) await recLoadEntries(pageNumber + 1, revision, bookId)
        else if (book.value.filter) await recLoadFilter(book.value.filter.id, 1, revision)
        else loadingEntries.value = false
    } catch (err) {
        if (revision !== bookRevision) return
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        loadingEntries.value = false
    }
}

async function recLoadFilter(filterId: number, pageNumber: number, revision = bookRevision): Promise<void> {
    const api = new ApiApi()
    try {
        const result = await api.apiRecipeList({filter: filterId, page: pageNumber, pageSize: 50})
        if (revision !== bookRevision) return
        const existingIds = new Set(recipes.value.map(recipe => recipe.id))
        recipes.value.push(...result.results.filter(recipe => !existingIds.has(recipe.id)))
        filterItems.value = recipes.value.length - manualItems.value
        if (result.next) await recLoadFilter(filterId, pageNumber + 1, revision)
        else loadingEntries.value = false
    } catch (err) {
        if (revision !== bookRevision) return
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        loadingEntries.value = false
    }
}

</script>

<style scoped></style>
