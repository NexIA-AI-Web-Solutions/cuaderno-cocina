<template>
    <p class="text-h6">{{ $t('Export') }}</p>
    <v-divider></v-divider>

    <v-form class="mt-2">
        <v-select :items="exportFormats" :label="$t('Type')" v-model="exportType"></v-select>

        <v-checkbox :label="$t('AllRecipes')" v-model="allRecipes" :disabled="selectedRecipes.length > 0 || selectedFilter != null"></v-checkbox>
        <v-model-select model="Recipe" multiple chips v-model="selectedRecipes" :disabled="allRecipes || selectedFilter != null"></v-model-select>
        <v-model-select model="CustomFilter" v-model="selectedFilter" :disabled="selectedRecipes.length > 0 || allRecipes"></v-model-select>

        <v-btn @click="doExport()" :loading="loading" :disabled="loading || selectedRecipes.length == 0 && selectedFilter == null && !allRecipes">{{ $t('Export') }}</v-btn>

        <v-alert v-if="pollError" type="error" role="alert" class="mt-3">{{ pollError }}<v-btn variant="text" min-height="44" :disabled="loading" @click="recRefreshExportLog">Reintentar estado</v-btn></v-alert>
        <template v-if="exportLog.id">
            <v-divider class="mt-4 mb-4"></v-divider>
            <h4>{{ $t('Export') }} #{{ exportLog.id }}</h4>
            <p>
                {{ $t('Recipes') }}: {{ exportLog.exportedRecipes }}
            </p>

            <v-btn color="success" :href="useDjangoUrls().getDjangoUrl(`export-file/${exportLog.id!}`)" class="mt-2" :disabled="exportLog.running">{{ $t('Download') }}</v-btn>

            <v-textarea :label="$t('Messages')" auto-grow readonly max-rows="20" v-model="exportLog.msg" class="mt-2"></v-textarea>

        </template>
    </v-form>
</template>

<script setup lang="ts">

import {computed, onBeforeUnmount, ref} from "vue";
import {INTEGRATIONS} from "@/utils/integration_utils.ts";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {ApiApi, CustomFilter, ExportLog, Recipe} from "@/openapi";
import {useDjangoUrls} from "@/composables/useDjangoUrls.ts";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore.ts";
import VModelSelect from "@/components/inputs/VModelSelect.vue";

const exportType = ref('DEFAULT')
const allRecipes = ref(false)
const selectedRecipes = ref([] as Recipe[])
const selectedFilter = ref<null|CustomFilter>(null)

const exportLog = ref({} as ExportLog)
const loading = ref(false)
const pollError = ref('')
let pollTimer: ReturnType<typeof setTimeout> | null = null
let mounted = true
let generation = 0
onBeforeUnmount(() => { mounted = false; generation++; if (pollTimer !== null) clearTimeout(pollTimer) })

/**
 * show export option for all types that have export marked as true in integration list
 */
const exportFormats = computed(() => {
    const formats: Array<{title: string, value: string, props: {subtitle: string}}> = []

    INTEGRATIONS.forEach(integration => {
        if (integration.export) {
            formats.push({title: integration.name, value: integration.id, props: {subtitle: integration.description}})
        }
    })

    return formats
})

function doExport() {
    if (loading.value) return
    generation++; if (pollTimer !== null) clearTimeout(pollTimer)
    pollError.value = ''
    let api = new ApiApi()
    exportLog.value = {} as ExportLog
    loading.value = true

    api.apiExportCreate({exportRequest: {all: allRecipes.value, type: exportType.value, recipes: selectedRecipes.value, customFilter: selectedFilter.value}}).then(r => {
        exportLog.value = r
        recRefreshExportLog()
    }).catch(err => {
        loading.value = false
        useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
    }).finally(() => {

    })
}

async function recRefreshExportLog() {
    if (!mounted || !exportLog.value.id) return
    const current = generation
    if (pollTimer !== null) clearTimeout(pollTimer)
    loading.value = true
    pollError.value = ''
    try {
        const r = await new ApiApi().apiExportLogRetrieve({id: exportLog.value.id!})
        if (!mounted || current !== generation) return
        exportLog.value = r
        if (r.running) pollTimer = setTimeout(() => { void recRefreshExportLog() }, 1000)
        else loading.value = false
    } catch (err) {
        if (!mounted || current !== generation) return
        loading.value = false
        pollError.value = 'No se pudo consultar el estado. La exportación se conserva; puedes reintentar.'
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }
}

</script>


<style scoped>

</style>
