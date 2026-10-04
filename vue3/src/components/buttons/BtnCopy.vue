<template>

    <v-btn :color="color" :size="size" :density="density" @click="clickCopy()" :variant="variant">
        <slot name="default">
            <v-icon icon="$copy"></v-icon>
            <v-tooltip v-model="showToolip" target="parent" location="top">
                <v-icon icon="$copy"></v-icon>
                {{$t('Copied')}}!
            </v-tooltip>
        </slot>
    </v-btn>

</template>

<script setup lang="ts">

import {useClipboard} from "@vueuse/core";
import {type PropType, ref} from "vue";

const {copy} = useClipboard()

const props = defineProps({
    copyValue: {type: String, default: ''},
    color: {type: String, default: 'success'},
    size: {type: String, default: 'default'},
    density: {type: String as PropType<'default' | 'comfortable' | 'compact'>, default: 'default'},
    variant: {type: String as PropType<'flat' | 'plain' | 'text' | 'elevated' | 'outlined' | 'tonal'>, default: 'elevated'},

})

const showToolip = ref(false)

function clickCopy() {
    copy(props.copyValue)
    showToolip.value = true
    setTimeout(() => {
        showToolip.value = false
    }, 3000)
}

</script>


<style scoped>

</style>
