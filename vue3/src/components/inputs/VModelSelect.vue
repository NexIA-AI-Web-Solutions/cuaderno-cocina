<template>

    <v-autocomplete
        :ref="`ref_${props.id}`"
        v-model="autoselectValue"
        v-model:search="search"
        autocomplete="suppress"
        no-filter
        :items="items"
        :item-title="itemLabelAttribute"
        item-value="id"
        :label="label"
        :hint="props.hint"
        :hide-details="props.hideDetails"
        :density="props.density"
        :clearable="props.clearable"
        :disabled="props.disabled"
        :chips="props.chips"
        :closable-chips="props.chips"
        :multiple="props.multiple"
        :placeholder="props.placeholder"
        :loading="loading"
        return-object
        @keydown.enter.exact="createItem(search, false); console.log('triggered enter keydown')"
        @keydown.shift.enter="createItem(search, true); console.log('triggered shift enter keydown')"
        @keydown.shift.e.prevent="editDialog = true"
        @blur="hasFocus = false"
        @focus="hasFocus = true; "
    >
        <template #prepend v-if="$slots.prepend">
            <slot name="prepend"></slot>
        </template>

        <template v-slot:chip="{ props, item }" v-if="props.chips">
            <v-chip
                v-bind="props"
                :text="item.title"
                :prepend-avatar="(modelClass.model.name == 'Recipe') ? (item.raw.image ?? undefined) : undefined"
            ></v-chip>
        </template>

        <template #no-data>
            <v-list-item v-if="hasLoadedOnce">
                {{ $t('No_Results') }}
            </v-list-item>
        </template>

        <template v-slot:item="{ props, item }">
            <v-list-item v-if="item.raw.id == undefined"
                         :title="item.title"
                         @click.exact="createItem(search, false); console.log('triggered click ITEM')"
                         @click.shift="createItem(search, true); console.log('triggered click ITEM SHIFT')"
            >
                <template #append>
                    <v-icon icon="$create" color="success">

                    </v-icon>
                </template>
            </v-list-item>
            <!-- normal items -> normal rendering -->
            <v-list-item v-if="(item.raw.id ?? 0) > 0"
                         v-bind="props"
                         :title="item.title"
            >
                <template #prepend v-if="modelClass.model.name == 'Recipe'">
                    <v-avatar :image="item.raw.image" v-if="item.raw.image"></v-avatar>
                    <v-avatar image="../../assets/recipe_no_image.svg" v-else></v-avatar>
                </template>


            </v-list-item>
            <!-- render special info item last -->
            <v-list-item v-if="item.raw.id == -1"
                         size="small"
                         density="compact"
                         disabled
                         v-bind="props"
                         :title="item.title"
            >
            </v-list-item>
        </template>

        <template #menu-footer v-if="!mobile && (!props.multiple || props.create)">
            <v-list-item>
                <span v-if="!props.multiple">
                    <v-chip size="x-small" class="mr-1" label><i class="fas fa-arrow-up"></i></v-chip>
                    <v-chip size="x-small" class="mr-1" label>E</v-chip>
                    <span>{{ $t('Editor') }}</span>
                </span>
                <span v-if="props.create" :class="{'text-disabled': !showCreate || loading }">
                    <v-chip size="x-small" class="mr-1" label><i class="fas fa-level-down-alt fa-rotate-90"></i></v-chip>
                    <span class="mr-4">{{ $t('Create') }}</span>

                    <template v-if="!props.multiple">
                        <v-chip size="x-small" class="mr-1" label><i class="fas fa-arrow-up"></i></v-chip>
                        <v-chip size="x-small" class="mr-1" label><i class="fas fa-level-down-alt fa-rotate-90"></i></v-chip>
                        <span>{{ $t('Create') }} & {{ $t('Edit') }}</span>
                    </template>
                </span>
            </v-list-item>
        </template>

        <template #append v-if="$slots.append">
            <slot name="append">

            </slot>
        </template>

    </v-autocomplete>

    <model-edit-dialog :model="props.model" v-model="editDialog" :item-id="editingItemId" @save="handleModelEditorUpdate" @create="handleModelEditorCreate"></model-edit-dialog>
