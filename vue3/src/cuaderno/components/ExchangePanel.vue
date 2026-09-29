<template>
    <v-expansion-panels class="mb-4">
        <v-expansion-panel>
            <v-expansion-panel-title>
                <v-icon icon="fa-solid fa-right-left" class="me-3" />
                Intercambio JSON de Cuaderno
            </v-expansion-panel-title>
            <v-expansion-panel-text>
                <p class="mb-3">
                    Exporta las recetas visibles de este espacio o importa un JSON de Cuaderno con vista previa obligatoria.
                    El importador nativo de Tandoor, situado debajo, sigue disponible para sus otros formatos.
                </p>
                <v-alert type="info" variant="tonal" class="mb-4">
                    El JSON no incluye fotos, archivos ni etiquetas; para conservarlos usa también la exportación ZIP nativa de Tandoor.
                    Los alérgenos, las conversiones personalizadas y los ajustes fiscales no forman parte de este intercambio y deben revisarse aparte.
                </v-alert>

                <div class="d-flex flex-wrap ga-2 mb-4">
                    <v-btn color="primary" variant="tonal" prepend-icon="fa-solid fa-download" min-height="44"
                           :loading="exporting" :disabled="busy" @click="downloadExport">
                        Exportar JSON visible
                    </v-btn>
                </div>

                <v-file-input label="Archivo JSON de Cuaderno" accept="application/json,.json" clearable
                              prepend-icon="fa-solid fa-file-code" hint="Máximo 2 MB y 1000 recetas. No se aceptan URL."
                              persistent-hint :loading="loadingFile" :disabled="operationBusy" @update:model-value="selectFile" />
                <p v-if="fileName" class="text-medium-emphasis mt-1">Archivo cargado: {{ fileName }}</p>

                <template v-if="document">
                    <v-divider class="my-4" />
                    <p class="mb-3"><strong>{{ document.recipes.length }}</strong> recetas preparadas desde {{ fileName }}.</p>

                    <template v-if="isV2">
                        <h3 class="text-subtitle-1 mb-1">Correspondencias del catálogo</h3>
                        <p class="text-body-2 mb-3">
                            Para cada identidad elige crearla o reutilizar una existente. Un nombre coincidente nunca se fusiona automáticamente.
                        </p>

                        <div v-for="item in foods" :key="item.ref" class="mapping-row">
                            <p class="mb-1"><strong>Ingrediente:</strong> {{ item.name }}</p>
                            <v-radio-group v-model="choices.foods[item.ref].mode" inline hide-details :disabled="busy">
                                <v-radio label="Crear nuevo" value="create" />
                                <v-radio label="Reutilizar existente" value="reuse" />
                            </v-radio-group>
                            <v-model-select v-if="choices.foods[item.ref].mode === 'reuse'"
                                            v-model="choices.foods[item.ref].target" model="Food" search-on-load clearable
                                            label="Ingrediente existente" hint="Selecciona la identidad exacta." :disabled="busy" />
                        </div>

                        <div v-for="item in units" :key="item.ref" class="mapping-row">
                            <p class="mb-1"><strong>Unidad:</strong> {{ item.name }}</p>
                            <v-radio-group v-model="choices.units[item.ref].mode" inline hide-details :disabled="busy">
                                <v-radio label="Crear nueva" value="create" />
                                <v-radio label="Reutilizar existente" value="reuse" />
                            </v-radio-group>
                            <v-model-select v-if="choices.units[item.ref].mode === 'reuse'"
                                            v-model="choices.units[item.ref].target" model="Unit" search-on-load clearable
                                            label="Unidad existente" hint="Debe tener la misma definición que la unidad importada." :disabled="busy" />
                        </div>

                        <div v-for="item in packages" :key="item.ref" class="mapping-row">
                            <p class="mb-1"><strong>Formato:</strong> {{ item.label }}</p>
                            <v-radio-group v-model="choices.packages[item.ref].mode" inline hide-details :disabled="busy">
                                <v-radio label="Crear nuevo" value="create" />
                                <v-radio label="Reutilizar existente" value="reuse" />
                            </v-radio-group>
                            <v-select v-if="choices.packages[item.ref].mode === 'reuse'"
                                      v-model="choices.packages[item.ref].target" :items="packageOptions" item-value="id"
                                      :item-title="packageTitle" label="Formato existente" clearable
                                      hint="Debe coincidir también su contenido y precios." persistent-hint :loading="loadingPackages" :disabled="busy" />
                        </div>
                    </template>

                    <template v-else>
                        <v-textarea v-model="legacyMapping" label="Correspondencias avanzadas (JSON)" rows="4"
                                    hint='Opcional. Ejemplo: {"foods":{"Harina":12},"units":{"kg":3}}'
                                    persistent-hint :disabled="busy" />
                    </template>

                    <div class="d-flex flex-wrap ga-2 mt-4">
                        <v-btn color="primary" prepend-icon="fa-solid fa-eye" min-height="44"
                               :loading="previewing" :disabled="busy || !document" @click="previewImport">
                            Previsualizar
                        </v-btn>
                        <v-btn v-if="previewHash" color="success" prepend-icon="fa-solid fa-file-import" min-height="44"
                               :loading="importing" :disabled="busy || !previewHash" @click="confirmImport">
                            Confirmar importación
                        </v-btn>
                    </div>
                </template>

                <v-alert v-if="message" :type="messageType" variant="tonal" class="mt-4" role="status">
                    {{ message }}
                </v-alert>

                <v-card v-if="previewResult" variant="outlined" class="mt-4">
                    <v-card-title>Vista previa: {{ previewResult.count }} recetas</v-card-title>
                    <v-card-text>
                        <p class="mb-2">No se ha escrito ningún dato.</p>
                        <v-list density="compact">
                            <v-list-item v-for="recipe in previewResult.preview" :key="`${recipe.source}:${recipe.external_id}`"
                                         :title="recipe.name" />
                        </v-list>
                        <v-alert v-for="warning in previewResult.warnings || []" :key="String(warning)"
                                 type="warning" variant="tonal" class="mt-2">{{ warning }}</v-alert>
                    </v-card-text>
                </v-card>
            </v-expansion-panel-text>
        </v-expansion-panel>
    </v-expansion-panels>
