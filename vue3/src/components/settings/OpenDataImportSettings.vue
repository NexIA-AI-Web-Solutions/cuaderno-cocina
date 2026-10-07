<!-- Community data provenance: https://github.com/TandoorRecipes/open-tandoor-data. -->
<template>
    <p class="text-h4">{{ $t('Open_Data_Import') }}</p>
    <v-divider></v-divider>
    <p class="text-subtitle-1">{{ $t('Data_Import_Info') }} <a href="https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/docs/features/import_export.md" target="_blank" rel="noreferrer nofollow">{{ $t('Learn_More') }}</a></p>

    <v-select :items="metadata.versions" :label="$t('Language')" class="mt-4" v-model="requestData.selectedVersion" :loading="loading"></v-select>

    <v-row v-if="requestData.selectedVersion">
        <v-col>
            <v-checkbox :label="$t('Update_Existing_Data')" v-model="requestData.updateExisting" hide-details></v-checkbox>
            <v-checkbox :label="$t('Use_Metric')" v-model="requestData.useMetric" hide-details></v-checkbox>

            <v-table>
                <thead>
                <tr>
                    <th>{{ $t('Import') }}</th>
                    <th>{{ $t('Datatype') }}</th>
                    <th>{{ $t('Number of Objects') }}</th>
                    <th>{{ $t('Imported') }}</th>
                </tr>
                </thead>
                <tbody>
                <tr v-for="d in supportedDatatypes" :key="d">
                    <td>
                        <v-checkbox hide-details density="compact" :loading="loading" v-model="importDatatype[d]"></v-checkbox>
                    </td>
                    <td>{{ $t(d.charAt(0).toUpperCase() + d.slice(1)) }}</td>
                    <td>{{ objectCount(requestData.selectedVersion, d) }}</td>
                    <td>
                        <template v-if="responseDetail(d)">
                            <p v-if="(responseDetail(d)?.totalCreated ?? 0) > 0" ><i class="fas fa-plus-circle"></i> {{ responseDetail(d)?.totalCreated }} {{ $t('Created') }}</p>
                            <p v-if="(responseDetail(d)?.totalUpdated ?? 0) > 0"><i class="fas fa-pencil-alt"></i> {{ responseDetail(d)?.totalUpdated }} {{ $t('Updated') }}</p>
                            <p v-if="(responseDetail(d)?.totalUntouched ?? 0) > 0"><i class="fas fa-forward"></i> {{ responseDetail(d)?.totalUntouched }} {{ $t('Unchanged') }}</p>
                            <p v-if="(responseDetail(d)?.totalErrored ?? 0) > 0"><i class="fas fa-exclamation-circle"></i> {{ responseDetail(d)?.totalErrored }} {{ $t('Error') }}</p>
                        </template>
                    </td>
                </tr>
                </tbody>
            </v-table>
            <v-btn @click="importOpenData()" class="mt-2 float-right" color="success" :loading="loading">{{ $t('Import') }}</v-btn>
        </v-col>
    </v-row>


</template>

<script setup lang="ts">

import {ApiApi, type ImportOpenDataMetaData, type ImportOpenDataRequest, type ImportOpenDataResponse, type ImportOpenDataResponseDetail, type ImportOpenDataVersionMetaData} from "@/openapi";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore.ts";
import {computed, onMounted, ref} from "vue";

const datatypeKeys = ['food', 'unit', 'category', 'property', 'store', 'conversion'] as const
type Datatype = typeof datatypeKeys[number]

let loading = ref(false)
let metadata = ref({} as ImportOpenDataMetaData)
let requestData = ref<ImportOpenDataRequest>({selectedVersion: '', selectedDatatypes: [], useMetric: true, updateExisting: true})
let responseData = ref({} as ImportOpenDataResponse)

let importDatatype = ref<Record<Datatype, boolean>>({
    food: true,
    unit: true,
    category: true,
    property: true,
    store: false,
    conversion: true
})

const supportedDatatypes = computed(() => metadata.value.datatypes?.filter(isDatatype) ?? [])

function isDatatype(value: string): value is Datatype {
    return datatypeKeys.some(key => key === value)
}

function responseDetail(datatype: Datatype): ImportOpenDataResponseDetail | undefined {
    return responseData.value[datatype]
}

function versionMetadata(version: string): ImportOpenDataVersionMetaData | undefined {
    const versions: Record<string, ImportOpenDataVersionMetaData> = {
        base: metadata.value.base, cs: metadata.value.cs, da: metadata.value.da, de: metadata.value.de,
        el: metadata.value.el, en: metadata.value.en, es: metadata.value.es, fr: metadata.value.fr,
        hu: metadata.value.hu, it: metadata.value.it, nb_NO: metadata.value.nbNO, nl: metadata.value.nl,
        pl: metadata.value.pl, pt: metadata.value.pt, pt_BR: metadata.value.ptBR, sk: metadata.value.sk,
        sl: metadata.value.sl, zh_Hans: metadata.value.zhHans,
    }
    return versions[version]
}

function objectCount(version: string, datatype: Datatype): number {
    return versionMetadata(version)?.[datatype] ?? 0
}

onMounted(() => {
    loadMetadata()
})

/**
 * perform request to metadata endpoint to load available versions and their statistics
 */
function loadMetadata() {
    let api = new ApiApi()
    loading.value = true
    api.apiImportOpenDataRetrieve().then(r => {
        metadata.value = r

        let locale = document.querySelector('html')!.getAttribute('lang')
        if (locale != null && metadata.value.versions.includes(locale)) {
            requestData.value.selectedVersion = locale
        }

    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        loading.value = false
    })
}

function importOpenData() {
    let api = new ApiApi()
    loading.value = true

    requestData.value.selectedDatatypes = []
    datatypeKeys.forEach(key => {
        if (importDatatype.value[key]) {
            requestData.value.selectedDatatypes.push(key)
        }
    })

    api.apiImportOpenDataCreate({importOpenData: requestData.value}).then(r => {
        responseData.value = r
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        loading.value = false
    })

}

</script>

<style scoped>

</style>