</template>

<script setup lang="ts">

import {computed, nextTick, onBeforeMount, onMounted, PropType, ref, watch} from "vue";
import {useDebounceFn} from "@vueuse/core";
import {EditorSupportedModels, GenericModel, getGenericModelFromString} from "@/types/Models.ts";
import {ErrorMessageType, PreparedMessage, useMessageStore} from "@/stores/MessageStore.ts";
import {useI18n} from "vue-i18n";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";
import {useDisplay} from "vuetify";

const {t} = useI18n()
const {mobile} = useDisplay()
type Density = 'default' | 'comfortable' | 'compact'
type ModelOption = {id?: number; name?: string | null; image?: string | null}

const emit = defineEmits(['update:modelValue', 'create'])

const props = defineProps({
    // custom logic
    model: {type: String as PropType<EditorSupportedModels>, required: true},
    id: {type: String, required: false, default: Math.floor(Math.random() * 10000).toString()},
    create: {type: Boolean, default: false},
    searchOnLoad: {type: Boolean, default: false},
    limit: {type: Number, default: 25},

    // default props
    label: {type: String, default: ''},
    hint: {type: String, default: ''},
    hideDetails: {type: Boolean, default: false},
    density: {type: String as PropType<Density | undefined>},
    clearable: {type: Boolean, default: false},
    disabled: {type: Boolean, default: false},
    returnObject: {type: Boolean, default: true},
    chips: {type: Boolean, default: false},
    multiple: {type: Boolean, default: false},
    placeholder: {type: String, default: undefined},

    // model
    modelValue: {type: [Object, Array, Number] as PropType<ModelOption | ModelOption[] | number | number[] | undefined | null>, default: undefined},
})


const autoselectValue = ref<ModelOption | ModelOption[] | undefined | null>(undefined)

const modelClass = ref({} as GenericModel)
const loading = ref(false)
const hasFocus = ref(false)
const hasLoadedOnce = ref(false)
const editDialog = ref(false)
const hasMoreItems = ref(false)
const lastAddedItem = ref<ModelOption | undefined>(undefined)

const items = ref<ModelOption[]>([])

const search = ref<string | undefined>(undefined)
let searchRevision = 0
let selectionRevision = 0

/**
 * determine if the user should be able to create a new item based on create prop and if the item is already present
 */
const showCreate = computed(() => {
    const existingNames = items.value.filter(item => item.id != undefined).map(item => optionLabel(item).toLowerCase())

    if (Array.isArray(autoselectValue.value)) {
        existingNames.concat(autoselectValue.value.map(item => optionLabel(item).toLowerCase()))
    } else if (autoselectValue.value != undefined) {
        existingNames.push(optionLabel(autoselectValue.value).toLowerCase())
    }

    return props.create && search.value != undefined && search.value.length > 0 && !existingNames.includes(search.value.toLowerCase())
})

/**
 * modelValue id or undefined if nothing is selected or its props.multiple is set
 */
const editingItemId = computed(() => {
    if (props.multiple && lastAddedItem.value) {
        return lastAddedItem.value.id
    } else if (autoselectValue.value && !Array.isArray(autoselectValue.value)) {
        return autoselectValue.value.id
    }

    return undefined
})

/**
 * default to model class localization key for a label when none is given
 */
const label = computed(() => {
    if (props.label) {
        return props.label
    } else {
        return t(modelClass.value.model.localizationKey)
    }
})

/**
 * check if model has a non-standard label attribute defined, if not use "name" as the value attribute
 */
const itemLabelAttribute = computed(() => {
    if (modelClass.value.model.itemLabel) {
        return modelClass.value.model.itemLabel
    }
    return 'name'
})

/**
 * watcher to update external model value
 */
watch(autoselectValue, (newValue, oldValue) => {
    console.log('AUTOSELECT value changed', oldValue, ' ==>', newValue)
    updateModelValue(newValue)
})

/**
 * watcher to update internal autoselectValue
 */
watch(() => props.modelValue, (newValue, oldValue) => {
    // do not trigger update if value has not actually changed
    if (modelValuesEqual(newValue, oldValue)) {
        return
    }

    console.log('MODEL value changed', oldValue, ' ==>', newValue)

    updateAutoselectValue(newValue)
})

