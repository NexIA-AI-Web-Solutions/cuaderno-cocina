<template>
    <v-alert color="primary" variant="tonal" v-if="useUserPreferenceStore().serverSettings.hosted">
        <v-alert-title>
            <v-row>
                <v-col>
                    <v-avatar :image="brandMark" class="me-2"></v-avatar>
                    {{ $t('ThankYou') }}!

                </v-col>
                <v-col>
                    <v-btn color="primary" class="float-right" :to="{name: 'EnterpriseSettingsBillingSubscription'}" target="_blank">{{ $t('ManageSubscription') }}</v-btn>

                </v-col>
            </v-row>
        </v-alert-title>
        <p class="mt-2">{{ $t('ThanksTextHosted') }}</p>
    </v-alert>

    <v-alert color="primary" variant="tonal" v-if="!useUserPreferenceStore().serverSettings.hosted">
        <v-alert-title>
            <v-row>
                <v-col>
                    <v-avatar :image="brandMark" class="me-2"></v-avatar>
                    {{ $t('ThankYou') }}!

                </v-col>
                <v-col>
                    <v-btn color="primary" class="float-right" :to="{name: 'SettingsPage'}">{{ $t('Settings') }}
                    </v-btn>

                </v-col>
            </v-row>
        </v-alert-title>
        <p class="mt-2">{{ $t('ThanksTextSelfhosted') }}</p>
    </v-alert>

</template>

<script setup lang="ts">

import brandMark from "@/assets/cuaderno-mark.svg";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";
</script>


<style scoped>

</style>