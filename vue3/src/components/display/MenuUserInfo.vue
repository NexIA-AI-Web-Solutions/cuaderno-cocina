<template>
    <v-list-item class="mb-2">
        <template #prepend>
            <v-avatar color="primary">{{ useUserPreferenceStore().userSettings.user.displayName.charAt(0) }}</v-avatar>
        </template>
        <v-list-item-title class="text-wrap cuaderno-identity-name">{{ useUserPreferenceStore().userSettings.user.displayName }}</v-list-item-title>
        <v-list-item-subtitle class="text-wrap cuaderno-identity-line">
            <i :class="TSpace.icon" aria-hidden="true"></i>
            <span class="sr-only">{{ $t('Space') }}:</span>
            {{ useUserPreferenceStore().activeSpace.name }}
        </v-list-item-subtitle>
        <router-link class="cuaderno-household-link cuaderno-identity-line"
            :to="{name: 'ModelListPage', params: {model: 'household'}}"
            v-if="activeHousehold">
            <i :class="THousehold.icon" aria-hidden="true"></i>
            {{ activeHousehold.name }}
        </router-link>
        <router-link class="cuaderno-household-link cuaderno-identity-line" :to="{name: 'ModelListPage', params: {model: 'UserSpace'}}"
                              v-else>
            <i :class="THousehold.icon" aria-hidden="true"></i>
            {{ $t('NoHousehold') }}
        </router-link>
    </v-list-item>
</template>

<script setup lang="ts">

import {THousehold, TSpace} from "@/types/Models.ts";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";
import {useRouter} from "vue-router";
import {computed} from "vue";

let router = useRouter()
const userPreferences = useUserPreferenceStore()
const activeHousehold = computed(() => userPreferences.activeUserSpace?.household ?? null)
</script>

<style scoped>
.cuaderno-identity-name, .cuaderno-identity-line { overflow-wrap: anywhere; }
.cuaderno-identity-line { display: block; margin-top: 4px; line-height: 1.5; }
.cuaderno-household-link { color: rgb(var(--v-theme-primary)); font-size: .875rem; }
.cuaderno-household-link i { margin-inline-end: 4px; }
</style>
