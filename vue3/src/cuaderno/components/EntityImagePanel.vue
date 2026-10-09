<template>
    <section class="entity-image-panel mt-4" :aria-label="title">
        <h3 class="text-subtitle-1 mb-2">{{ title }}</h3>
        <v-progress-linear v-if="loading" indeterminate :aria-label="'Cargando ' + title.toLowerCase()" />
        <v-alert v-if="error" type="error" role="alert" class="my-3">{{ error }}</v-alert>
        <p v-if="notice" role="status" class="my-3">{{ notice }}</p>
        <figure v-if="data?.image" class="mb-3">
            <v-img :src="data.image.url" :alt="data.image.caption || title" max-height="220" contain class="rounded" />
            <figcaption class="text-body-2 mt-2">{{ data.image.caption }}</figcaption>
        </figure>
        <p v-else-if="data" class="mb-3">Todavía no hay imagen.</p>
        <v-btn v-if="!data && !loading" variant="text" @click="load">Volver a cargar imagen</v-btn>
        <div v-if="data?.can_edit && allowEdit" class="d-print-none">
            <v-file-input v-model="photoFile" accept="image/jpeg,image/png,image/webp,image/gif" :label="fileLabel" :disabled="busy || loading" />
            <v-text-field v-model="caption" label="Descripción de la imagen" maxlength="240" :disabled="busy || loading" />
            <div class="d-flex flex-wrap ga-2">
                <v-btn color="primary" :disabled="busy || loading || !selectedFile" :loading="busy" min-height="44" @click="upload">{{ data.image ? 'Cambiar imagen' : 'Guardar imagen' }}</v-btn>
                <v-btn v-if="data.image" color="error" variant="text" :disabled="busy || loading" min-height="44" @click="confirmRemove = true">Eliminar imagen</v-btn>
            </div>
            <p class="text-caption mt-2">Imagen opcional JPG, PNG, WebP o GIF sin animación de hasta 5 MiB. El servidor verifica el archivo.</p>
        </div>
        <p v-else-if="data" class="text-body-2">Modo Consulta: puedes ver la imagen. Cocina o Responsable pueden cambiarla.</p>
        <v-dialog v-model="confirmRemove" max-width="440" persistent>
            <v-card title="Eliminar imagen"><v-card-text>Se eliminará esta imagen. Se conservarán los demás datos.</v-card-text><v-card-actions class="flex-wrap"><v-btn :disabled="busy" @click="confirmRemove = false">Cancelar</v-btn><v-btn color="error" :disabled="busy" :loading="busy" @click="remove">Confirmar eliminación</v-btn></v-card-actions></v-card>
        </v-dialog>
    </section>
</template>
<script setup lang="ts">
import {computed, ref, watch} from 'vue'
import {planningRequest, uploadEntityImage, type EntityImageData, type EntityImage} from '@/cuaderno/planningApi'
const props = withDefaults(defineProps<{entityId: number; kind: 'food' | 'template'; title?: string; allowEdit?: boolean; refreshKey?: number}>(), {title: 'Imagen', allowEdit: true, refreshKey: 0})
const emit = defineEmits<{changed: [image: EntityImage | null, revision?: string]; permissions: [canEdit: boolean]}>()
const data = ref<EntityImageData|null>(null), loading = ref(false), busy = ref(false), error = ref(''), notice = ref(''), confirmRemove = ref(false)
const photoFile = ref<File|File[]|null>(null), caption = ref('')
const selectedFile = computed(() => Array.isArray(photoFile.value) ? photoFile.value[0] : photoFile.value)
const fileLabel = computed(() => props.kind === 'food' ? 'Foto del ingrediente (hasta 5 MiB)' : 'Portada del menú (hasta 5 MiB)')
const path = computed(() => `${props.kind === 'food' ? 'foods' : 'planning/templates'}/${props.entityId}/image/`)
let generation = 0
function accept(value: EntityImageData) {data.value = value; emit('changed',value.image,value.revision); emit('permissions',value.can_edit === true)}
async function load() {
    const current = ++generation, requestPath = path.value
    loading.value = true; error.value = ''
    try {const value=await planningRequest<EntityImageData>(requestPath);if(current===generation) {accept(value);caption.value=value.image?.caption || ''}}
    catch(failure) {if(current===generation) error.value=(failure as Error).message}
    finally {if(current===generation) loading.value=false}
}
async function change(action:(requestPath:string)=>Promise<EntityImageData>,message:string) {
    if(busy.value || loading.value || !data.value?.can_edit || !props.allowEdit) return
    const current = generation, requestPath = path.value
    busy.value=true;error.value='';notice.value=''
    try {
        const permission=await planningRequest<EntityImageData>(requestPath)
        if(current!==generation) return
        if(!permission.can_edit || !props.allowEdit) {accept(permission);throw new Error('Tu acceso ha cambiado. La imagen seleccionada se conserva; Cocina o Responsable pueden guardarla.')}
        const saved=await action(requestPath)
        if(current===generation) {accept(saved);photoFile.value=null;caption.value=saved.image?.caption || '';confirmRemove.value=false;notice.value=message}
    } catch(failure) {if(current===generation) error.value=(failure as Error).message}
    finally {if(current===generation) busy.value=false}
}
function upload() {const file=selectedFile.value;if(!file) return;return change(requestPath=>uploadEntityImage(requestPath,file,caption.value),'Imagen guardada.')}
function remove() {return change(requestPath=>planningRequest<EntityImageData>(requestPath,'DELETE'),'Imagen eliminada.')}
watch(() => props.refreshKey, () => {void load()})
watch([() => props.entityId, () => props.kind],() => {data.value=null;photoFile.value=null;caption.value='';notice.value='';busy.value=false;confirmRemove.value=false;void load()}, {immediate:true})
</script>
<style scoped>
.entity-image-panel {min-width:0;overflow-wrap:anywhere;}
.entity-image-panel figure {margin-left:0;margin-right:0;}
</style>
