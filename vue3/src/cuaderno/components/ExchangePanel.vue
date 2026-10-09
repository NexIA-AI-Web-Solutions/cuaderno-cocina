<template>
    <v-expansion-panels class="mb-4">
        <v-expansion-panel>
            <v-expansion-panel-title>
                <v-icon icon="fa-solid fa-right-left" class="me-3" />
                Intercambio JSON de Cuaderno
            </v-expansion-panel-title>
            <v-expansion-panel-text>
                <p class="mb-3">
                    Exporta las recetas visibles de este espacio.
                    <template v-if="!readOnly">También puedes importar un JSON de Cuaderno con vista previa obligatoria; el importador nativo situado debajo admite otros formatos.</template>
                </p>
                <v-alert type="info" variant="tonal" class="mb-4">
                    Las nuevas exportaciones incluyen las conversiones de unidades necesarias para las recetas visibles.
                    Las fotos, archivos y etiquetas se conservan con la exportación ZIP nativa de Cuaderno Cocina;
                    los alérgenos y ajustes fiscales siguen fuera de este intercambio y deben revisarse aparte.
                </v-alert>

                <div class="d-flex flex-wrap ga-2 mb-4">
                    <v-btn color="primary" variant="tonal" prepend-icon="fa-solid fa-download" min-height="44"
                           :loading="exporting" :disabled="busy" @click="downloadExport">
                        Exportar JSON visible
                    </v-btn>
                </div>

                <template v-if="!readOnly">
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
                        <v-alert v-if="isV2WithoutConversions" type="warning" variant="tonal" class="mb-3">
                            Este archivo antiguo no contiene conversiones de unidades. Puedes importarlo, pero revisa después
                            densidades, pesos unitarios y costes que dependan de ellas.
                        </v-alert>

                        <div v-for="item in foods" :key="item.ref" class="mapping-row">
                            <p class="mb-1"><strong>Ingrediente:</strong> {{ item.name }}</p>
                            <v-radio-group :model-value="choiceMode('foods', item.ref)" inline hide-details :disabled="busy"
                                           @update:model-value="value => setChoiceMode('foods', item.ref, value)">
                                <v-radio label="Crear nuevo" value="create" />
                                <v-radio label="Reutilizar existente" value="reuse" />
                            </v-radio-group>
                            <v-model-select v-if="choiceMode('foods', item.ref) === 'reuse'"
                                            :model-value="choiceTarget('foods', item.ref)" model="Food" search-on-load clearable
                                            @update:model-value="value => setChoiceTarget('foods', item.ref, value)"
                                            label="Ingrediente existente" hint="Selecciona la identidad exacta." :disabled="busy" />
                        </div>

                        <div v-for="item in units" :key="item.ref" class="mapping-row">
                            <p class="mb-1"><strong>Unidad:</strong> {{ item.name }}</p>
                            <v-radio-group :model-value="choiceMode('units', item.ref)" inline hide-details :disabled="busy"
                                           @update:model-value="value => setChoiceMode('units', item.ref, value)">
                                <v-radio label="Crear nueva" value="create" />
                                <v-radio label="Reutilizar existente" value="reuse" />
                            </v-radio-group>
                            <v-model-select v-if="choiceMode('units', item.ref) === 'reuse'"
                                            :model-value="choiceTarget('units', item.ref)" model="Unit" search-on-load clearable
                                            @update:model-value="value => setChoiceTarget('units', item.ref, value)"
                                            label="Unidad existente" hint="Debe tener la misma definición que la unidad importada." :disabled="busy" />
                        </div>

                        <div v-for="item in packages" :key="item.ref" class="mapping-row">
                            <p class="mb-1"><strong>Formato:</strong> {{ item.label }}</p>
                            <v-radio-group :model-value="choiceMode('packages', item.ref)" inline hide-details :disabled="busy"
                                           @update:model-value="value => setChoiceMode('packages', item.ref, value)">
                                <v-radio label="Crear nuevo" value="create" />
                                <v-radio label="Reutilizar existente" value="reuse" />
                            </v-radio-group>
                            <v-select v-if="choiceMode('packages', item.ref) === 'reuse'"
                                      :model-value="choiceTarget('packages', item.ref)" :items="packageOptions" item-value="id"
                                      @update:model-value="value => setChoiceTarget('packages', item.ref, value)"
                                      :item-title="packageTitle" label="Formato existente" clearable
                                      hint="Debe coincidir también su contenido y precios." persistent-hint :loading="loadingPackages" :disabled="busy" />
                        </div>

                        <div v-for="item in conversions" :key="item.ref" class="mapping-row">
                            <p class="mb-1"><strong>Conversión:</strong> {{ conversionTitle(item) }}</p>
                            <v-radio-group :model-value="choiceMode('conversions', item.ref)" inline hide-details :disabled="busy"
                                           @update:model-value="value => setChoiceMode('conversions', item.ref, value)">
                                <v-radio label="Crear nueva" value="create" />
                                <v-radio label="Reutilizar existente" value="reuse" />
                            </v-radio-group>
                            <v-model-select v-if="choiceMode('conversions', item.ref) === 'reuse'"
                                            :model-value="choiceTarget('conversions', item.ref)" model="UnitConversion"
                                            search-on-load clearable
                                            @update:model-value="value => setChoiceTarget('conversions', item.ref, value)"
                                            label="Conversión existente"
                                            hint="Debe usar las mismas unidades, alimento y proporción."
                                            persistent-hint :disabled="busy" />
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
                </template>
                <v-alert v-if="message" :type="messageType" variant="tonal" class="mt-4" role="status">
                    {{ message }}
                </v-alert>

            </v-expansion-panel-text>
        </v-expansion-panel>
    </v-expansion-panels>
