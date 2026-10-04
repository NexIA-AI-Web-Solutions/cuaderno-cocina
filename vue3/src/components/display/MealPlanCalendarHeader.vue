<template>
    <div>
        <v-row class="pa-2">
            <v-col md="8" cols="12" class="align-center d-none d-md-flex text-h5">
                {{ DateTime.fromJSDate(props.headerProps?.displayFirstDate).toLocaleString(DateTime.DATE_MED) }} -
                {{ DateTime.fromJSDate(props.headerProps?.displayLastDate).toLocaleString(DateTime.DATE_MED) }}
            </v-col>
            <v-col md="4" cols="12">
                <v-date-input
                    v-model="date"
                    prepend-icon=""
                    variant="outlined"
                    density="compact"
                    hide-details
                >
                    <template #prepend>
                        <v-btn density="compact" icon="fa-solid fa-chevron-left" variant="plain" :disabled="!props.headerProps.previousFullPeriod" @click="setDate(props.headerProps.previousFullPeriod)"></v-btn>
                    </template>
                    <template #append-inner>
                        <v-btn density="compact" icon="fa-solid fa-calendar-day" variant="plain" @click.stop="date = new Date()"></v-btn>
                    </template>
                    <template #append>
                        <v-btn density="compact" icon="fa-solid fa-chevron-right" variant="plain" :disabled="!props.headerProps.nextFullPeriod" @click="setDate(props.headerProps.nextFullPeriod)"></v-btn>
                    </template>
                </v-date-input>
            </v-col>
        </v-row>
    </div>
</template>

<script setup lang="ts">

import {IHeaderProps} from "vue-simple-calendar";
import {ref, watch} from "vue";
import {VDateInput} from "vuetify/labs/VDateInput";
import {DateTime} from "luxon";

const emit = defineEmits(['input'])

const props = defineProps({
    headerProps: {
        type: Object as () => IHeaderProps,
        required: true,
    },
})

const date = ref(new Date())

function setDate(value: Date | null) {
    if (value) date.value = value
}

watch(() => date.value, (newValue, oldValue) => {
    emit('input', newValue)
})

</script>

<style scoped>

</style>
