<template>
    <v-app class="cuaderno-app">
        <a href="#cuaderno-main" class="cuaderno-skip-link">{{ $t('SkipToContent') }}</a>
        <v-app-bar color="tandoor" flat density="comfortable" v-if="!useUserPreferenceStore().isAuthenticated && !useUserPreferenceStore().isPrintMode">
            <router-link :to="{ name: 'StartPage' }">
                <v-img :src="brandLogo" alt="Cuaderno Cocina" width="140px" class="ms-2" ></v-img>
            </router-link>
        </v-app-bar>
        <v-app-bar :color="useUserPreferenceStore().activeSpace.navBgColor ? useUserPreferenceStore().activeSpace.navBgColor : useUserPreferenceStore().userSettings.navBgColor"
                   flat density="comfortable" v-if="useUserPreferenceStore().isAuthenticated && !useUserPreferenceStore().isPrintMode"
                   :absolute="!useUserPreferenceStore().userSettings.navSticky"
                   :scroll-behavior="useUserPreferenceStore().userSettings.navSticky ? 'elevate' : ''">
            <router-link :to="{ name: 'StartPage', params: {} }">
                <v-img :src="brandLogo" alt="Cuaderno Cocina" width="140px" class="ms-2"
                       v-if="useUserPreferenceStore().userSettings.navShowLogo && !useUserPreferenceStore().activeSpace.navLogo"></v-img>
                <v-img :src="useUserPreferenceStore().activeSpace.navLogo?.preview" width="140px" class="ms-2"
                       v-if="useUserPreferenceStore().userSettings.navShowLogo && useUserPreferenceStore().activeSpace.navLogo != undefined"></v-img>
            </router-link>

            <v-spacer></v-spacer>
            <global-search-dialog></global-search-dialog>
            <v-btn icon="$add" class="d-print-none" :aria-label="$t('Create Recipe')" :title="$t('Create Recipe')">
                <v-icon icon="$add" class="fa-fw"></v-icon>
                <v-menu activator="parent">
                    <v-list>
                        <v-list-item prepend-icon="$add" :to="{ name: 'ModelEditPage', params: {model: 'recipe'} }">{{ $t('Create Recipe') }}</v-list-item>
                        <v-list-item prepend-icon="fa-solid fa-globe" :to="{ name: 'RecipeImportPage', params: {} }">{{ $t('Import Recipe') }}</v-list-item>
                    </v-list>
                </v-menu>
            </v-btn>

            <v-btn class="cuaderno-user-menu me-2 d-print-none" :aria-label="$t('Profile')" :title="$t('Profile')" icon variant="text">
                <v-avatar color="primary" size="36">{{ useUserPreferenceStore().userSettings.user.displayName.charAt(0) }}</v-avatar>
                <v-menu activator="parent">

                    <v-list density="compact">
                        <menu-user-info></menu-user-info>
                        <v-divider></v-divider>

                        <component :is="item.component" :="item" :key="item.title" v-for="item in useNavigation().getUserNavigation()"></component>
                    </v-list>
                </v-menu>
            </v-btn>

        </v-app-bar>
        <v-app-bar color="info"
                   v-if="useUserPreferenceStore().isAuthenticated && useUserPreferenceStore().activeSpace.maxRecipes == 10 && useUserPreferenceStore().serverSettings.hosted">
            <p class="text-center w-100">
                {{ $t('HostedFreeVersion') }}
                <v-btn color="success" size="small" variant="flat" :to="{name: 'EnterpriseSettingsBillingSubscription'}">{{ $t('UpgradeNow') }}</v-btn>
            </p>
        </v-app-bar>
        <v-app-bar color="warning" v-if="useUserPreferenceStore().isAuthenticated && isSpaceAboveLimit(useUserPreferenceStore().activeSpace)">
            <p class="text-center w-100">
                {{ $t('SpaceLimitExceeded') }}
                <v-btn color="success" size="small" variant="flat" :to="{name: 'SpaceSettings'}">{{ $t('SpaceSettings') }}</v-btn>
            </p>
        </v-app-bar>

        <v-app-bar color="info" density="compact"
                   v-if="useUserPreferenceStore().isAuthenticated && useUserPreferenceStore().activeSpace.message != '' && !useUserPreferenceStore().isPrintMode">
            <p class="text-center w-100">
                {{ useUserPreferenceStore().activeSpace.message }}
            </p>
        </v-app-bar>

        <v-main id="cuaderno-main" tabindex="-1">
            <router-view></router-view>
        </v-main>

        <!-- completely hide in print mode because setting d-print-node keeps layout -->
        <v-navigation-drawer v-if="lgAndUp && useUserPreferenceStore().isAuthenticated && !useUserPreferenceStore().isPrintMode">
            <v-list>
                <menu-user-info></menu-user-info>
                <v-divider></v-divider>
                <component :is="item.component" :="item" :key="item.title" v-for="item in useNavigation().getNavigationDrawer()"></component>

                <navigation-drawer-context-menu></navigation-drawer-context-menu>
            </v-list>

            <template #append>
                <v-list nav>
                    <v-list-item prepend-icon="fas fa-sliders" :title="$t('Settings')" :to="{ name: 'SettingsPage', params: {} }"></v-list-item>
                    <v-list-item prepend-icon="fa-solid fa-heart" link>
                        Cuaderno Cocina {{ useUserPreferenceStore().serverSettings.version }}
                        <help-dialog></help-dialog>
                    </v-list-item>
                </v-list>
            </template>

        </v-navigation-drawer>

        <v-bottom-navigation grow height="72" class="cuaderno-bottom-navigation" v-if="useUserPreferenceStore().isAuthenticated && !lgAndUp && !useUserPreferenceStore().isPrintMode">
            <v-btn value="recent" :aria-label="$t('Recipes')" :to="{ name: 'StartPage', params: {} }">
                <v-icon icon="fa-fw fas fa-book "/>
                <span>{{ $t('Recipes') }}</span>
            </v-btn>

            <v-btn value="favorites" :aria-label="$t('Meal_Plan')" to="/mealplan">
                <v-icon icon="fa-fw fas fa-calendar-alt"></v-icon>
                <span>{{ $t('Meal_Plan') }}</span>
            </v-btn>

            <v-btn value="nearby" :aria-label="$t('Shopping_list')" to="/shopping">
                <v-icon icon="fa-fw fas fa-shopping-cart"></v-icon>
                <span>{{ $t('Shopping_list') }}</span>
            </v-btn>

            <v-btn value="more" :aria-label="$t('More')">
                <v-icon icon="fa-fw fas fa-bars"></v-icon>
                <span>{{ $t('More') }}</span>
                <v-bottom-sheet activator="parent" close-on-content-click>
                    <v-list nav>
                        <menu-user-info></menu-user-info>
                        <component :is="item.component" :="item" :key="item.title" v-for="item in useNavigation().getBottomNavigation()"></component>
                    </v-list>
                </v-bottom-sheet>
            </v-btn>
        </v-bottom-navigation>

        <v-snackbar-queued
            :vertical="true"
            location="top"
        ></v-snackbar-queued>

    </v-app>