</template>

<script setup lang="ts">
import {computed, reactive, ref, watch} from 'vue'
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {exchangeBody, readExchangeFile} from '@/cuaderno/exchangeUi'

type CatalogItem = {ref: string; id?: number; name?: string; label?: string}
type Choice = {mode: 'create' | 'reuse'; target: any}
type Preview = {count: number; preview: Array<Record<string, any>>; writes: number; preview_sha256: string; warnings?: unknown[]}

const document = ref<Record<string, any> | null>(null)
const fileName = ref('')
const legacyMapping = ref('{}')
const previewHash = ref('')
const previewResult = ref<Preview | null>(null)
const message = ref('')
const messageType = ref<'success' | 'error' | 'info'>('info')
const exporting = ref(false)
const previewing = ref(false)
const importing = ref(false)
const loadingFile = ref(false)
const loadingPackages = ref(false)
const packageOptions = ref<any[]>([])
const choices = reactive<Record<'foods' | 'units' | 'packages', Record<string, Choice>>>({foods: {}, units: {}, packages: {}})
let selectionToken = 0

const operationBusy = computed(() => exporting.value || previewing.value || importing.value)
const busy = computed(() => operationBusy.value || loadingFile.value || loadingPackages.value)
const isV2 = computed(() => document.value?.format === 'cuaderno-recipes-v2')
const foods = computed<CatalogItem[]>(() => Array.isArray(document.value?.catalog?.foods) ? document.value!.catalog.foods : [])
const units = computed<CatalogItem[]>(() => Array.isArray(document.value?.catalog?.units) ? document.value!.catalog.units : [])
const packages = computed<CatalogItem[]>(() => Array.isArray(document.value?.catalog?.packages) ? document.value!.catalog.packages : [])

function invalidatePreview() {
    previewHash.value = ''
    previewResult.value = null
}

watch(choices, invalidatePreview, {deep: true})
watch(legacyMapping, invalidatePreview)

function initialiseChoices() {
    for (const kind of ['foods', 'units', 'packages'] as const) {
        choices[kind] = {}
        const items = kind === 'foods' ? foods.value : kind === 'units' ? units.value : packages.value
        for (const item of items) choices[kind][item.ref] = {mode: 'create', target: null}
    }
}

