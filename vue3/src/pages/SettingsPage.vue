<template>
    <v-container class="cuaderno-settings-page">
        <v-row>
            <v-col cols="12" md="3" offset-md="1" offset-xl="2" xl="2">
                <nav :aria-label="$t('Settings')">
                <details class="cuaderno-settings-navigation" :open="mdAndUp">
                    <summary class="cuaderno-settings-summary">{{ $t('Settings') }}</summary>
                <v-list class="bg-transparent">
                    <v-list-item :to="{name: 'AccountSettings'}" prepend-icon="fa-solid fa-user">{{ $t('Profile') }}</v-list-item>

                    <v-divider></v-divider>
                    <v-list-subheader>{{ $t('Settings') }}</v-list-subheader>
                    <v-list-item :to="{name: 'CosmeticSettings'}" prepend-icon="fa-solid fa-palette">{{ $t('Cosmetic') }}</v-list-item>
                    <v-list-item :to="{name: 'ShoppingSettings'}" prepend-icon="$shopping">{{ $t('Shopping_list') }}</v-list-item>
                    <v-list-item :to="{name: 'MealPlanSettings'}" prepend-icon="$mealplan">{{ $t('Meal_Plan') }}</v-list-item>
                    <v-list-item :to="{name: 'SearchSettings'}" prepend-icon="$search">{{ $t('Search') }}</v-list-item>
                    <v-divider></v-divider>
                    <v-list-subheader>{{ $t('Space') }}</v-list-subheader>
                    <v-list-item :to="{name: 'SpaceSettings'}" prepend-icon="$settings">{{ $t('SpaceSettings') }}</v-list-item>
                    <v-list-item :to="{name: 'OpenDataImportSettings'}" prepend-icon="fa-solid fa-cloud-arrow-down">{{ $t('Open_Data_Import') }}</v-list-item>
                    <v-list-item :to="{name: 'ExportDataSettings'}" prepend-icon="fa-solid fa-file-export">{{ $t('Export') }}</v-list-item>

                    <template v-for="p in TANDOOR_PLUGINS" :key="p.name">
                        <component :is="p.settingsComponent" v-if="p.settingsComponent"></component>
                    </template>

                    <v-divider></v-divider>
                    <v-list-subheader>Administración</v-list-subheader>
                    <v-list-item :to="{name: 'ApiSettings'}" prepend-icon="fa-solid fa-code">{{ $t('API') }}</v-list-item>
                    <v-list-item :href="getDjangoUrl('system')" target="_blank" prepend-icon="fa-solid fa-server">{{ $t('System') }}</v-list-item>
                </v-list>
                </details>
                </nav>

            </v-col>
            <v-col cols="12" md="7" xl="6" class="cuaderno-settings-content">
                <router-view/>

            </v-col>
        </v-row>
    </v-container>
</template>

<script setup lang="ts">

import {useDjangoUrls} from "@/composables/useDjangoUrls";
import {TANDOOR_PLUGINS} from "@/types/Plugins.ts";
import {useDisplay} from "vuetify";

const {getDjangoUrl} = useDjangoUrls()
const {mdAndUp} = useDisplay()

</script>


<style scoped>
.cuaderno-settings-navigation {
    border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
    border-radius: 16px;
    background: rgb(var(--v-theme-surface));
}
.cuaderno-settings-summary {
    padding: 16px;
    cursor: pointer;
    font-weight: 700;
    min-height: 48px;
}
.cuaderno-settings-navigation :deep(.v-list-item) {
    margin: 4px 8px;
    border-radius: 10px;
}
.cuaderno-settings-navigation :deep(.v-list-item--active) {
    color: rgb(var(--v-theme-primary));
    border-inline-start: 3px solid rgb(var(--v-theme-primary));
    font-weight: 600;
}
.cuaderno-settings-content { min-width: 0; }
@media (min-width: 960px) {
    .cuaderno-settings-summary { display: none; }
    .cuaderno-settings-navigation { position: sticky; top: 80px; }
}
</style>