</template>

<script lang="ts" setup>
import brandLogo from "@/assets/cuaderno-logo.svg?no-inline";
import GlobalSearchDialog from "@/components/inputs/GlobalSearchDialog.vue"

import {useDisplay, useLocale} from "vuetify"
import {toVuetifyLocale} from "@/vuetify"
import VSnackbarQueued from "@/components/display/VSnackbarQueued.vue";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import NavigationDrawerContextMenu from "@/components/display/NavigationDrawerContextMenu.vue";
import {onBeforeUnmount, onMounted, ref, watch} from "vue";
import {isSpaceAboveLimit} from "@/utils/logic_utils";
import HelpDialog from "@/components/dialogs/HelpDialog.vue";
import {useNavigation} from "@/composables/useNavigation.ts";
import {useRouter} from "vue-router";
import {useI18n} from "vue-i18n";
import {THousehold, TSpace} from "@/types/Models.ts";
import MenuUserInfo from "@/components/display/MenuUserInfo.vue";

const {lgAndUp} = useDisplay()
const {t} = useI18n()

const router = useRouter()

// These pages replace the generic route title with a recipe/model-specific one.
const pageOwnedTitles = new Set(['RecipeViewPage', 'ModelListPage', 'ModelEditPage', 'ModelDeletePage'])
let lastRouteTitle: string | undefined
watch(() => {
    const route = router.currentRoute.value
    return {path: route.fullPath, name: route.name, text: typeof route.meta.title === 'string' ? t(route.meta.title) : 'Cuaderno Cocina'}
}, (current, previous) => {
    const navigation = !previous || current.path !== previous.path || current.name !== previous.name
    // Reading t() above also tracks messages loaded after the initial route.
    // On locale updates, retain any title that a page has taken ownership of.
    if (navigation || (!pageOwnedTitles.has(String(current.name)) && document.title === lastRouteTitle)) {
        document.title = current.text
        lastRouteTitle = current.text
    }
}, {immediate: true, flush: 'sync'})