async function selectFile(value: File | File[] | null) {
    const token = ++selectionToken
    const file = Array.isArray(value) ? value[0] : value
    message.value = ''
    invalidatePreview()
    document.value = null
    packageOptions.value = []
    loadingPackages.value = false
    fileName.value = file?.name || ''
    if (!file) {
        loadingFile.value = false
        loadingPackages.value = false
        return
    }
    loadingFile.value = true
    try {
        if (file.size > 2_000_000) throw new Error('El archivo supera 2 MB.')
        const text = await file.text()
        if (token !== selectionToken) return
        document.value = readExchangeFile(text)
        legacyMapping.value = '{}'
        initialiseChoices()
        if (document.value.format === 'cuaderno-recipes-v2') await loadPackages(token)
        if (token !== selectionToken) return
    } catch (error) {
        if (token !== selectionToken) return
        document.value = null
        messageType.value = 'error'
        message.value = error instanceof Error ? error.message : 'No se ha podido leer el archivo JSON.'
    } finally {
        if (token === selectionToken) loadingFile.value = false
    }
}

async function loadPackages(token: number) {
    loadingPackages.value = true
    const response = await cuadernoFetch('/api/cuaderno/packages/')
    if (token !== selectionToken) return
    const {ok, status, data} = await readJson(response)
    if (token !== selectionToken) return
    loadingPackages.value = false
    if (ok && Array.isArray(data)) packageOptions.value = data
    else {
        messageType.value = 'error'
        message.value = apiError(status, data)
    }
}

function packageTitle(item: any) {
    return `${item.food_name} — ${item.label} (${item.quantity} ${item.unit_name})`
}

function mapping(): Record<string, any> {
    if (!isV2.value) {
        const parsed = JSON.parse(legacyMapping.value || '{}')
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('Las correspondencias deben ser un objeto JSON.')
        return parsed
    }
    const result: Record<string, Record<string, number>> = {foods: {}, units: {}, packages: {}}
    for (const kind of ['foods', 'units', 'packages'] as const) {
        for (const [ref, choice] of Object.entries(choices[kind])) {
            if (choice.mode !== 'reuse') continue
            const id = typeof choice.target === 'number' ? choice.target : choice.target?.id
            if (!Number.isSafeInteger(id) || id < 1) throw new Error('Selecciona la identidad existente para cada correspondencia marcada como reutilizar.')
            result[kind][ref] = id
        }
    }
    return result
}

async function previewImport() {
    if (!document.value || previewing.value) return
    message.value = ''
    invalidatePreview()
    try {
        const body = exchangeBody(document.value, mapping())
        previewing.value = true
        const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/exchange/?preview=1', {
            method: 'POST', body: JSON.stringify(body),
        }))
        if (!ok) throw new Error(apiError(status, data))
        previewResult.value = data as Preview
        previewHash.value = String((data as any).preview_sha256 || '')
        if (!previewHash.value) throw new Error('El servidor no devolvió una confirmación de previsualización válida.')
        messageType.value = 'success'
        message.value = 'Vista previa lista. Revisa las recetas antes de confirmar.'
    } catch (error) {
        messageType.value = 'error'
        message.value = error instanceof Error ? error.message : 'No se ha podido previsualizar la importación.'
    } finally {
        previewing.value = false
    }
}

async function confirmImport() {
    if (!document.value || !previewHash.value || importing.value) return
    message.value = ''
    try {
        const body = exchangeBody(document.value, mapping(), previewHash.value)
        importing.value = true
        const {ok, status, data} = await readJson(await cuadernoFetch('/api/cuaderno/exchange/', {
            method: 'POST', body: JSON.stringify(body),
        }))
        if (!ok) throw new Error(apiError(status, data))
        const result = data as any
        messageType.value = 'success'
        message.value = `Importación terminada: ${result.created?.length || 0} creadas, ${result.replayed?.length || 0} ya importadas y ${result.rejected?.length || 0} rechazadas.`
        invalidatePreview()
    } catch (error) {
        messageType.value = 'error'
        message.value = error instanceof Error ? error.message : 'No se ha podido confirmar la importación.'
    } finally {
        importing.value = false
    }
}

async function downloadExport() {
    exporting.value = true
    message.value = ''
    const response = await cuadernoFetch('/api/cuaderno/exchange/')
    if (!response.ok) {
        const {status, data} = await readJson(response)
        messageType.value = 'error'
        message.value = apiError(status, data)
        exporting.value = false
        return
    }
    const url = URL.createObjectURL(await response.blob())
    const link = globalThis.document.createElement('a')
    link.href = url
    link.download = `cuaderno-recetas-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(url)
    messageType.value = 'success'
    message.value = 'Exportación JSON descargada.'
    exporting.value = false
}
</script>

<style scoped>
.mapping-row {
    border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    padding-block: 12px;
}
</style>
