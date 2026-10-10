<template>
    <v-form>
        <p class="text-h6">{{ $t('API') }}</p>
        <v-divider class="mb-3"></v-divider>

        <v-row>
            <database-link-col prepend-icon="fa-solid fa-terminal" :href="useDjangoUrls().getDjangoUrl('api')" :lg="6" :title="$t('API_Browser')"></database-link-col>
            <database-link-col prepend-icon="fa-solid fa-laptop-code" :href="useDjangoUrls().getDjangoUrl('/docs/api/')" :lg="6"
                               :title="$t('API_Documentation')"></database-link-col>
        </v-row>

        <v-row>
            <v-col>

                <v-alert color="error" variant="tonal">
                    La API permite a los desarrolladores interactuar con la aplicación.
                    Su uso puede modificar datos; crea una copia de seguridad antes de realizar cambios.
                    La definición de la API puede cambiar en futuras versiones. Consulta el registro de cambios antes de actualizar tus integraciones.
                </v-alert>
            </v-col>
        </v-row>

        <v-row>
            <v-col>
                Para autenticarte, utiliza la palabra <code>Bearer</code> seguida de una clave de API en la cabecera
                <code>Authorization</code> de la petición, como en estos ejemplos. <br/>
                <code>Authorization: Bearer TOKEN</code> o bien:<br/>
                <code>curl -X GET http://your.domain.com/api/recipe/ -H 'Authorization:
                    Bearer TOKEN'</code>

                <br/>
                <br/>
                Puedes crear varias claves y asignar a cada una su ámbito de acceso: <code>read</code> para lectura,
                <code>write</code> para escritura y <code>bookmarklet</code> para el marcador de importación del navegador.

                <v-alert color="warning" variant="tonal">Guarda la clave al crearla, ya que después no podrás volver a consultarla.</v-alert>
            </v-col>

        </v-row>

        <v-btn prepend-icon="$create" color="create" class="mt-2">{{ $t('New') }}
            <model-edit-dialog model="AccessToken" @create="loadAccessTokens()" :close-after-create="false"></model-edit-dialog>
        </v-btn>

        <v-list class="mt-2" border>
            <v-list-item v-for="at in accessTokenList">
                <v-list-item-title>{{ at.token }}</v-list-item-title>
                <v-list-item-subtitle>Ámbito: {{ at.scope }}
                    Caduca: {{ DateTime.fromJSDate(at.expires).toLocaleString(DateTime.DATE_FULL) }}
                </v-list-item-subtitle>
                <template #append>
                    <v-chip color="error" class="me-2" v-if="at.expires < DateTime.now().toJSDate()">Caducada</v-chip>
                    <v-btn color="edit">
                        <v-icon icon="$edit"></v-icon>
                        <model-edit-dialog model="AccessToken" :item="at" class="mt-2" @delete="loadAccessTokens()"></model-edit-dialog>
                    </v-btn>
                </template>
            </v-list-item>
        </v-list>


    </v-form>
</template>


<script setup lang="ts">

import {onMounted, ref} from "vue";
import {AccessToken, ApiApi} from "@/openapi";
import {ErrorMessageType, useMessageStore} from "@/stores/MessageStore";
import {DateTime} from "luxon";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";
import DatabaseLinkCol from "@/components/display/DatabaseLinkCol.vue";
import {useDjangoUrls} from "@/composables/useDjangoUrls.ts";

const accessTokenList = ref([] as AccessToken[])

onMounted(() => {
    loadAccessTokens()
})

function loadAccessTokens() {
    const api = new ApiApi()
    api.apiAccessTokenList().then(r => {
        accessTokenList.value = r
    }).catch(err => {
        useMessageStore().addError(ErrorMessageType.FETCH_ERROR, err)
    })
}

</script>

<style scoped>

</style>