onMounted(() => {
    useUserPreferenceStore().init().then(() => {
        if (useUserPreferenceStore().activeSpace.spaceSetupCompleted != undefined && !useUserPreferenceStore().activeSpace.spaceSetupCompleted) {
            router.push({name: 'WelcomePage'})
        }
    })


    const {current} = useLocale()
    let locale = document.querySelector('html')!.getAttribute('lang')
    if (locale != null) {
        current.value = toVuetifyLocale(locale.toLowerCase())
    }
})

/**
 * Space onboarding redirects after navigation.
 */
const removeNavigationHook = router.afterEach((to, from) => {
    if (to.name == 'StartPage' && useUserPreferenceStore().initCompleted && useUserPreferenceStore().activeSpace.spaceSetupCompleted !== undefined && !useUserPreferenceStore().activeSpace.spaceSetupCompleted && useUserPreferenceStore().activeSpace.createdBy.id! == useUserPreferenceStore().userSettings.user.id!) {
        router.push({name: 'WelcomePage'})
    } else if (to.name == 'StartPage' &&
        useUserPreferenceStore().initCompleted &&
        useUserPreferenceStore().activeSpace.spaceSetupCompleted &&
        useUserPreferenceStore().activeSpace.householdSetupCompleted !== undefined &&
        !useUserPreferenceStore().activeSpace.householdSetupCompleted &&
        useUserPreferenceStore().activeSpace.createdBy.id! == useUserPreferenceStore().userSettings.user.id! &&
        useUserPreferenceStore().activeUserSpace?.household == undefined ) {
        router.push({name: 'HouseholdPage'})
    }
})
onBeforeUnmount(removeNavigationHook)

</script>

<style>
@media screen {
    .cuaderno-app .v-app-bar { border-bottom: 1px solid rgba(var(--v-theme-on-surface), .12); }
    .cuaderno-app .v-navigation-drawer .v-list-item {
        min-height: 48px;
        margin: 4px 10px;
        border-radius: 10px;
        border-inline-start: 3px solid transparent;
    }
    .cuaderno-app .v-navigation-drawer .v-list-item--active { border-inline-start-color: rgb(var(--v-theme-primary)); }
    .cuaderno-app .v-btn { text-transform: none; letter-spacing: .01em; }
    .cuaderno-app .v-card { border-radius: 16px; border: 1px solid rgba(var(--v-theme-on-surface), .12); }
    .cuaderno-app .v-card-title { white-space: normal; overflow-wrap: anywhere; line-height: 1.4; }
    .cuaderno-app main h1, .cuaderno-app main h2 { overflow-wrap: anywhere; }
    .cuaderno-app :is(a, button, summary, [role="button"]):focus-visible {
        outline: 3px solid rgb(var(--v-theme-primary));
        outline-offset: 3px;
    }
    .cuaderno-skip-link {
        position: absolute;
        top: 8px;
        left: 16px;
        z-index: 10000;
        padding: 12px 16px;
        border-radius: 8px;
        background: rgb(var(--v-theme-primary));
        color: rgb(var(--v-theme-on-primary));
        transform: translateY(-200%);
    }
    .cuaderno-skip-link:focus { transform: translateY(0); }
    .cuaderno-bottom-navigation { padding-bottom: env(safe-area-inset-bottom, 0); }
    .cuaderno-bottom-navigation .v-btn {
        min-width: 0;
        padding-inline: 6px;
        border-top: 3px solid transparent;
    }
    .cuaderno-bottom-navigation .v-btn--active { border-top-color: rgb(var(--v-theme-primary)); }
    .cuaderno-bottom-navigation .v-btn span {
        font-size: .75rem;
        line-height: 1.2;
        white-space: normal;
        margin-top: 6px;
    }
}