</template>

<script setup lang="ts">
import {computed, reactive, ref, toRaw, watch} from 'vue'
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {exchangeBody, readExchangeFile} from '@/cuaderno/exchangeUi'

const props = defineProps({readOnly: {type: Boolean, default: false}})

type CatalogItem = {ref: string; id?: number; name?: string; label?: string}
type CatalogConversion = CatalogItem & {
    food_ref: string | null
    base_unit_ref: string
    converted_unit_ref: string
    base_amount: string
    converted_amount: string
}
type ChoiceKind = 'foods' | 'units' | 'packages' | 'conversions'
type ChoiceTarget = {id: number} | number | null | undefined
type Choice = {mode: 'create' | 'reuse'; target: ChoiceTarget}
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
const choices = reactive<Record<ChoiceKind, Record<string, Choice>>>({foods: {}, units: {}, packages: {}, conversions: {}})
let selectionToken = 0

const operationBusy = computed(() => exporting.value || previewing.value || importing.value)
const busy = computed(() => operationBusy.value || loadingFile.value || loadingPackages.value)
const isV2 = computed(() => document.value?.format === 'cuaderno-recipes-v2')
const foods = computed<CatalogItem[]>(() => Array.isArray(document.value?.catalog?.foods) ? document.value!.catalog.foods : [])
const units = computed<CatalogItem[]>(() => Array.isArray(document.value?.catalog?.units) ? document.value!.catalog.units : [])
const packages = computed<CatalogItem[]>(() => Array.isArray(document.value?.catalog?.packages) ? document.value!.catalog.packages : [])
const conversions = computed<CatalogConversion[]>(() => Array.isArray(document.value?.catalog?.conversions) ? document.value!.catalog.conversions : [])
const isV2WithoutConversions = computed(() => isV2.value
    && document.value?.catalog
    && !Object.prototype.hasOwnProperty.call(document.value.catalog, 'conversions'))

function ensureChoice(kind: ChoiceKind, ref: string): Choice {
    const existing = choices[kind][ref]
    if (existing) return existing
    const created: Choice = {mode: 'create', target: null}
    choices[kind][ref] = created
    return created
}

function choiceMode(kind: ChoiceKind, ref: string): Choice['mode'] {
    return ensureChoice(kind, ref).mode
}

function choiceTarget(kind: ChoiceKind, ref: string): ChoiceTarget {
    return ensureChoice(kind, ref).target
}

function setChoiceMode(kind: ChoiceKind, ref: string, value: unknown) {
    ensureChoice(kind, ref).mode = value === 'reuse' ? 'reuse' : 'create'
}

