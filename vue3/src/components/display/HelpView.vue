<template>
    <!-- Upstream source provenance: https://github.com/TandoorRecipes/recipes; original licenses retained. -->
    <v-layout class="cuaderno-help-layout">
        <v-navigation-drawer v-model="drawer" class="cuaderno-help-navigation">
            <v-list :aria-label="$t('Help')">
                <v-list-item v-for="section in helpSections" :key="section.id" link
                             :title="$t(section.title)" :prepend-icon="section.icon"
                             :active="window === section.id" @click="window = section.id"></v-list-item>
                <v-list-item link :title="$t('Translations')" prepend-icon="fa-solid fa-language"
                             :active="window === 'translations'" @click="window = 'translations'"></v-list-item>
            </v-list>
        </v-navigation-drawer>
        <v-main scrollable>
            <v-container class="cuaderno-help-article">
                <v-select v-model="window" :items="mobileMenuItems" :label="$t('Help')" class="d-block d-lg-none" variant="outlined"></v-select>
                <v-window v-model="window">
                    <v-window-item v-for="section in helpSections" :key="section.id" :value="section.id">
                        <h1 class="text-h4 mb-4">{{ section.id === 'start' ? 'Bienvenido a Cuaderno Cocina' : $t(section.title) }}</h1>
                        <v-alert v-if="section.id === 'ai' && !aiEnabled" type="info" variant="tonal" class="mb-4" role="status">
                            La IA no está habilitada para este espacio. Puedes trabajar con recetas, listas y planes sin activarla.
                        </v-alert>
                        <p v-for="paragraph in section.paragraphs" :key="paragraph" class="mb-4">{{ paragraph }}</p>
                        <div v-if="section.id !== 'ai' || aiEnabled" class="d-flex flex-wrap ga-2 mt-5">
                            <v-btn v-for="action in section.actions" :key="`${action.to.name}-${action.title}`"
                                   color="primary" variant="tonal" min-height="44"
                                   :prepend-icon="action.icon" :to="action.to">{{ $t(action.title) }}</v-btn>
                        </div>
                        <v-btn v-if="section.id === 'start'" class="mt-4" variant="text" min-height="44"
                               href="https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/tree/cuaderno/main"
                               target="_blank" rel="noopener noreferrer" prepend-icon="fa-solid fa-code-branch">Código fuente</v-btn>
                    </v-window-item>
                    <v-window-item value="translations">
                        <div class="d-flex align-center justify-space-between">
                            <h2>{{ $t('Translations') }}</h2>
                            <v-btn variant="tonal" color="primary" href="https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/tree/cuaderno/main/vue3/src/locales" target="_blank" prepend-icon="fa-solid fa-language">
                                {{ $t('help_translate') }}
                            </v-btn>
                        </div>
                        <p class="mt-3">
                            Las traducciones comunitarias se mantienen junto al código fuente de la aplicación.
                            Los idiomas con al menos un {{ minCoverage }}% de traducción de la interfaz están disponibles en el selector de idioma.
                        </p>

                        <v-table density="compact" class="mt-4">
                            <thead>
                                <tr>
                                    <th>{{ $t('Language') }}</th>
                                    <th>Interfaz</th>
                                    <th>Servidor</th>
                                    <th><span class="sr-only">Editar traducción</span></th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="lang in sortedCoverage" :key="lang.filename">
                                    <td>
                                        <span :class="{'text-disabled': lang.fe < minCoverage}">
                                            {{ lang.name }}
                                        </span>
                                    </td>
                                    <td style="min-width: 120px">
                                        <div class="d-flex align-center ga-2">
                                            <v-progress-linear
                                                :model-value="lang.fe"
                                                :color="barColor(lang.fe)"
                                                height="24"
                                                rounded
                                                style="max-width: 100px"
                                            >
                                                <template #default>
                                                    <span class="text-caption" style="font-size: 12px">{{ lang.fe }}%</span>
                                                </template>
                                            </v-progress-linear>
                                        </div>
                                    </td>
                                    <td style="min-width: 120px">
                                        <div class="d-flex align-center ga-2">
                                            <v-progress-linear
                                                :model-value="lang.be"
                                                :color="barColor(lang.be)"
                                                height="24"
                                                rounded
                                                style="max-width: 100px"
                                            >
                                                <template #default>
                                                    <span class="text-caption" style="font-size: 12px">{{ lang.be }}%</span>
                                                </template>
                                            </v-progress-linear>
                                        </div>
                                    </td>
                                    <td>
                                        <v-btn
                                            min-height="44"
                                            min-width="44"
                                            variant="text"
                                            icon="fa-solid fa-pen"
                                            :href="weblateUrl(lang.filename)"
                                            target="_blank"
                                            :aria-label="'Editar traducción: ' + lang.name"
                                        ></v-btn>
                                    </td>
                                </tr>
                            </tbody>
                        </v-table>
                    </v-window-item>
                </v-window>
            </v-container>
        </v-main>
    </v-layout>


</template>

<script setup lang="ts">

import {ref, computed} from "vue";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";
import {useI18n} from "vue-i18n";
import {useRoute} from "vue-router";
import {localeCoverage, LOCALE_MIN_COVERAGE as minCoverage} from "@/i18n.ts";
import {helpSections, validHelpSection} from "@/cuaderno/helpContent";

const props = withDefaults(defineProps<{
    defaultSection?: string
}>(), {
    defaultSection: undefined,
})

const {t} = useI18n()
const route = useRoute()
const drawer = defineModel<boolean>()
const section = props.defaultSection || (typeof route.query.section === 'string' ? route.query.section : null)
const window = ref(validHelpSection(section))
const aiEnabled = computed(() => useUserPreferenceStore().activeSpace.aiEnabled === true)

const mobileMenuItems = computed(() => [
    ...helpSections.map(section => ({title: t(section.title), props: {prependIcon: section.icon}, value: section.id})),
    {title: t('Translations'), props: {prependIcon: 'fa-solid fa-language'}, value: 'translations'},
])

// Weblate directory names use underscore format (nb_NO, zh_Hant)
function weblateUrl(filename: string): string {
    return `https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/blob/cuaderno/main/vue3/src/locales/${filename}.json`
}

function barColor(pct: number): string {
    if (pct >= 80) return 'success'
    if (pct >= minCoverage) return 'warning'
    return 'error'
}

// Use Intl.DisplayNames to get native language names
const displayNames = new Intl.DisplayNames(['es'], {type: 'language'})

const sortedCoverage = computed(() => {
    return Object.entries(localeCoverage)
        .filter(([filename]) => filename !== 'en')  // exclude source language
        .map(([filename, data]) => {
            const code = filename.split('_').join('-').toLowerCase()
            let name: string
            try {
                name = displayNames.of(code) || filename
            } catch {
                name = filename
            }
            return {filename, code, name, fe: data.fe, be: data.be}
        })
        .sort((a, b) => b.fe - a.fe || b.be - a.be)
})

</script>


<style scoped>
.cuaderno-help-layout { min-height: 70vh; }
.cuaderno-help-article { max-width: 860px; padding: 24px; }
.cuaderno-help-article p { max-width: 68ch; line-height: 1.75; }
.cuaderno-help-navigation { border-inline-end: 1px solid rgba(var(--v-theme-on-surface), 0.12); }
@media (max-width: 600px) {
    .cuaderno-help-article { padding: 16px; }
    .cuaderno-help-article h1 { font-size: 1.65rem !important; line-height: 1.3; }
}
</style>
