<template>
    <v-card class="mt-3 recipe-extras" :loading="loading">
        <v-card-title class="d-flex flex-wrap align-center ga-2">
            <h2 class="text-h6">Fotos, variantes y dietas</h2>
            <v-spacer />
            <v-btn v-if="extras" :prepend-icon="extras.is_favorite ? 'fa-solid fa-heart' : 'fa-regular fa-heart'"
                   :aria-pressed="extras.is_favorite" :disabled="busy" variant="tonal" color="primary" min-height="44" @click="toggleFavorite">
                {{ extras.is_favorite ? 'En mis favoritas' : 'Guardar en favoritas' }}
            </v-btn>
        </v-card-title>
        <v-card-text>
            <v-alert v-if="error" type="error" variant="tonal" role="alert" class="mb-3">{{ error }}</v-alert>
            <p v-if="notice" role="status" class="mb-3">{{ notice }}</p>
            <v-btn v-if="!extras && !loading" variant="text" @click="load">Volver a cargar</v-btn>
            <template v-if="extras">
                <p class="text-body-2 mb-3">Las favoritas son personales. Las fotos y declaraciones pertenecen a esta receta y conservan sus permisos.</p>
                <v-row v-if="extras.gallery.length">
                    <v-col v-for="photo in extras.gallery" :key="photo.id" cols="12" sm="6" md="4">
                        <figure>
                            <v-img :src="photo.url" :alt="photo.caption || 'Foto de la receta'" height="200" cover class="rounded" />
                            <figcaption class="mt-2">{{ photo.caption }}</figcaption>
                            <v-btn v-if="extras.can_edit" variant="text" color="error" :disabled="busy" min-height="44"
                                   :aria-label="'Eliminar foto: ' + (photo.caption || 'sin descripción')" @click="deletePhoto = photo.id">Eliminar foto</v-btn>
                        </figure>
                    </v-col>
                </v-row>
                <p v-else class="mb-3">Todavía no hay fotos adicionales.</p>
                <div v-if="extras.can_edit" class="d-print-none mt-3">
                    <v-file-input v-model="photoFile" accept="image/jpeg,image/png,image/webp,image/gif" label="Añadir foto (hasta 5 MiB)" :disabled="busy || extras.gallery.length >= 20" />
                    <v-text-field v-model="caption" label="Descripción de la foto" maxlength="240" :disabled="busy" />
                    <v-btn variant="tonal" :disabled="busy || !selectedFile || extras.gallery.length >= 20" @click="upload">Añadir foto</v-btn>
                    <p class="text-caption mt-2">Hasta 20 imágenes fijas por receta, sin animación. El servidor comprueba el formato real y el tamaño.</p>
                </div>
                <v-divider class="my-5" />
                <h3 class="text-subtitle-1 mb-2">Variantes vinculadas</h3>
                <p v-if="extras.variant_of">Receta de origen: <router-link :to="{name: 'RecipeViewPage', params: {id: extras.variant_of.id}}">{{ extras.variant_of.name }}</router-link></p>
                <ul v-if="extras.variants.length" class="ps-5"><li v-for="variant in extras.variants" :key="variant.id"><router-link :to="{name: 'RecipeViewPage', params: {id: variant.id}}">{{ variant.name }}</router-link></li></ul>
                <p v-if="extras.variants_truncated" class="text-body-2 mt-2">Se muestran las primeras 100 variantes a las que tienes acceso.</p>
                <p v-if="!extras.variant_of && !extras.variants.length">Sin variantes vinculadas.</p>
                <p v-if="extras.can_edit" class="text-body-2 mt-2">En el menú de la receta, «Crear variante vinculada» duplica su contenido y conserva el enlace con el original.</p>
                <v-divider class="my-5" />
                <h3 class="text-subtitle-1 mb-2">Declaraciones dietéticas</h3>
                <p class="mb-4">Son declaraciones manuales de la cocina, no una evaluación clínica. «No declarado» no significa apto. Revisa ingredientes y preparación antes de decidir.</p>
                <v-alert v-if="dietConflict" type="warning" role="alert" class="mb-3">Otra persona ha cambiado las declaraciones. Tus borradores se conservan: revísalos antes de «Descartar cambios y actualizar». No se guardarán sobre la versión nueva.</v-alert>
                <v-row v-for="diet in drafts" :key="diet.slug" align="center" class="diet-row">
                    <v-col cols="12" sm="3"><strong>{{ diet.label }}</strong></v-col>
                    <v-col cols="12" sm="4">
                        <v-select v-if="extras.can_edit" v-model="diet.status" :items="statuses" :label="'Declaración: ' + diet.label" item-title="label" item-value="value" :disabled="busy" hide-details />
                        <v-chip v-else :color="dietPresentation(diet.status).color" variant="tonal">{{ dietPresentation(diet.status).label }}</v-chip>
                    </v-col>
                    <v-col cols="12" sm="5"><v-text-field v-if="extras.can_edit" v-model="diet.note" :label="'Nota: ' + diet.label" maxlength="500" :disabled="busy" hide-details /><p v-else>{{ diet.note || 'Sin notas' }}</p></v-col>
                </v-row>
                <div v-if="extras.can_edit" class="d-flex flex-wrap ga-2 mt-4 d-print-none">
                    <v-btn color="primary" :loading="busy" :disabled="busy || dietConflict" min-height="44" @click="saveDiets">Guardar declaraciones</v-btn>
                    <v-btn variant="text" :disabled="busy" min-height="44" @click="load">Descartar cambios y actualizar</v-btn>
                </div>
                <p v-else class="mt-3">Tu acceso permite consultar esta receta y gestionar tus favoritas personales.</p>
            </template>
        </v-card-text>
        <v-dialog :model-value="deletePhoto !== null" max-width="440" @update:model-value="value => { if (!value) deletePhoto = null }">
            <v-card title="Eliminar foto"><v-card-text>Se eliminará esta foto adicional de la receta.</v-card-text><v-card-actions><v-btn :disabled="busy" @click="deletePhoto = null">Cancelar</v-btn><v-btn color="error" :loading="busy" @click="removePhoto">Eliminar foto</v-btn></v-card-actions></v-card>
        </v-dialog>
    </v-card>