function setChoiceTarget(kind: ChoiceKind, ref: string, value: unknown) {
    ensureChoice(kind, ref).target = typeof value === 'number'
        ? value
        : (typeof value === 'object' && value !== null && 'id' in value && typeof value.id === 'number' ? {id: value.id} : null)
}

function invalidatePreview() {
    previewHash.value = ''
    previewResult.value = null
}

watch(choices, invalidatePreview, {deep: true})
watch(legacyMapping, invalidatePreview)

function initialiseChoices() {
    for (const kind of ['foods', 'units', 'packages', 'conversions'] as const) {
        choices[kind] = {}
        const items = kind === 'foods' ? foods.value
            : kind === 'units' ? units.value
                : kind === 'packages' ? packages.value : conversions.value
        for (const item of items) choices[kind][item.ref] = {mode: 'create', target: null}
    }
}

function validateCatalogShape(value: Record<string, any>) {
    if (value.format !== 'cuaderno-recipes-v2') return
    const catalog = value.catalog
    if (!catalog || Array.isArray(catalog) || typeof catalog !== 'object') {
        throw new Error('El catálogo del archivo está mal formado.')
    }
    for (const kind of ['foods', 'units', 'packages'] as const) {
        if (Object.prototype.hasOwnProperty.call(catalog, kind)
            && (!Array.isArray(catalog[kind])
                || catalog[kind].some((item: unknown) => !item || Array.isArray(item) || typeof item !== 'object'))) {
            throw new Error('El catálogo del archivo está mal formado.')
        }
    }
    if (Object.prototype.hasOwnProperty.call(catalog, 'conversions')
        && (!Array.isArray(catalog.conversions)
            || catalog.conversions.some((item: unknown) => !item || Array.isArray(item) || typeof item !== 'object'))) {
        throw new Error('El catálogo del archivo está mal formado.')
    }
}

async function selectFile(value: File | File[] | null) {
    if (props.readOnly) return
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
        const parsed = readExchangeFile(text)
        validateCatalogShape(parsed)
        document.value = parsed
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

function catalogTitle(items: CatalogItem[], ref: string | null, fallback: string) {
    if (ref === null) return fallback
    const item = items.find(candidate => candidate.ref === ref)
    return item?.name || ref
}

function conversionTitle(item: CatalogConversion) {
    const baseUnit = catalogTitle(units.value, item.base_unit_ref, 'unidad desconocida')
    const convertedUnit = catalogTitle(units.value, item.converted_unit_ref, 'unidad desconocida')
    const scope = catalogTitle(foods.value, item.food_ref, 'conversión general')
    return `${item.base_amount} ${baseUnit} → ${item.converted_amount} ${convertedUnit} · ${scope}`
}

function mapping(): Record<string, any> {
    if (!isV2.value) {
        const parsed = JSON.parse(legacyMapping.value || '{}')
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('Las correspondencias deben ser un objeto JSON.')
        return parsed
    }
    const result: Record<string, Record<string, number>> = {foods: {}, units: {}, packages: {}, conversions: {}}
    for (const kind of ['foods', 'units', 'packages', 'conversions'] as const) {
        for (const [ref, choice] of Object.entries(choices[kind])) {
            if (choice.mode !== 'reuse') continue
            const id = typeof choice.target === 'number' ? choice.target : choice.target?.id
            if (typeof id !== 'number' || !Number.isSafeInteger(id) || id < 1) throw new Error('Selecciona la identidad existente para cada correspondencia marcada como reutilizar.')
            const target = result[kind]
            if (!target) throw new Error('No se ha podido preparar la correspondencia del catálogo.')
            target[ref] = id
        }
    }
    return result
}

async function previewImport() {
    if (props.readOnly) return
    if (!document.value || previewing.value) return
    message.value = ''
    invalidatePreview()
    try {
        const body = exchangeBody(toRaw(document.value), mapping())
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
    if (props.readOnly) return
    if (!document.value || !previewHash.value || importing.value) return
    message.value = ''
    try {
        const body = exchangeBody(toRaw(document.value), mapping(), previewHash.value)
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