.v-theme--dark {

    a:not([class]) {
        color: #b98766;
        text-decoration: none;
        background-color: transparent
    }

    a:hover {
        color: #fff;
        text-decoration: none
    }

    a:not([href]):not([tabindex]), a:not([href]):not([tabindex]):focus, a:not([href]):not([tabindex]):hover {
        color: inherit;
        text-decoration: none
    }

    a:not([href]):not([tabindex]):focus {
        outline: 0
    }

    /* Meal-Plan */

    .cv-header {
        background-color: #303030 !important;
    }

    .cv-weeknumber, .cv-header-day {
        background-color: #303030 !important;
        color: #fff !important;
    }

    .cv-day.past {
        background-color: #333333 !important;
    }

    .cv-day.today {
        background-color: rgba(185, 135, 102, 0.2) !important;
    }

    .cv-day.outsideOfMonth {
        background-color: #0d0d0d !important;
    }

    .cv-item {
        background-color: #4E4E4E !important;
    }

    .d01 .cv-day-number {
        background-color: #b98766 !important;
    }

    /* mavon-editor link/image dialog */

    .add-image-link {
        background-color: #212121 !important;
        color: #fff !important;
    }

    .add-image-link > i {
        color: rgba(255, 255, 255, 0.7) !important;
    }

    .add-image-link .input-wrapper {
        border-color: #555 !important;
    }

    .add-image-link .input-wrapper input {
        background-color: #212121 !important;
        color: #fff !important;
    }

    .add-image-link .op-btn {
        color: #fff !important;
    }

    /* mavon-editor dark mode — container + toolbar */

    .v-note-wrapper {
        background-color: #212121 !important;
        border-color: #555 !important;
    }

    .v-note-wrapper .v-note-op {
        background-color: #303030 !important;
        border-bottom-color: #555 !important;
    }

    /* mavon-editor dark mode — toolbar icons */

    .v-note-wrapper .op-icon {
        color: rgba(255, 255, 255, 0.7) !important;
    }

    .v-note-wrapper .op-icon:hover {
        color: #fff !important;
        background-color: rgba(255, 255, 255, 0.1) !important;
    }

    .v-note-wrapper .op-icon.selected {
        color: #fff !important;
        background-color: rgba(255, 255, 255, 0.15) !important;
    }

    .v-note-wrapper .op-icon-divider {
        border-left-color: #555 !important;
    }

    /* mavon-editor dark mode — textarea and wrappers */

    .auto-textarea-input,
    .content-input-wrapper,
    .auto-textarea-wrapper {
        color: #e0e0e0 !important;
        background-color: #212121 !important;
    }

    .v-note-wrapper .v-show-content,
    .v-note-wrapper .v-show-content-html,
    .v-note-wrapper .v-note-read-model {
        background-color: #212121 !important;
    }

    .v-note-wrapper .v-note-navigation-wrapper {
        background-color: rgba(33, 33, 33, 0.98) !important;
    }

    .v-note-wrapper .op-header.popup-dropdown {
        background-color: #303030 !important;
        border-color: #555 !important;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3) !important;
    }

    /* mavon-editor dark mode — preview panel */

    .v-note-wrapper .markdown-body {
        color: #e0e0e0 !important;
    }

    .v-note-wrapper .markdown-body a {
        color: #b98766 !important;
    }

    .v-note-wrapper .markdown-body h1,
    .v-note-wrapper .markdown-body h2 {
        border-bottom-color: #555 !important;
    }

    .v-note-wrapper .markdown-body h6 {
        color: #999 !important;
    }

    .v-note-wrapper .markdown-body hr {
        background-color: #555 !important;
    }

    .v-note-wrapper .markdown-body blockquote {
        color: #999 !important;
        border-left-color: #555 !important;
        background-color: rgba(255, 255, 255, 0.05) !important;
    }

    .v-note-wrapper .markdown-body table tr {
        background-color: #212121 !important;
        border-top-color: #555 !important;
    }

    .v-note-wrapper .markdown-body table tr:nth-child(2n) {
        background-color: #2a2a2a !important;
    }

    .v-note-wrapper .markdown-body table td,
    .v-note-wrapper .markdown-body table th {
        border-color: #555 !important;
    }

    .v-note-wrapper .markdown-body code {
        background-color: rgba(255, 255, 255, 0.1) !important;
        color: #e0e0e0 !important;
    }

    .v-note-wrapper .markdown-body .highlight pre,
    .v-note-wrapper .markdown-body pre {
        background-color: #2a2a2a !important;
        color: #e0e0e0 !important;
    }

    .v-note-wrapper .markdown-body kbd {
        color: #e0e0e0 !important;
        background-color: #333 !important;
        border-color: #555 !important;
        box-shadow: inset 0 -1px 0 #444 !important;
    }

    .v-note-wrapper .markdown-body img {
        background-color: transparent !important;
    }

    /* mavon-editor dark mode — dropdown menus */

    .v-note-wrapper .op-icon.dropdown-wrapper .dropdown-item {
        color: #e0e0e0 !important;
        background-color: #303030 !important;
    }

    .v-note-wrapper .op-icon.dropdown-wrapper .dropdown-item:hover {
        color: #fff !important;
        background-color: #424242 !important;
    }

    /* mavon-editor dark mode — scrollbar */

    .v-note-wrapper .scroll-style::-webkit-scrollbar {
        background-color: #333 !important;
    }

    .v-note-wrapper .scroll-style::-webkit-scrollbar-thumb {
        background-color: #555 !important;
    }

    /* markdown display (read-only view in StepView) */

    .markdown-body {
        color: #e0e0e0 !important;
    }

    .markdown-body a {
        color: #b98766 !important;
    }

    .markdown-body blockquote {
        background: rgba(255, 255, 255, 0.05) !important;
        border-left-color: #555 !important;
    }

    .markdown-body code {
        background-color: rgba(255, 255, 255, 0.1) !important;
        color: #e0e0e0 !important;
    }
}

.v-theme--light {
    a:not([class]) {
        color: #b98766;
        text-decoration: none;
        background-color: transparent
    }

    a:hover {
        color: #000;
        text-decoration: none
    }

    a:not([href]):not([tabindex]), a:not([href]):not([tabindex]):focus, a:not([href]):not([tabindex]):hover {
        color: inherit;
        text-decoration: none
    }

    a:not([href]):not([tabindex]):focus {
        outline: 0
    }

}

/* vueform/multiselect */

.multiselect-option.is-pointed {
    background: #b98766 !important;
}

.multiselect-option.is-selected {
    background: #b55e4f !important;
}

/* Browser printing also works without the dedicated ?print route. Vuetify's
   layout padding is inline, so reset it together with the hidden app shell. */
@media print {
    .v-app-bar, .v-navigation-drawer, .v-bottom-navigation, .v-bottom-sheet {
        display: none !important;
    }
    .v-main {
        padding: 0 !important;
    }
}

</style>
