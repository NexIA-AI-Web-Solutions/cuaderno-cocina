import {useI18n} from "vue-i18n";
import {VDivider, VListItem} from "vuetify/components";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore.ts";
import {useDjangoUrls} from "@/composables/useDjangoUrls.ts";
import {TANDOOR_PLUGINS} from "@/types/Plugins.ts";
import {ref} from 'vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {cuadernoNavigationCapabilities, type CuadernoEdition} from '@/cuaderno/navigationUi'

const navigationEdition = ref<CuadernoEdition | null>(null)
let navigationEditionSpace: number | null = null
let navigationEditionLoading = false
let navigationEditionRefresh: ReturnType<typeof setTimeout> | null = null

function loadNavigationEdition(spaceId: unknown) {
    if (!Number.isSafeInteger(spaceId) || Number(spaceId) <= 0) return
    const requestedSpace = Number(spaceId)
    if (navigationEditionLoading) {
        if (navigationEditionSpace !== requestedSpace) {
            navigationEditionSpace = requestedSpace
            navigationEdition.value = null
        }
        return
    }
    if (navigationEditionSpace !== requestedSpace) {
        if (navigationEditionRefresh !== null) clearTimeout(navigationEditionRefresh)
        navigationEdition.value = null
    }
    navigationEditionSpace = requestedSpace
    navigationEditionLoading = true
    cuadernoFetch('/api/cuaderno/edition/')
        .then(readJson)
        .then(result => {
            if (navigationEditionSpace !== requestedSpace) return
            navigationEdition.value = result.ok ? cuadernoNavigationCapabilities(result.data).edition : null
            scheduleNavigationEditionRefresh(requestedSpace, result.ok ? 60_000 : 5_000)
        })
        .catch(() => {
            if (navigationEditionSpace === requestedSpace) {
                navigationEdition.value = null
                scheduleNavigationEditionRefresh(requestedSpace, 5_000)
            }
        })
        .finally(() => {
            navigationEditionLoading = false
            if (navigationEditionSpace !== requestedSpace && navigationEditionSpace !== null) {
                loadNavigationEdition(navigationEditionSpace)
            }
        })
}

function scheduleNavigationEditionRefresh(spaceId: number, delay: number) {
    if (navigationEditionRefresh !== null) clearTimeout(navigationEditionRefresh)
    navigationEditionRefresh = setTimeout(() => {
        navigationEditionRefresh = null
        if (navigationEditionSpace === spaceId) loadNavigationEdition(spaceId)
    }, delay)
}

/**
 * manages configuration and loading of navigation entries for tandoor main app and plugins
 */