function modelValuesEqual(
    left: ModelOption | ModelOption[] | number | number[] | undefined | null,
    right: ModelOption | ModelOption[] | number | number[] | undefined | null,
): boolean {
    if (left === right) return true
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false
    const key = (value: ModelOption | number) => typeof value === 'number' ? value : value.id
    return left.every((value, index) => key(value) === key(right[index]!))
}


/**
 * listen to search update and call debounced search
 */
watch(search, (newValue, oldValue) => {
    // without the focus check an additional load is performed when the select is collapsed as vuetify changes the search
    if (hasFocus.value || !hasLoadedOnce.value) {
        loading.value = true
        debouncedSearchItems()
    }
})

/**
 * create instance of model class before mounting
 */
onBeforeMount(() => {
    modelClass.value = getGenericModelFromString(props.model, t)
})

onMounted(() => {
    if (props.searchOnLoad) {
        searchItems()
    }

    //watcher does not trigger on initial load so trigger once when mounted (do not use immediate as that is to early/before everything else is initialiezd)
    updateAutoselectValue(props.modelValue)
})

/**
 * debounce search to prevent race conditions
 */
const debouncedSearchItems = useDebounceFn(() => {
    searchItems()
}, 300)

/**
 * performs the API request to search for the selected input
 */
function searchItems() {
    const revision = ++searchRevision
    console.log('searching items')
    let query = (search.value == undefined) ? '' : search.value
    if (query.startsWith(' ')) {
        console.log('search query starts with space')
        loading.value = false
        return
    }
    console.log('search query is', query)
    loading.value = true
    return modelClass.value.list({query: query, page: 1, pageSize: props.limit}).then((r: any) => {
        if (revision !== searchRevision || query !== (search.value ?? '')) return
        if (modelClass.value.model.isPaginated) {
            hasMoreItems.value = !!r.next
            items.value = r.results
        } else {
            hasMoreItems.value = false
            items.value = r
        }

        if (showCreate.value) {
            let createItem = optionWithLabel(search.value)
            items.value.splice(0, 0, createItem)
        }

        if (hasMoreItems.value) {
            let infoItem = optionWithLabel(t('ModelSelectResultsHelp'), -1)
            items.value.push(infoItem)
        }

    }).catch((err: any) => {
        if (revision === searchRevision) useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    }).finally(() => {
        if (revision !== searchRevision) return
        console.log('search items finished')
        loading.value = false
        hasLoadedOnce.value = true
    })
}


/**
 * handle new object being created
 * @param name name of the item to create
 * @param edit if the edit dialog should be opened after creation
 */
async function createItem(name: string | undefined, edit: boolean) {
    if (props.create && name != undefined && name != '') {
        loading.value = true
        return modelClass.value.create({name: name}).then((createdObj: any) => {
            useMessageStore().addPreparedMessage(PreparedMessage.CREATE_SUCCESS, createdObj)
            emit('create', createdObj)

            items.value.push(createdObj)
            items.value = items.value.filter((item: any) => item.id != undefined)

            if (props.multiple) {
                if (Array.isArray(autoselectValue.value)) {
                    autoselectValue.value.push(createdObj)
                } else {
                    autoselectValue.value = [createdObj]
                }

                search.value = ''
            } else {
                autoselectValue.value = createdObj
            }

            lastAddedItem.value = createdObj

            if (edit && !props.multiple) {
                editDialog.value = true
            }
            return createdObj
        }).catch((err: any) => {
            useMessageStore().addError(ErrorMessageType.CREATE_ERROR, err)
        }).finally(() => {
            loading.value = false
        })
    }
}

/**
 * handle edit dialog updates depending on the mode the select is in
 * @param event
 */
function handleModelEditorUpdate(event: ModelOption) {
    if (props.multiple) {
        console.log('is multiple')
        if (Array.isArray(autoselectValue.value) && autoselectValue.value.length > 0) {
            let existingIndex = autoselectValue.value.findIndex((item: any) => item.id == event.id)
            console.log('splicing at', existingIndex)
            if (existingIndex >= 0) autoselectValue.value.splice(existingIndex, 1, event)
        }
    } else {
        autoselectValue.value = event
    }
}

