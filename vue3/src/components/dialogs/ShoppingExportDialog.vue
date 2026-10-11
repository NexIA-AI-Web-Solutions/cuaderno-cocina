<template>

    <v-dialog v-model="dialog" :activator="props.activator" style="max-width: 75vw;">
        <v-card>

            <v-closable-card-title :title="$t('Export')" v-model="dialog"></v-closable-card-title>
            <v-card-text>
                <v-row>
                    <v-col>

                        <v-btn-toggle role="group" aria-label="Formato de exportación de la compra" border divided v-model="mode">
                            <v-btn value="md_list" aria-label="Lista Markdown" min-height="44"><i class="fa-solid fa-list-check"></i></v-btn>
                            <v-btn value="md_table" aria-label="Tabla Markdown" min-height="44"><i class="fa-solid fa-table-cells"></i></v-btn>
                            <v-btn value="csv" aria-label="Archivo CSV" min-height="44"><i class="fa-solid fa-file-csv"></i></v-btn>
                        </v-btn-toggle>
                    </v-col>
                </v-row>

                <v-row>
                    <v-col>
                        <v-text-field :label="$t('csv_delim_label')" :hint="$t('csv_delim_help')" persistent-hint
                                      v-model="useUserPreferenceStore().userSettings.csvDelim"></v-text-field>

                    </v-col>
                    <v-col>
                        <v-text-field :label="$t('csv_prefix_label')" :hint="$t('csv_prefix_help')" persistent-hint
                                      v-model="useUserPreferenceStore().userSettings.csvPrefix"></v-text-field>
                    </v-col>
                </v-row>
                <v-row>
                    <v-col>
                        <v-textarea label="Vista previa de la exportación" :model-value="exportText" auto-grow max-rows="25" readonly>

                        </v-textarea>
                    </v-col>
                </v-row>
                <btn-copy class="float-right" :copy-value="exportText"></btn-copy>
            </v-card-text>
            <v-card-actions>
                <v-btn @click="downloadExport()" prepend-icon="fa-solid fa-download">{{ $t('Download') }}</v-btn>
                <v-btn @click="copy(exportText)" prepend-icon="$copy">{{ $t('Copy') }}</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>

</template>

<script setup lang="ts">

import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import {computed, PropType, ref, shallowRef} from "vue";
import {useShoppingStore} from "@/stores/ShoppingStore.ts";
import {isEntryVisible, isShoppingCategoryVisible, isShoppingListFoodVisible} from "@/utils/logic_utils.ts";
import {useI18n} from "vue-i18n";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";
import {ShoppingListEntry} from "@/openapi";
import BtnCopy from "@/components/buttons/BtnCopy.vue";
import {useClipboard} from "@vueuse/core";
import {EditorSupportedModels, getGenericModelFromString} from "@/types/Models.ts";

const {t} = useI18n()
const {copy} = useClipboard()

const props = defineProps({
    activator: {default: 'parent'},
})

const dialog = defineModel<boolean>()
const mode = ref<'md_list' | 'md_table' | 'csv'>('md_list')

/**
 * shorthand for csvDelim user preference
 */
const csvDelim = computed(() => {
    return useUserPreferenceStore().userSettings.csvDelim || ';'
})

/**
 * compute the export text
 */
const exportText = computed(() => {
    let textArray: string[] = []

    textArray.push(formatHeader())

    useShoppingStore().entriesByGroup.forEach(category => {
        if (isShoppingCategoryVisible(category)) {
            if (category.name === useShoppingStore().UNDEFINED_CATEGORY) {
                textArray.push(formatCategory(t('NoCategory')))
            } else {
                textArray.push(formatCategory(category.name))
            }

            category.foods.forEach(food => {
                if (isShoppingListFoodVisible(food, useUserPreferenceStore().deviceSettings)) {
                    food.entries.forEach(entry => {
                        if (isEntryVisible(entry, useUserPreferenceStore().deviceSettings)) {
                            textArray.push(formatEntry(entry))
                        }
                    })
                }
            })
        }
    })

    // delete first two empty lines in md list
    if (mode.value == 'md_list') {
        textArray.splice(0, 2)
    }

    return textArray.join('\n')
})

/**
 * create the header for the exported list depending on the mode
 */
function csvField(value: unknown): string {
    const text = String(value ?? '')
    return text.includes(csvDelim.value) || /["\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function formatHeader() {
    if (mode.value == 'md_list') {
        return ''
    } else if (mode.value == 'md_table') {
        return `|${t('Amount')}|${t('Unit')}|${t('Food')}|\n|-|-|-|`
    } else if (mode.value == 'csv') {
        return [t('Amount'), t('Unit'), t('Food')].map(csvField).join(csvDelim.value)
    }
    return ''
}

/**
 * format category lines depending on the mode
 * @param categoryName name of the category
 */
function formatCategory(categoryName: string) {
    if (mode.value == 'md_list') {
        return `\n${categoryName}`
    } else if (mode.value == 'md_table') {
        return `|${categoryName}|`
    } else if (mode.value == 'csv') {
        return [categoryName, '', ''].map(csvField).join(csvDelim.value)
    }
    return ''
}

/**
 * format the shopping list entry according to the selected mode
 * @param entry
 */
function formatEntry(entry: ShoppingListEntry) {
    if (mode.value == 'md_list') {
        return `${useUserPreferenceStore().userSettings.csvPrefix} ${entry.amount} ${(entry.unit) ? entry.unit.name : ''} ${entry.food?.name}`
    } else if (mode.value == 'md_table') {
        return `|${entry.amount}|${(entry.unit) ? entry.unit.name : ''}|${entry.food?.name}|`
    } else if (mode.value == 'csv') {
        return [entry.amount, entry.unit?.name || '', entry.food?.name || ''].map(csvField).join(csvDelim.value)
    }
    return ''
}

/**
 * encode the exportText into a URI and trigger browser to download the export as a file
 */
function downloadExport() {
    const url = URL.createObjectURL(new Blob([exportText.value], {type: mode.value === 'csv' ? 'text/csv;charset=utf-8' : 'text/markdown;charset=utf-8'}))
    const link = document.createElement('a')
    link.href = url
    link.download = `${t('Shopping_list')}.${mode.value === 'csv' ? 'csv' : 'md'}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)

}

</script>

<style scoped>

</style>