<template>
    <v-btn-group density="compact">
        <v-btn color="create" @click="addProperty()" prepend-icon="$create">{{ $t('Add') }}</v-btn>
        <v-btn color="secondary" @click="addAllProperties" prepend-icon="fa-solid fa-list">{{ $t('AddAll') }}</v-btn>
        <ai-action-button color="info" @selected="propertiesFromAi" :loading="aiLoading" prepend-icon="$ai">{{ $t('AI') }}</ai-action-button>
    </v-btn-group>

    <v-row class="d-none d-md-flex mt-2" v-for="p in properties" dense>
        <v-col cols="0" md="6">
            <v-number-input :step="10" v-model="p.propertyAmount" control-variant="stacked" :precision="2" density="compact" hide-details>
                <template #append-inner v-if="p.propertyType">
                    <v-chip class="me-4">{{ p.propertyType.unit }} / {{ props.amountFor }}
                    </v-chip>
                </template>
            </v-number-input>
        </v-col>
        <v-col cols="0" md="6">
            <v-model-select v-model="p.propertyType" model="PropertyType" density="compact" hide-details>
                <template #append>
                    <v-btn color="delete" size="small" icon @click="deleteProperty(p)">
                        <v-icon icon="$delete"></v-icon>
                    </v-btn>
                </template>
            </v-model-select>
        </v-col>
    </v-row>
    <v-list class="d-md-none">
        <v-list-item v-for="p in properties" border>
            <span v-if="p.propertyType">{{ p.propertyAmount }} {{ p.propertyType.unit }} {{ p.propertyType.name }} / {{ props.amountFor }}
            </span>
            <span v-else><i><{{ $t('New') }}></i></span>
            <template #append>
                <v-btn color="edit">
                    <v-icon icon="$edit"></v-icon>
                    <model-edit-dialog model="Property" :item="p"></model-edit-dialog>
                </v-btn>
            </template>
        </v-list-item>
    </v-list>
</template>

<script setup lang="ts">

import {ApiApi, Food, Property, Recipe, Unit} from "@/openapi";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {computed, nextTick, onMounted, ref} from "vue";
import AiActionButton from "@/components/buttons/AiActionButton.vue";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore.ts";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";
import VModelSelect from "@/components/inputs/VModelSelect.vue";

const props = defineProps({
    amountFor: {type: String, required: true},
})

const editingObj = defineModel<Food | Recipe>({required: true})
const properties = computed(() => editingObj.value.properties ?? [])

const aiLoading = ref(false)

function asFood(value: Food | Recipe): Food | null {
    return 'steps' in value ? null : value
}

function ensureProperties(): Property[] {
    if (!editingObj.value.properties) editingObj.value.properties = []
    return editingObj.value.properties
}

function addProperty() {
    ensureProperties().push({} as Property)
    addPropertiesFoodUnit()
}

/**
 * remove a property from the list
 * @param property property to delete
 */
function deleteProperty(property: Property) {
    if (editingObj.value.properties) {
        editingObj.value.properties = editingObj.value.properties.filter(p => p !== property)
        // TODO delete from DB, needs endpoint for property relation to either recipe or food
    }
}

/**
 * load list of property types from server and add all types that are not yet
 * in the list to the list
 */
function addAllProperties() {
    const api = new ApiApi()

    // if (editingObj.value.properties) {
    //     editingObj.value.properties = []
    // }

    addPropertiesFoodUnit()

    api.apiPropertyTypeList().then(r => {
        const currentProperties = ensureProperties()
        r.results.forEach(pt => {
            if (currentProperties.findIndex(x => x.propertyType.name == pt.name) == -1) {
                currentProperties.push({propertyAmount: 0, propertyType: pt} as Property)
            }
        })
    })
}

function propertiesFromAi(providerId: number) {
    const api = new ApiApi()
    aiLoading.value = true

    const food = asFood(editingObj.value)
    if (food) {
        api.apiFoodAipropertiesCreate({id: food.id, food, provider: providerId}).then(r => {
            editingObj.value = r
            nextTick(() => {
                addPropertiesFoodUnit()
            })
        }).catch(err => {
            useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        }).finally(() => {
            aiLoading.value = false
        })
    } else {
        const recipe = editingObj.value
        if (!('steps' in recipe)) return
        api.apiRecipeAipropertiesCreate({id: recipe.id, recipe, provider: providerId}).then(r => {
            editingObj.value = r
        }).catch(err => {
            useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
        }).finally(() => {
            aiLoading.value = false
        })
    }

}

/**
 * if its empty add the properties food unit
 */
function addPropertiesFoodUnit(){
    const food = asFood(editingObj.value)
    console.log('ADDING UNIT', !food?.propertiesFoodUnit)
    if (food && !food.propertiesFoodUnit) {
        console.log('ADDING UNIT ACTUALLY')
        food.propertiesFoodUnit = (useUserPreferenceStore().defaultUnitObj != null) ? useUserPreferenceStore().defaultUnitObj! : {name: 'g'} as Unit
    }
}


</script>

<style scoped>

</style>