function handleModelEditorCreate(event: ModelOption) {
    if (props.multiple) {
        const selected = Array.isArray(autoselectValue.value) ? autoselectValue.value : []
        if (!selected.some(item => item.id === event.id)) autoselectValue.value = [...selected, event]
    } else {
        autoselectValue.value = event
    }
    lastAddedItem.value = event
    emit('create', event)
}

/**
 * updates the internal autoselectValue from the external modelValue which might use IDs when return object is set to false
 * @param newValue
 */
function updateAutoselectValue(newValue: ModelOption | ModelOption[] | number | number[] | undefined | null) {
    const revision = ++selectionRevision
    console.log('updating autoselect value', newValue)
    if (typeof newValue === 'number') {
        if (!autoselectValue.value || Array.isArray(autoselectValue.value) || autoselectValue.value.id !== newValue) {
            loading.value = true
            return modelClass.value.retrieve(newValue).then((r: ModelOption) => {
                if (revision === selectionRevision) autoselectValue.value = r
            }).catch((err: any) => {
                if (revision === selectionRevision) useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
            }).finally(() => {
                if (revision === selectionRevision) loading.value = false
            })
        }
    } else if ((Array.isArray(newValue) && newValue.every(item => typeof item === 'number'))) {
        let missingIds = newValue

        if (autoselectValue.value && Array.isArray(autoselectValue.value)) {
            // remove existing items no longer in external model
            // check before filtering because filtering triggers an update which causes an infinite loop
            if (autoselectValue.value.findIndex(item => item.id !== undefined && !newValue.includes(item.id)) != -1) {
                autoselectValue.value = autoselectValue.value.filter(item => item.id !== undefined && newValue.includes(item.id))
            }

            // remove already existing values from missingIds
            const existingIds = new Set(autoselectValue.value.map(item => item.id))
            missingIds = newValue.filter(id => !existingIds.has(id))
        }
        console.log('missingIds', missingIds)

        if (missingIds.length > 0) {
            loading.value = true

            return Promise.all(
                missingIds.map(id => modelClass.value.retrieve(id))
            ).then((missingItems: ModelOption[]) => {
                if (revision !== selectionRevision) return
                if (autoselectValue.value && Array.isArray(autoselectValue.value)) {
                    // check again items were not already added (might occur with race conditions)
                    const existingIds = new Set(autoselectValue.value.map(item => item.id))
                    missingItems = missingItems.filter(item => !existingIds.has(item.id))

                    autoselectValue.value = autoselectValue.value.concat(missingItems)
                } else {
                    autoselectValue.value = missingItems
                }
            }).catch((err: any) => {
                if (revision === selectionRevision) useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
            }).finally(() => {
                if (revision === selectionRevision) loading.value = false
            })
        }
        if (!Array.isArray(autoselectValue.value)) autoselectValue.value = []
    } else {
        autoselectValue.value = newValue
    }
    loading.value = false
}

/**
 * updates external model value when changes to the internal autoselectValue occur
 * supports returning ids or objects
 * @param newValue
 */
function updateModelValue(newValue: ModelOption | ModelOption[] | undefined | null) {
    if (!props.returnObject) {
        console.log('returning value as ID(s)', newValue)
        if (Array.isArray(newValue)) {
            console.log('as flat array', newValue.flatMap(item => item.id))
            emit('update:modelValue', newValue.flatMap(item => item.id))
        } else {
            emit('update:modelValue', newValue == null ? newValue : newValue.id)
        }
    } else {
        emit('update:modelValue', newValue)
    }
}

function optionLabel(item: ModelOption): string {
    const value = (item as Record<string, unknown>)[itemLabelAttribute.value]
    return typeof value === 'string' ? value : ''
}

function optionWithLabel(label: string | undefined, id?: number): ModelOption {
    return {...(id === undefined ? {} : {id}), [itemLabelAttribute.value]: label ?? ''}
}

</script>

<style scoped>

</style>
