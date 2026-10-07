<template>
    <v-dialog max-width="600px" v-model="dialog">
        <template #activator="{ props }">
            <v-list-item v-bind="props" prepend-icon="fa-solid fa-calendar-days" link>
                {{ $t('Calendar') }}
            </v-list-item>
        </template>
        <v-card :loading="loading">
            <v-closable-card-title v-model="dialog" :title="$t('Calendar')" icon="fa-solid fa-calendar-days"></v-closable-card-title>

            <v-card-text>
                <p class="mb-4">{{ $t('CalendarIcsHelp') }}</p>
                <v-text-field
                    v-if="apiToken"
                    :model-value="icalUrl"
                    :label="$t('Calendar_URL')"
                    readonly
                >
                    <template #append-inner>
                        <btn-copy icon variant="plain" color="" :copyValue="icalUrl"></btn-copy>
                    </template>
                </v-text-field>
                <v-alert v-if="tokenError" type="error" variant="tonal" class="mb-4" role="alert">
                    No se pudo preparar el enlace del calendario. Vuelve a intentarlo.
                </v-alert>
                <v-btn v-if="!apiToken" @click="loadOrCreateToken(true)" :loading="loading" :disabled="loading" color="primary">
                    {{ tokenError ? 'Reintentar' : 'Generar enlace del calendario' }}
                </v-btn>
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn prepend-icon="$download" :href="icalUrl" :disabled="!apiToken || loading">{{$t('Download')}}</v-btn>
                <v-btn @click="dialog = false">{{ $t('Close') }}</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script setup lang="ts">
import {computed, ref, watch} from 'vue';
import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import {AccessToken, ApiApi} from "@/openapi";
import BtnCopy from "@/components/buttons/BtnCopy.vue";
import {DateTime} from "luxon";
import {useDjangoUrls} from "@/composables/useDjangoUrls.ts";

const {getFullUrl} = useDjangoUrls()
const dialog = ref(false)
const loading = ref(false)
const tokenError = ref(false)
const apiToken = ref('')
let pendingTokenRequest: Promise<void> | undefined

const icalUrl = computed(() => apiToken.value
    ? getFullUrl('/api/meal-plan/ical/') + "?access_token=" + apiToken.value
    : '')

watch(dialog, open => {
    if (open) void loadOrCreateToken()
})

/** Opening reads existing tokens; only the explicit generation action may create one. */
function loadOrCreateToken(createIfMissing = false): Promise<void> {
    if (apiToken.value) return Promise.resolve()
    if (pendingTokenRequest) return pendingTokenRequest
    loading.value = true
    tokenError.value = false
    const api = new ApiApi()
    pendingTokenRequest = (async () => {
        try {
            const tokens = await api.apiAccessTokenList()
            const existing = tokens.filter(token => token.scope === 'mealplan' && typeof token.token === 'string' && token.token.length > 0).slice(-1)[0]
            if (existing) {
                apiToken.value = existing.token
            } else if (createIfMissing) {
                const token = await api.apiAccessTokenCreate({accessToken: {
                    scope: 'mealplan', expires: DateTime.now().plus({year: 100}).toJSDate()
                } as AccessToken})
                if (typeof token.token !== 'string' || token.token.length === 0) throw new Error('Enlace del calendario no disponible')
                apiToken.value = token.token
            }
        } catch {
            tokenError.value = true
        } finally {
            loading.value = false
        }
    })().finally(() => { pendingTokenRequest = undefined })
    return pendingTokenRequest
}
</script>
