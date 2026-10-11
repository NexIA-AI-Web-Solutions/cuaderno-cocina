<template>
    <v-container class="books-page">
        <h1 class="text-h4 mb-2">Libros de recetas</h1><p class="mb-4">Agrupa tus recetas en libros para consultarlas y compartir una colección.</p>
        <v-progress-linear v-if="loading" indeterminate aria-label="Cargando libros de recetas" class="mb-3" />
        <v-alert v-if="loadError" type="error" role="alert" class="mb-3">{{ loadError }} <v-btn variant="text" :disabled="loading" @click="loadBooks">Reintentar carga</v-btn></v-alert>
        <v-row>
            <v-col cols="12" md="6" offset-md="3">
                <v-text-field v-model="bookQuery" :label="$t('Search')" clearable>
                    <template #append>
                        <v-btn color="create" aria-label="Crear libro de recetas" min-height="44" @click="bookCreateOpen = true">Crear libro</v-btn>
                    </template>
                </v-text-field>
            </v-col>
        </v-row>
        <p v-if="!loading && !loadError && !books.length" class="my-4">Todavía no hay libros de recetas. <v-btn variant="tonal" @click="bookCreateOpen = true">Crear el primer libro</v-btn></p>
        <p v-else-if="!loading && books.length && !visibleBooks.length" role="status" class="my-4">No hay libros que coincidan con «{{ bookQuery }}». <v-btn variant="text" @click="bookQuery = ''">Limpiar búsqueda</v-btn></p>
        <v-btn variant="text" :disabled="loading" @click="loadBooks">Volver a cargar libros</v-btn>
        <model-edit-dialog v-model="bookCreateOpen" model="RecipeBook" @create="(arg: RecipeBook) => {books.push(arg)}" />
        <v-row>
            <v-col cols="12" md="3" v-for="b in visibleBooks" :key="b.id">
                <v-card>
                    <v-card-title>
                        <v-icon icon="$books" size="small"></v-icon>
                        {{ b.name }}
                    </v-card-title>
                    <v-card-subtitle>{{ b.createdBy.displayName }}</v-card-subtitle>
                    <v-card-text>
                        {{ b.description }}
                    </v-card-text>
                    <v-card-actions>
                        <v-btn>
                            {{ $t('Edit') }}
                            <model-edit-dialog model="RecipeBook" :item="b"
                                               @delete="(arg: RecipeBook) => { books.splice(books.findIndex((value: RecipeBook) => value.id == arg.id!),1)}"></model-edit-dialog>
                        </v-btn>
                        <v-btn :to="{name: 'BookViewPage', params: {bookId: b.id}}">
                            {{ $t('View') }}
                        </v-btn>
                    </v-card-actions>
                </v-card>
            </v-col>
        </v-row>
    </v-container>
</template>

<script setup lang="ts">


import {computed, onMounted, ref} from "vue";
import {ApiApi, RecipeBook, RecipeBookEntry} from "@/openapi";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";

const loading = ref(false), loadError = ref(''), bookCreateOpen = ref(false)

const viewingBook = ref<null | RecipeBook>(null)
const viewingBookEntries = ref([] as RecipeBookEntry[])

const books = ref([] as RecipeBook[])
const bookQuery = ref<string | null>('')
const visibleBooks = computed(() => {
    const query = (bookQuery.value ?? '').trim().toLocaleLowerCase()
    return query ? books.value.filter(book => book.name.toLocaleLowerCase().includes(query)) : books.value
})

onMounted(() => {
    loadBooks()
})

async function loadBooks() {
    if (loading.value) return
    const api = new ApiApi()
    loading.value = true; loadError.value = ''
    try {
        const loaded: RecipeBook[] = []
        let page = 1
        while (true) {
            const result = await api.apiRecipeBookList({page})
            loaded.push(...result.results)
            if (!result.next) break
            page++
        }
        books.value = loaded
    } catch (err) {
        loadError.value = 'No se han podido cargar los libros. Conservamos la colección anterior; reintenta la carga.'
    } finally {
        loading.value = false
    }
}

function loadBookEntries(recipeBook : RecipeBook){
    if (loading.value) return
    const api = new ApiApi()
    loading.value = true; loadError.value = ''
    api.apiRecipeBookEntryList({})
}

</script>

<style scoped>.books-page :deep(.v-card-title){white-space:normal;overflow-wrap:anywhere}.books-page :deep(.v-field__append-inner),.books-page :deep(.v-input__append){flex-wrap:wrap}</style>
