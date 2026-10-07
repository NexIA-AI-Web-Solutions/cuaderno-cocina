<template>
    <div>
        <v-row class="pa-2">
            <v-col md="7" cols="12" class="align-center d-flex cuaderno-calendar-period">
                <h1 class="text-h6">
                {{ DateTime.fromJSDate(props.headerProps?.displayFirstDate).setLocale(dateLocale).toLocaleString(DateTime.DATE_MED) }} –
                {{ DateTime.fromJSDate(props.headerProps?.displayLastDate).setLocale(dateLocale).toLocaleString(DateTime.DATE_MED) }}
                </h1>
            </v-col>
            <v-col md="5" cols="12">
                <v-date-input
                    v-model="date"
                    :label="$t('Date')"
                    prepend-icon=""
                    variant="outlined"
                    density="compact"
                    hide-details
                >
                    <template #prepend>
                        <v-btn min-width="44" min-height="44" :aria-label="$t('Previous_Period')" :title="$t('Previous_Period')" icon="fa-solid fa-chevron-left" variant="plain" :disabled="!props.headerProps.previousFullPeriod" @click="setDate(props.headerProps.previousFullPeriod)"></v-btn>
                    </template>
                    <template #append-inner>
                        <v-btn min-width="44" min-height="44" :aria-label="$t('Today')" :title="$t('Today')" icon="fa-solid fa-calendar-day" variant="plain" @click.stop="date = new Date()"></v-btn>
                    </template>
                    <template #append>
                        <v-btn min-width="44" min-height="44" :aria-label="$t('Next')" :title="$t('Next')" icon="fa-solid fa-chevron-right" variant="plain" :disabled="!props.headerProps.nextFullPeriod" @click="setDate(props.headerProps.nextFullPeriod)"></v-btn>
                    </template>
                </v-date-input>
            </v-col>
        </v-row>
    </div>
</template>

<script setup lang="ts">

import {IHeaderProps} from "vue-simple-calendar";
import {computed, ref, watch} from "vue";
import {VDateInput} from "vuetify/labs/VDateInput";
import {DateTime} from "luxon";
import {useI18n} from "vue-i18n";

const {locale} = useI18n()
const dateLocale = computed(() => locale.value.replace(/_/g, '-'))

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
.cuaderno-calendar-period h1 { line-height: 1.4; }
@media (max-width: 959px) { .cuaderno-calendar-period { padding-bottom: 0; } }
</style>