export function useNavigation() {
    const {t} = useI18n()

    function getNavigationDrawer() {
        const preferenceStore = useUserPreferenceStore()
        loadNavigationEdition(preferenceStore.activeSpace.id)
        const cuaderno = cuadernoNavigationCapabilities({edition: navigationEdition.value})
        let navigation = [
            {component: VListItem, prependIcon: '$recipes', title: t('Home'), to: {name: 'StartPage', params: {}}},
            ...(cuaderno.prices ? [{component: VListItem, prependIcon: 'fa-solid fa-euro-sign', title: 'Costes', to: {name: 'CuadernoPreciosPage', params: {}}}] : []),
            {component: VListItem, prependIcon: '$search', title: t('Search'), to: {name: 'SearchPage', params: {}}},
            ...(cuaderno.prices ? [{component: VListItem, prependIcon: 'fa-solid fa-heart', title: 'Favoritas', to: {name: 'CuadernoFavoritasPage', params: {}}}] : []),
            {component: VListItem, prependIcon: '$mealplan', title: t('Meal_Plan'), to: {name: 'MealPlanPage', params: {}}},
            ...(cuaderno.production ? [{component: VListItem, prependIcon: 'fa-solid fa-calendar-days', title: 'Planificación', to: {name: 'CuadernoPlanificacionPage', params: {}}}] : []),
            ...(cuaderno.production ? [{component: VListItem, prependIcon: 'fa-solid fa-clipboard-list', title: 'Producción', to: {name: 'CuadernoProduccionPage', params: {}}}] : []),
            ...(cuaderno.warehouse ? [{component: VListItem, prependIcon: 'fa-solid fa-warehouse', title: 'Almacén', to: {name: 'CuadernoAlmacenPage', params: {}}}] : []),
            {component: VListItem, prependIcon: '$shopping', title: t('Shopping'), to: {name: 'ShoppingListPage', params: {}}},
            ...(preferenceStore.canWriteNativeRecipes ? [{component: VListItem, prependIcon: 'fas fa-globe', title: t('Import'), to: {name: 'RecipeImportPage', params: {}}}] : []),
            {component: VListItem, prependIcon: '$pantry', title: t('Pantry'), to: {name: 'PantryPage', params: {}}},
            {component: VListItem, prependIcon: '$books', title: t('Books'), to: {name: 'BooksPage', params: {}}},
            {component: VListItem, prependIcon: 'fa-solid fa-folder-tree', title: t('Database'), to: {name: 'DatabasePage', params: {}}},
        ]

        TANDOOR_PLUGINS.forEach(plugin => {
            plugin.navigationDrawer.forEach(navEntry => {
                let navEntryCopy = Object.assign({}, navEntry)
                if ('title' in navEntryCopy) {
                    navEntryCopy.title = t(navEntryCopy.title)
                }
                navigation.push(navEntryCopy)
            })
        })

        return navigation
    }

    function getBottomNavigation() {
        const preferenceStore = useUserPreferenceStore()
        loadNavigationEdition(preferenceStore.activeSpace.id)
        const cuaderno = cuadernoNavigationCapabilities({edition: navigationEdition.value})
        let navigation = [
            {component: VListItem, prependIcon: 'fa-solid fa-sliders', title: t('Settings'), to: {name: 'SettingsPage', params: {}}},
            ...(cuaderno.prices ? [{component: VListItem, prependIcon: 'fa-solid fa-heart', title: 'Favoritas', to: {name: 'CuadernoFavoritasPage', params: {}}}] : []),
            ...(cuaderno.production ? [{component: VListItem, prependIcon: 'fa-solid fa-calendar-days', title: 'Planificación', to: {name: 'CuadernoPlanificacionPage', params: {}}}] : []),
            ...(cuaderno.prices ? [{component: VListItem, prependIcon: 'fa-solid fa-euro-sign', title: 'Costes', to: {name: 'CuadernoPreciosPage', params: {}}}] : []),
            ...(cuaderno.production ? [{component: VListItem, prependIcon: 'fa-solid fa-clipboard-list', title: 'Producción', to: {name: 'CuadernoProduccionPage', params: {}}}] : []),
            ...(cuaderno.warehouse ? [{component: VListItem, prependIcon: 'fa-solid fa-warehouse', title: 'Almacén', to: {name: 'CuadernoAlmacenPage', params: {}}}] : []),
            ...(preferenceStore.canWriteNativeRecipes ? [{component: VListItem, prependIcon: 'fas fa-globe', title: t('Import'), to: {name: 'RecipeImportPage', params: {}}}] : []),
            {component: VListItem, prependIcon: 'fa-solid fa-folder-tree', title: t('Database'), to: {name: 'DatabasePage', params: {}}},
            {component: VListItem, prependIcon: '$search', title: t('Search'), to: {name: 'SearchPage', params: {}}},
            {component: VListItem, prependIcon: '$pantry', title: t('Pantry'), to: {name: 'PantryPage', params: {}}},
            {component: VListItem, prependIcon: '$books', title: t('Books'), to: {name: 'BooksPage', params: {}}},
        ]

        TANDOOR_PLUGINS.forEach(plugin => {
            plugin.bottomNavigation.forEach(navEntry => {
                let navEntryCopy = Object.assign({}, navEntry)
                if ('title' in navEntryCopy) {
                    navEntryCopy.title = t(navEntryCopy.title)
                }
                navigation.push(navEntryCopy)
            })
        })

        return navigation
    }

    function getUserNavigation() {
        let navigation = []

        navigation.push({component: VListItem, prependIcon: 'fa-solid fa-sliders', title: t('Settings'), to: {name: 'SettingsPage', params: {}}})
        navigation.push({component: VListItem, prependIcon: 'fa-solid fa-question', title: t('Help'), to: {name: 'HelpPage', params: {}}})

        if (useUserPreferenceStore().userSettings.user.isSuperuser) {
            navigation.push({component: VListItem, prependIcon: 'fa-solid fa-shield', title: t('Admin'), href: useDjangoUrls().getDjangoUrl('admin')})
        }

        if (useUserPreferenceStore().spaces.length > 1) {
            navigation.push({component: VDivider})
            useUserPreferenceStore().spaces.forEach(space => {
                navigation.push({
                    component: VListItem,
                    prependIcon: (useUserPreferenceStore().activeSpace.id == space.id) ? 'fa-solid fa-circle-dot' : 'fa-solid fa-circle',
                    title: space.name,
                    onClick: () => {
                        useUserPreferenceStore().switchSpace(space)
                    }
                })
            })
            navigation.push({component: VDivider})
        }

        TANDOOR_PLUGINS.forEach(plugin => {
            plugin.userNavigation.forEach(navEntry => {
                let navEntryCopy = Object.assign({}, navEntry)
                if ('title' in navEntryCopy) {
                    navEntryCopy.title = t(navEntryCopy.title)
                }
                navigation.push(navEntryCopy)
            })
        })

        navigation.push({component: VListItem, prependIcon: 'fa-solid fa-arrow-right-from-bracket', title: t('Logout'), href: useDjangoUrls().getDjangoUrl('accounts/logout')})

        return navigation
    }

    return {getNavigationDrawer, getBottomNavigation, getUserNavigation}
}
