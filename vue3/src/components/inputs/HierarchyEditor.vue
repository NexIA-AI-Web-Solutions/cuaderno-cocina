<template>
    <v-row justify="space-between" dense>
        <v-col cols="6">
            <v-card :loading="loading" variant="outlined">
                <v-card-text>
                    <v-treeview
                        v-model:activated="activeObjs"
                        return-object
                        activatable
                        rounded
                        indent-lines
                        hide-actions
                        density="compact"
                        open-all
                        item-title="name"
                        :items="objTree"
                        :disabled="loading">
                        <template v-slot:append="{ item, depth, isFirst, isLast }">
                            <v-icon icon="fa-solid fa-location-crosshairs" v-if="item.id == editingObj.id"></v-icon>
                        </template>
                    </v-treeview>
                </v-card-text>
            </v-card>
        </v-col>
        <v-col cols="6">
            <v-card v-if="selectedObject" :title="genericModel.getLabel(selectedObject)" :prepend-icon="genericModel.model.icon" variant="outlined">
                <v-card-text>
                    <v-label>{{$t('AddChild')}}</v-label>
                    <v-model-select :model="genericModel.model.name" v-model="addChildObj" create>
                        <template #append>
                            <v-btn color="save" icon="$save" :disabled="addChildObj == undefined" @click="addChildObj && moveObject(addChildObj, selectedObject!.id); addChildObj = undefined"></v-btn>
                        </template>
                    </v-model-select>
                    <v-label>{{$t('Parent')}}</v-label>
                    <v-model-select :model="genericModel.model.name" v-model="setParentObj" create>
                        <template #append>
                            <v-btn color="save" icon="$save" :disabled="setParentObj == undefined" @click="setParentObj && moveObject(selectedObject!, setParentObj.id); setParentObj = undefined"></v-btn>
                        </template>
                    </v-model-select>

                    <v-btn @click="moveObject(selectedObject!,0)" class="mt-2" color="warning" prepend-icon="fa-solid fa-link-slash" block>
                        {{$t('RemoveParent')}}
                    </v-btn>
                    <v-btn block prepend-icon="$edit" color="info" class="mt-4"
                           :to="{name: 'ModelEditPage' , params: {model: genericModel.model.name, id: selectedObject!.id }}"
                            v-if="selectedObject!.id != editingObj.id">
                        {{ $t('Edit') }}
                    </v-btn>
                    <v-btn block prepend-icon="$search" color="success" class="mt-4 mb-10"
                           :to="searchLink" target="_blank"
                           v-if="searchLink">
                        {{ $t('Recipes') }}
                    </v-btn>
                </v-card-text>
            </v-card>
        </v-col>
    </v-row>
</template>

<script setup lang="ts">

import {computed, onMounted, PropType, ref} from "vue";
import ModelSelect from "@/components/inputs/ModelSelect.vue";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore.ts";
import {EditorSupportedModels, getGenericModelFromString} from "@/types/Models.ts";
import type {Food, Keyword} from "@/openapi";
import {useI18n} from "vue-i18n";
import VModelSelect from "@/components/inputs/VModelSelect.vue";

type HierarchyObject = Food | Keyword
type Tree<T> = T & { children: Tree<T>[] };

const props = defineProps({
    model: {type: String as PropType<EditorSupportedModels>, required: true},
})

const editingObj = defineModel<HierarchyObject>({required: true})

const t = useI18n()

/**
 * compute tree structure based on object list
 */
const objTree = computed(() => {
    return buildTreeDFS(objList.value)
})

/**
 * link to search for recipes using the selected object
 */
const searchLink = computed(() => {
    if (selectedObject.value) {
        if (props.model == 'Keyword') {
            return {name: 'SearchPage', query: {keywords: selectedObject.value.id}}
        } else if (props.model == 'Food') {
            return {name: 'SearchPage', query: {foods: selectedObject.value.id}}
        }
    }
    return undefined
})

const loading = ref(false)


const objList = ref<HierarchyObject[]>([])

const activeObjs = ref<HierarchyObject[]>([])
const selectedObject = computed(() => activeObjs.value.length === 1 ? activeObjs.value[0] : undefined)
const addChildObj = ref<HierarchyObject>()
const setParentObj = ref<HierarchyObject>()

const genericModel = ref(getGenericModelFromString(props.model, t))

onMounted(() => {
    recLoadObjectTree(editingObj.value.id, 1)
})

/**
 * recursively load all objects belonging to the selected objects tree
 * @param objId base object id to look for tree
 * @param page page to load
 */
function recLoadObjectTree(objId: number, page: number) {
    loading.value = true

    genericModel.value.list({rootTree: objId, pageSize: 100}).then(response => {
        objList.value = objList.value.concat(response.results as HierarchyObject[])
        if (response.next) {
            recLoadObjectTree(objId, page + 1)
        } else {
            if (activeObjs.value.length == 0) {
                const editedNode = objTree.value.find(x => x.id === editingObj.value.id)
                activeObjs.value = editedNode ? [editedNode] : []
            }
            loading.value = false
        }
    })
}

/**
 * move the given obj to the desired parent and update in local data cache
 * @param obj object to change parent for
 * @param parentId parent id to change the object to or 0 to remove parent
 */
function moveObject(obj: HierarchyObject, parentId: number) {
    loading.value = true

    genericModel.value.move(obj, parentId).then((r: any) => {
        objList.value = []
        recLoadObjectTree(editingObj.value.id, 1)
    }).catch((err: any) => {
        loading.value = false
        useMessageStore().addError(ErrorMessageType.UPDATE_ERROR, err)
    })
}

/**
 * Recursively build a tree datastructures from a DFS ordered list of objects
 */
function buildTreeDFS<T extends { id: number; parent: number }>(items: T[]): Tree<T>[] {
    let index = 0;

    function buildSubtree(parentId: number): Tree<T>[] {
        const children: Tree<T>[] = [];
        while (index < items.length && items[index]?.parent === parentId) {
            const item = items[index++];
            if (!item) break
            const node: Tree<T> = {
                ...item,
                children: buildSubtree(item.id) // recurse immediately, consumes children in DFS order
            };
            children.push(node);
        }
        return children;
    }

    return buildSubtree(0)
}

</script>

<style scoped>

</style>
