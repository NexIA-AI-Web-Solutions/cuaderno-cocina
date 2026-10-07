<template>
    <v-card class="ml-auto mr-auto" max-width="300px" :prepend-avatar="brandMark" :title="$t('ImportIntoTandoor')" @click="dialog = true">

    </v-card>

    <v-dialog max-width="800px" v-model="dialog">
        <v-card>
            <v-closable-card-title :title="$t('ImportIntoTandoor')" v-model="dialog"></v-closable-card-title>
            <v-tabs grow v-model="tab">
                <v-tab value="hosted">Cuaderno Cocina</v-tab>
                <v-tab value="selfhosted">{{ $t('SelfHosted') }}</v-tab>
            </v-tabs>

            <v-card-text>
                <v-tabs-window v-model="tab">
                    <v-tabs-window-item value="hosted">
                        <p>{{ $t('AboutTandoor') }} <router-link :to="{name: 'StartPage'}">{{$t('Learn_More')}}.</router-link></p>
                        <p>{{ $t('ImportIntoTandoorHelp') }}</p>
                        <v-list>
                            <v-list-item border>
                                <v-card-title>1. {{ $t('CreateAccount') }}</v-card-title>
                                <template #append>
                                    <v-btn icon="fa-solid fa-arrow-up-right-from-square" :href="getFullUrl('')" target="_blank"></v-btn>
                                </template>
                            </v-list-item>
                            <v-list-item border>
                                <v-card-title>2. {{ $t('Import') }}</v-card-title>
                                <template #append>
                                    <v-btn icon="fa-solid fa-paper-plane" :href="hostedImportUrl" target="_blank"></v-btn>
                                </template>
                            </v-list-item>
                        </v-list>
                    </v-tabs-window-item>
                    <v-tabs-window-item value="selfhosted">
                        <p>{{ $t('AboutTandoor') }} <router-link :to="{name: 'StartPage'}">{{$t('Learn_More')}}.</router-link></p>
                        <p>{{ $t('ImportIntoTandoorHelp') }}</p>

                        <v-list-item border>
                            <v-card-title>1. {{ $t('URL') }}</v-card-title>
                            <v-text-field v-model="selfhostedUrl" :label="$t('Url')"></v-text-field>
                        </v-list-item>
                        <v-list-item border>
                            <v-card-title>2. {{ $t('Import') }}</v-card-title>
                            <template #append>
                                <v-btn icon="fa-solid fa-paper-plane" :href="selfhostedImportUrl" :disabled="selfhostedUrl == ''" target="_blank"></v-btn>
                            </template>
                        </v-list-item>

                    </v-tabs-window-item>
                </v-tabs-window>
            </v-card-text>
        </v-card>
    </v-dialog>
</template>


<script setup lang="ts">

import brandMark from "@/assets/cuaderno-mark.svg";
import {useDjangoUrls} from "@/composables/useDjangoUrls";
import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import {computed, ref} from "vue";

const {getFullUrl} = useDjangoUrls()

const hostedImportUrl = computed(() => {
    return getFullUrl('recipe/import') + '?url=' + encodeURIComponent(location.href)
})

const selfhostedImportUrl = computed(() => {
    let selfhostedServerUrl = selfhostedUrl.value
    if (!selfhostedServerUrl.endsWith('/')) {
        selfhostedServerUrl += '/'
    }
    return selfhostedServerUrl + 'recipe/import/?url=' + encodeURIComponent(location.href)
})

const dialog = ref(false)
const tab = ref('hosted')
const selfhostedUrl = ref('')


</script>


<style scoped>

</style>