</template>

<script setup lang="ts">
import {computed, ref, watch} from 'vue'
import {planningRequest, uploadRecipeGallery, type RecipeExtras, type DietDeclaration} from '@/cuaderno/planningApi'
import {dietPresentation} from '@/cuaderno/planningUi.mjs'
const props = defineProps<{recipeId: number}>()
const emit = defineEmits<{permissions: [canEdit: boolean]}>()
const extras = ref<RecipeExtras | null>(null), drafts = ref<DietDeclaration[]>([])
const draftRevision = ref(''), draftBaseline = ref(''), dietConflict = ref(false)
function dietSignature(diets: DietDeclaration[]) {return JSON.stringify(diets.map(({slug, status, note}) => ({slug, status, note})).sort((a, b) => a.slug.localeCompare(b.slug)))}
const loading = ref(false), busy = ref(false), error = ref(''), notice = ref('')
const photoFile = ref<File | File[] | null>(null), caption = ref(''), deletePhoto = ref<number | null>(null)
const selectedFile = computed(() => Array.isArray(photoFile.value) ? photoFile.value[0] : photoFile.value)
const statuses = [{value: 'unknown', label: 'No declarado'}, {value: 'suitable', label: 'Apto · declaración manual'}, {value: 'unsuitable', label: 'No apto · declaración manual'}]
let generation = 0
function accept(value: RecipeExtras, replaceDrafts = true) {
    extras.value = value; emit('permissions', value.can_edit === true)
    const signature = dietSignature(value.diets)
    if (replaceDrafts) {
        drafts.value = value.diets.map(diet => ({...diet})); draftBaseline.value = signature
        draftRevision.value = value.revision; dietConflict.value = false
    } else if (!dietConflict.value && signature === draftBaseline.value) {
        // A gallery-only change may advance the revision without rebasing edited declarations.
        draftRevision.value = value.revision
    } else dietConflict.value = true
}
async function load() {
    const current = ++generation; loading.value = true; error.value = ''; notice.value = ''
    try {const value = await planningRequest<RecipeExtras>(`recipes/${props.recipeId}/extras/`); if (current === generation) accept(value)}
    catch (failure) {if (current === generation) error.value = (failure as Error).message}
    finally {if (current === generation) loading.value = false}
}
async function mutate(action: () => Promise<void>, message: string) {
    if (busy.value) return
    busy.value = true; error.value = ''; notice.value = ''
    try {await action(); notice.value = message} catch (failure) {error.value = (failure as Error).message} finally {busy.value = false}
}
function toggleFavorite() {
    if (!extras.value) return
    const favorite = !extras.value.is_favorite
    return mutate(async () => {const result = await planningRequest<{is_favorite: boolean}>(`recipes/${props.recipeId}/favorite/`, 'PUT', {favorite}); if (extras.value) extras.value.is_favorite = result.is_favorite}, favorite ? 'Guardada en tus favoritas.' : 'Retirada de tus favoritas.')
}
function saveDiets() {
    if (!extras.value?.can_edit || dietConflict.value) return
    const revision = draftRevision.value
    return mutate(async () => accept(await planningRequest<RecipeExtras>(`recipes/${props.recipeId}/extras/`, 'PUT', {revision, diets: drafts.value.map(({slug, status, note}) => ({slug, status, note}))})), 'Declaraciones guardadas.')
}
function upload() {
    const file = selectedFile.value
    if (!file || !extras.value?.can_edit) return
    return mutate(async () => {accept(await uploadRecipeGallery(props.recipeId, file, caption.value), false); photoFile.value = null; caption.value = ''}, 'Foto añadida.')
}
function removePhoto() {
    if (!extras.value?.can_edit || deletePhoto.value === null) return
    const id = deletePhoto.value
    return mutate(async () => {accept(await planningRequest<RecipeExtras>(`recipes/${props.recipeId}/gallery/${id}/`, 'DELETE'), false); deletePhoto.value = null}, 'Foto eliminada.')
}
watch(() => props.recipeId, () => {extras.value = null; emit('permissions', false); photoFile.value = null; caption.value = ''; void load()}, {immediate: true})
</script>

<style scoped>
.recipe-extras :deep(.v-card-title) {white-space: normal;}
.diet-row + .diet-row {border-top: 1px solid rgba(var(--v-theme-on-surface), .12); margin-top: 8px;}
figure {margin: 0;}
</style>
