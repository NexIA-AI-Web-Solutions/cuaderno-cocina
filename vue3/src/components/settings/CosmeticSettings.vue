<template>
    <v-form class="cuaderno-appearance-form">
        <section class="cuaderno-settings-section" aria-labelledby="cuaderno-appearance-heading">
        <h1 id="cuaderno-appearance-heading" class="text-h5">{{ $t('Cosmetic') }}</h1>
        <v-divider class="mb-3"></v-divider>

        <language-select></language-select>

        <v-label>{{$t('Nav_Color')}}</v-label>
        <v-color-picker v-model="useUserPreferenceStore().userSettings.navBgColor" mode="hex" :modes="['hex']" show-swatches :swatches="[['#ddbf86'],['#b98766'],['#b55e4f'],['#82aa8b'],['#385f84']]"></v-color-picker>

        <v-select :label="$t('Theme')" class="mt-4" v-model="useUserPreferenceStore().userSettings.theme" :items="[{title: 'Cuaderno Cocina', value: 'TANDOOR'}, {title: 'Cuaderno Cocina oscuro (incompleto)', value: 'TANDOOR_DARK'}, ]">
        </v-select>

        <v-checkbox :label="$t('Show_Logo')" :hint="$t('Show_Logo_Help')" persistent-hint v-model="useUserPreferenceStore().userSettings.navShowLogo"></v-checkbox>
        <v-checkbox :label="$t('Sticky_Nav')" :hint="$t('Sticky_Nav_Help')" persistent-hint v-model="useUserPreferenceStore().userSettings.navSticky"></v-checkbox>

        <v-btn class="mt-3" color="success" @click="useUserPreferenceStore().updateUserSettings()" prepend-icon="$save">{{$t('Save')}}</v-btn>
        </section>

        <section class="cuaderno-settings-section mt-5" aria-labelledby="cuaderno-preferences-heading">
        <h2 id="cuaderno-preferences-heading" class="text-h5">{{ $t('Preferences') }}</h2>
        <v-divider class="mb-3"></v-divider>

        <v-text-field v-model="useUserPreferenceStore().userSettings.defaultUnit" :label="$t('Default_Unit')"></v-text-field>
        <v-number-input v-model="useUserPreferenceStore().userSettings.ingredientDecimals" :label="$t('Decimals')" :step="1" :min="0" :max="4"></v-number-input>

<!--        <v-select-->
<!--            :label="$t('DefaultPage')"-->
<!--            v-model="useUserPreferenceStore().userSettings.defaultPage"-->
<!--            :items="availableDefaultPages"-->
<!--            item-title="label"-->
<!--            item-value="page"-->
<!--        ></v-select>-->

        <v-checkbox :label="$t('Use_Fractions')" :hint="$t('Use_Fractions_Help')" persistent-hint v-model="useUserPreferenceStore().userSettings.useFractions"></v-checkbox>
        <v-checkbox :label="$t('Comments_setting')" v-model="useUserPreferenceStore().userSettings.comments"></v-checkbox>
        <v-checkbox :label="$t('left_handed')" :hint="$t('left_handed_help')" persistent-hint v-model="useUserPreferenceStore().userSettings.leftHanded"></v-checkbox>
        <v-checkbox :label="$t('show_step_ingredients_setting')" :hint="$t('show_step_ingredients_setting_help')" persistent-hint v-model="useUserPreferenceStore().userSettings.showStepIngredients"></v-checkbox>
        <v-btn class="mt-3" color="success" @click="useUserPreferenceStore().updateUserSettings()" prepend-icon="$save">{{$t('Save')}}</v-btn>
        </section>
    </v-form>
</template>


<script setup lang="ts">


import {onMounted, ref} from "vue";
import {ApiApi, Localization} from "@/openapi";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import {useI18n} from "vue-i18n";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import LanguageSelect from "@/components/inputs/LanguageSelect.vue";

const {t} = useI18n()

const availableDefaultPages = ref([
    {page: 'SEARCH', label: t('Search')},
    {page: 'SHOPPING', label: t('Shopping_list')},
    {page: 'PLAN', label: t('Meal_Plan')},
    {page: 'BOOKS', label: t('Books')},
])

onMounted(() => {

})

</script>

<style scoped>
.cuaderno-settings-section {
    padding: 24px;
    border: 1px solid rgba(var(--v-theme-on-surface), .14);
    border-radius: 16px;
    background: rgb(var(--v-theme-surface));
}
.cuaderno-appearance-form :deep(.v-color-picker) { max-width: 100%; }
@media (max-width: 600px) { .cuaderno-settings-section { padding: 16px; } }
</style>
