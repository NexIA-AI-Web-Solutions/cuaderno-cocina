<template>
    <v-container class="cuaderno-reservations-page">
        <h1 class="text-h5 mb-3">Reservas internas</h1>
        <p class="mb-4">Organiza comensales con los menús guardados. Reservar o confirmar no cambia las existencias. El paso a cocina prepara las fichas y registra la producción; en Integral consume los ingredientes disponibles.</p>
        <v-alert v-if="message" :type="conflict ? 'warning' : 'info'" variant="tonal" class="mb-3" role="status">{{ message }}</v-alert>
        <v-progress-linear v-if="loading" indeterminate aria-label="Cargando reservas" />
        <template v-if="enabled">
            <v-alert v-if="!canOperate" type="info" variant="tonal" class="mb-3">Modo Consulta: puedes revisar las reservas, el resumen y su historial.</v-alert>
            <v-alert v-if="canOperate && listLoaded && !canCreate && !loading" type="info" variant="tonal" class="mb-3">Necesitas un hogar operativo asignado para registrar reservas.</v-alert>
            <div class="d-flex flex-wrap ga-3 align-center mb-4">
                <v-text-field v-model="date" label="Fecha de las reservas" type="date" hide-details class="reservation-date" :disabled="busy" />
                <v-btn min-height="44" :disabled="busy || loading" @click="offset = 0; load()">Actualizar día</v-btn>
                <v-btn v-if="canCreate" color="primary" min-height="44" :disabled="busy" @click="create">Nueva reserva</v-btn>
                <v-btn :to="{name: 'CuadernoProduccionPage'}" min-height="44" variant="text">Ver producción</v-btn>
            </div>
            <section v-if="summary" aria-labelledby="reservation-summary-title" class="mb-5">
                <h2 id="reservation-summary-title" class="text-h6">Comensales pendientes del día: {{ summary.pending_covers }}</h2>
                <p class="text-body-2 mb-3">Pendientes de cocina: {{ summary.pending_covers }} · en cocina: {{ summary.in_kitchen_covers }} · total activo: {{ summary.total_active_covers }}. Solicitadas, servidas y anuladas quedan fuera.</p>
                <v-row>
                    <v-col v-for="group in summary.groups" :key="summaryGroupKey(group)" cols="12" md="6">
                        <v-card variant="tonal"><v-card-text>
                            <h3 class="text-subtitle-1">{{ group.template_name }} · día {{ group.template_day + 1 }} · {{ group.meal_type_name }}</h3>
                            <p>Confirmadas, pendientes de cocina: {{ group.confirmed_covers }}</p>
                            <p>En cocina: {{ group.in_kitchen_covers }}</p>
                            <p class="font-weight-bold">Pendientes de cocina: {{ group.pending_covers }} · total activo: {{ group.total_active_covers }}</p>
                            <h4 class="mt-3">Raciones por plato</h4>
                            <ul class="ml-5"><li v-for="(dish,index) in group.dishes || []" :key="index">{{ dish.course_name ? dish.course_name + ': ' : '' }}{{ dish.recipe_name }} — pendientes {{ dish.pending_servings }}, en cocina {{ dish.in_kitchen_servings }}, total {{ dish.total_active_servings }}</li></ul>
                            <h4 class="mt-3">Ingredientes pendientes consolidados</h4>
                            <p class="text-body-2">Necesidades congeladas de las confirmadas. La producción ya iniciada queda fuera para evitar contar sus ingredientes dos veces.</p>
                            <ul class="ml-5"><li v-for="(need,index) in group.needs || []" :key="index">{{ need.food_name }}: {{ need.quantity }} {{ need.unit_name || '(sin unidad)' }}</li></ul>
                            <p v-if="!group.needs?.length">No hay necesidades de ingredientes pendientes declaradas.</p>
                            <v-alert v-if="group.warnings?.length" type="warning" class="mt-3">Hay necesidades incompletas. Revisa las fichas de producción; una cantidad desconocida no se cuenta como cero.</v-alert>
                        </v-card-text></v-card>
                    </v-col>
                </v-row>
                <p v-if="!summary.groups.length">No hay comensales confirmados pendientes para este día.</p>
            </section>
            <section aria-labelledby="reservation-list-title">
                <h2 id="reservation-list-title" class="text-h6 mb-3">Reservas del día ({{ count }})</h2>
                <p v-if="!rows.length && !loading">No hay reservas para esta fecha.</p>
                <v-row>
                    <v-col v-for="row in rows" :key="row.id" cols="12" md="6">
                        <v-card>
                            <v-card-title class="reservation-wrap">{{ row.customer_name }}</v-card-title>
                            <v-card-text>
                                <v-chip class="mb-3">{{ reservationStateLabel(row.state) }}</v-chip>
                                <p>{{ row.service_date }} · {{ row.service_time }} · {{ row.covers }} comensales</p>
                                <p>{{ row.template_name }} · día {{ row.template_day + 1 }} · {{ row.meal_type_name }}</p>
                                <p v-if="row.phone">Teléfono: {{ row.phone }}</p><p v-if="row.email">Correo: {{ row.email }}</p>
                                <p v-if="row.note" class="reservation-wrap">{{ row.note }}</p>
                                <ul v-if="row.menu_snapshot?.dishes?.length" class="ml-5 mt-2"><li v-for="(dish,index) in row.menu_snapshot.dishes" :key="index">{{ dish.course_name ? dish.course_name + ': ' : '' }}{{ dish.recipe_name }}</li></ul>
                                <p v-if="row.services?.length" class="mt-3">Fichas de producción: {{ row.services.map(service => '#' + service.id).join(', ') }}</p>
                            </v-card-text>
                            <v-card-actions class="flex-wrap ga-2">
                                <v-btn min-height="44" :disabled="busy" @click="inspect(row)">Ver detalles e historial</v-btn>
                                <v-btn v-if="canOperate && row.can_edit && ['requested','confirmed'].includes(row.state)" min-height="44" :disabled="busy" @click="edit(row)">Editar</v-btn>
                                <v-btn v-for="action in actions(row)" :key="action" min-height="44" :disabled="busy" @click="openTransition(row, action)">{{ actionLabel(action) }}</v-btn>
                            </v-card-actions>
                        </v-card>
                    </v-col>
                </v-row>
                <div class="d-flex flex-wrap ga-3 mt-4"><v-btn :disabled="offset === 0 || loading || busy" @click="offset = Math.max(0, offset - limit); load()">Anterior</v-btn><p class="align-self-center">{{ count ? offset + 1 : 0 }}–{{ Math.min(offset + rows.length, count) }} de {{ count }}</p><v-btn :disabled="offset + rows.length >= count || loading || busy" @click="offset += limit; load()">Siguiente</v-btn></div>
            </section>
        </template>
        <v-dialog v-model="editorOpen" max-width="760" :persistent="busy">
            <v-card><v-card-title>{{ selected ? 'Editar reserva' : 'Nueva reserva' }}</v-card-title><v-card-text>
                <v-alert v-if="conflict" type="warning" class="mb-3">Otra persona cambió esta reserva. Tu borrador se conserva y no se puede guardar con la revisión anterior. Recarga la reserva para revisar su versión actual.</v-alert>
                <v-alert v-for="error in errors" :key="error" type="error" class="mb-2" role="alert">{{ error }}</v-alert>
                <v-text-field v-model="draft.customer_name" label="Cliente" maxlength="160" :disabled="busy" />
                <v-row dense><v-col cols="12" sm="6"><v-text-field v-model="draft.phone" label="Teléfono" type="tel" maxlength="64" :disabled="busy" /></v-col><v-col cols="12" sm="6"><v-text-field v-model="draft.email" label="Correo electrónico" type="email" maxlength="254" :disabled="busy" /></v-col></v-row>
                <p class="text-body-2 mb-3">Indica al menos un teléfono o un correo.</p>
                <v-row dense><v-col cols="12" sm="6"><v-text-field v-model="draft.service_date" label="Fecha del servicio" type="date" :disabled="busy" /></v-col><v-col cols="12" sm="6"><v-text-field v-model="draft.service_time" label="Hora del servicio" type="time" :disabled="busy" /></v-col></v-row>
                <v-select v-model="chosenMenu" :items="menuItems" label="Menú guardado, día y servicio" item-title="title" item-value="value" :disabled="busy || (selected !== null && (!canManage || !selected.can_change_menu))" />
                <p v-if="selected && !canManage" class="text-body-2 mb-3">El menú solo lo cambia Responsable.</p>
                <p v-if="!menus.length" class="text-body-2 mb-3">Guarda una plantilla con platos en Planificación para disponer de menús.</p>
                <v-text-field v-model="draft.covers" label="Número de comensales" inputmode="numeric" :disabled="busy" />
                <v-textarea v-model="draft.note" label="Nota de organización" maxlength="1000" :disabled="busy" />
                <v-textarea v-model="draft.reason" label="Motivo del registro o cambio" maxlength="1000" :disabled="busy" />
                <p v-if="selected">Revisión que estás editando: {{ selected.revision }}.</p>
            </v-card-text><v-card-actions class="flex-wrap ga-2"><v-btn min-height="44" :disabled="busy" @click="editorOpen = false">Volver</v-btn><v-btn v-if="conflict && selected" min-height="44" :disabled="busy" @click="reloadSelected">Recargar y sustituir borrador</v-btn><v-btn color="primary" min-height="44" :loading="busy" :disabled="!canOperate || conflict || busy" @click="save">{{ selected ? 'Guardar cambios' : 'Registrar reserva' }}</v-btn></v-card-actions></v-card>
        </v-dialog>
        <v-dialog :model-value="transition !== null" max-width="620" :persistent="busy" @update:model-value="value => { if (!value && !busy) transition = null }">
            <v-card v-if="transition"><v-card-title>{{ actionLabel(transition.action) }}</v-card-title><v-card-text>
                <p>{{ transition.row.customer_name }} · {{ transition.row.covers }} comensales · revisión {{ transition.row.revision }}.</p>
                <p v-if="transition.action === 'confirm'" class="mt-3">La confirmación conserva el menú y sus fichas sin descontar existencias.</p>
                <p v-if="transition.action === 'start_kitchen'" class="mt-3">Se registrará la producción de las fichas de esta reserva. En Integral se consumirán ingredientes de las existencias del hogar; si faltan existencias no se completará la acción. En Profesional se registra la producción sin movimientos de stock.</p>
                <p v-if="transition.action === 'cancel'" class="mt-3">La reserva quedará anulada conservando el historial. Si está en cocina se revertirá su producción y, en Integral, se compensarán los movimientos de existencias.</p>
                <v-textarea v-model="transitionReason" label="Motivo de la acción" maxlength="1000" :disabled="busy" class="mt-3" />
                <v-alert v-for="error in errors" :key="error" type="error" class="mb-2">{{ error }}</v-alert>
                <v-alert v-if="conflict" type="warning">La reserva ha cambiado. Cierra y actualiza el día para revisar la nueva versión; no se ha aplicado esta acción.</v-alert>
            </v-card-text><v-card-actions><v-btn :disabled="busy" min-height="44" @click="transition = null">Volver</v-btn><v-btn color="primary" min-height="44" :disabled="busy || conflict" :loading="busy" @click="applyTransition">Confirmar acción</v-btn></v-card-actions></v-card>
        </v-dialog>
        <v-dialog v-model="detailOpen" max-width="900"><v-card v-if="detail"><v-card-title>Historial de {{ detail.customer_name }}</v-card-title><v-card-text>
            <p>Estado: {{ reservationStateLabel(detail.state) }} · revisión {{ detail.revision }}.</p>
            <p v-if="!detail.history?.length">No hay entradas de historial disponibles.</p>
            <div v-for="entry in detail.history || []" :key="entry.revision" class="mt-4"><h3 class="text-subtitle-1">Revisión {{ entry.revision }} · {{ reservationHistoryAction(entry.action) }} · {{ reservationHistoryDate(entry.created_at) }}</h3><p>Motivo: {{ entry.reason }}</p><v-row><v-col cols="12" md="6"><h4>Antes</h4><pre class="reservation-history">{{ reservationHistoryText(entry.before) }}</pre></v-col><v-col cols="12" md="6"><h4>Después</h4><pre class="reservation-history">{{ reservationHistoryText(entry.after) }}</pre></v-col></v-row></div>
        </v-card-text><v-card-actions><v-btn min-height="44" @click="detailOpen = false">Cerrar</v-btn></v-card-actions></v-card></v-dialog>
    </v-container>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { cuadernoFetch, readJson } from '@/cuaderno/api';
import { editionOperationalRole } from '@/cuaderno/operationalRoleUi';
import { menuKey, summaryGroupKey, reservationHistoryAction, reservationHistoryText, reservationHistoryDate, reservationActions, reservationBody, reservationStateLabel, type MenuChoice, type ReservationAction, type ReservationDraft, type ReservationRow, type ReservationSummary } from '@/cuaderno/reservationsUi';
const today = () => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`; };
const date = ref(today()), rows = ref<ReservationRow[]>([]), menus = ref<MenuChoice[]>([]), summary = ref<ReservationSummary | null>(null);
const enabled = ref(false), canOperate = ref(false), canCreate = ref(false), listLoaded = ref(false), canManage = ref(false), loading = ref(false), busy = ref(false), message = ref(''), errors = ref<string[]>([]), conflict = ref(false);
const offset = ref(0), count = ref(0), limit = 50;
const selected = ref<ReservationRow | null>(null), editorOpen = ref(false), detailOpen = ref(false), detail = ref<ReservationRow | null>(null);
const transition = ref<{
    row: ReservationRow;
    action: ReservationAction;
} | null>(null), transitionReason = ref('');
const blank = (): ReservationDraft => ({ customer_name: '', phone: '', email: '', service_date: date.value, service_time: '13:00', covers: '', note: '', reason: '', menu: null });
const draft = reactive<ReservationDraft>(blank());
const chosenMenu = ref<string | null>(null);
const menuItems = computed(() => { const choices = [...menus.value]; if (selected.value && !choices.some(menu => menuKey(menu) === menuKey(selected.value!)))
    choices.push(selected.value); return choices.map(menu => ({ title: `${menu.template_name} · día ${menu.template_day + 1} · ${menu.meal_type_name}`, value: menuKey(menu) })); });
let generation = 0, controller: AbortController | null = null;
const actionLabel = (action: ReservationAction) => ({ confirm: 'Confirmar reserva', start_kitchen: 'Pasar a cocina', serve: 'Marcar servida', cancel: 'Anular reserva' })[action];
function actions(row: ReservationRow) { return reservationActions(row.state, canOperate.value && row.can_operate === true, canManage.value).filter(action => action !== 'cancel' || row.can_cancel); }
function fail(status: number, data: any) { conflict.value = status === 409; const fallback = status === 403 ? 'No tienes permiso para realizar esta acción.' : status === 409 ? 'La reserva cambió. Tu borrador se conserva; recarga antes de continuar.' : 'No se pudo completar la acción. Revisa los datos y reintenta.'; const detail = typeof data?.detail === 'string' ? data.detail : fallback; errors.value = [detail]; message.value = detail; }
function fill(row: ReservationRow) { selected.value = row; chosenMenu.value = menuKey(row); Object.assign(draft, { customer_name: row.customer_name, phone: row.phone, email: row.email, service_date: row.service_date, service_time: row.service_time.slice(0, 5), covers: String(row.covers), note: row.note, reason: '', menu: row }); errors.value = []; conflict.value = false; }
function create() { if (!canCreate.value || busy.value)
    return; selected.value = null; Object.assign(draft, blank()); chosenMenu.value = null; errors.value = []; conflict.value = false; editorOpen.value = true; }
function edit(row: ReservationRow) { if (!canOperate.value || !row.can_edit || !['requested', 'confirmed'].includes(row.state) || busy.value)
    return; fill(row); editorOpen.value = true; }
async function inspect(row: ReservationRow) { const response = await readJson(await cuadernoFetch(`/api/cuaderno/reservations/${row.id}/`)); if (!response.ok) {
    fail(response.status, response.data);
    return;
} detail.value = response.data; detailOpen.value = true; }
async function reloadSelected() { if (!selected.value || busy.value)
    return; busy.value = true; try {
    const response = await readJson(await cuadernoFetch(`/api/cuaderno/reservations/${selected.value.id}/`));
    if (!response.ok) {
        fail(response.status, response.data);
        return;
    }
    if (!response.data.can_edit || !['requested', 'confirmed'].includes(response.data.state)) {
        editorOpen.value = false;
        message.value = 'La reserva ya no admite cambios. Revisa su historial.';
        await load();
        return;
    }
    fill(response.data);
    message.value = 'Reserva recargada. Revisa los datos y escribe un nuevo motivo.';
}
finally {
    busy.value = false;
} }
async function load() { if (!enabled.value)
    return; const current = ++generation; controller?.abort(); controller = new AbortController(); loading.value = true; const options = { signal: controller.signal }; try {
    const request = async (path: string) => readJson(await cuadernoFetch(path, options));
    const responses = await Promise.all([
        request(`/api/cuaderno/reservations/?date=${encodeURIComponent(date.value)}&offset=${offset.value}&limit=${limit}`),
        request(`/api/cuaderno/reservations/summary/?date=${encodeURIComponent(date.value)}`),
        request('/api/cuaderno/reservations/menus/'),
    ]);
    if (current !== generation)
        return;
    const [list, daily, choices] = responses;
    if (!list.ok) {
        canCreate.value = false;
        listLoaded.value = false;
        rows.value = [];
        summary.value = null;
        fail(list.status, list.data);
        return;
    }
    listLoaded.value = true;
    canCreate.value = canOperate.value && list.data.can_operate === true;
    rows.value = Array.isArray(list.data.results) ? list.data.results : [];
    count.value = Number.isSafeInteger(list.data.count) ? list.data.count : 0;
    if (daily.ok && Array.isArray(daily.data.groups))
        summary.value = daily.data;
    else {
        summary.value = null;
        fail(daily.status, daily.data);
    }
    if (choices.ok && Array.isArray(choices.data.results))
        menus.value = choices.data.results;
    else {
        menus.value = [];
        fail(choices.status, choices.data);
    }
}
finally {
    if (current === generation)
        loading.value = false;
} }
async function save() { if (!canOperate.value || (!selected.value && !canCreate.value) || busy.value || conflict.value)
    return; draft.menu = menus.value.find(menu => menuKey(menu) === chosenMenu.value) || ((selected.value && menuKey(selected.value) === chosenMenu.value) ? selected.value : null); const result = reservationBody(draft); errors.value = result.errors; if (!result.body)
    return; const body: any = { ...result.body }; if (selected.value) {
    if (!selected.value.can_edit || !['requested', 'confirmed'].includes(selected.value.state))
        return;
    body.revision = selected.value.revision;
    if (!canManage.value || !selected.value.can_change_menu || chosenMenu.value === menuKey(selected.value)) {
        delete body.template;
        delete body.template_day;
        delete body.meal_type;
    }
    for (const key of ['customer_name', 'phone', 'email', 'service_date', 'service_time', 'covers', 'note'] as const) {
        const before = key === 'service_time' ? selected.value[key].slice(0, 5) : String(selected.value[key] ?? '');
        if (String(body[key]) === before)
            delete body[key];
    }
} busy.value = true; try {
    const path = selected.value ? `/api/cuaderno/reservations/${selected.value.id}/` : '/api/cuaderno/reservations/';
    const response = await readJson(await cuadernoFetch(path, { method: selected.value ? 'PATCH' : 'POST', body: JSON.stringify(body) }));
    if (!response.ok) {
        fail(response.status, response.data);
        return;
    }
    date.value = draft.service_date;
    offset.value = 0;
    editorOpen.value = false;
    message.value = 'Reserva guardada. Las existencias no han cambiado.';
    await load();
}
finally {
    busy.value = false;
} }
function openTransition(row: ReservationRow, action: ReservationAction) { if (!actions(row).includes(action) || busy.value)
    return; transition.value = { row, action }; transitionReason.value = ''; errors.value = []; conflict.value = false; }
async function applyTransition() { const pending = transition.value; if (!pending || busy.value || conflict.value || !actions(pending.row).includes(pending.action))
    return; const reason = transitionReason.value.trim(); if (!reason || reason.length > 1000) {
    errors.value = ['Indica un motivo de hasta 1000 caracteres.'];
    return;
} busy.value = true; try {
    const response = await readJson(await cuadernoFetch(`/api/cuaderno/reservations/${pending.row.id}/transition/`, { method: 'POST', body: JSON.stringify({ action: pending.action, revision: pending.row.revision, reason }) }));
    if (!response.ok) {
        fail(response.status, response.data);
        return;
    }
    transition.value = null;
    message.value = 'Acción registrada. Consulta las fichas y el historial para revisar el resultado.';
    await load();
}
finally {
    busy.value = false;
} }
onMounted(async () => { const response = await readJson(await cuadernoFetch('/api/cuaderno/edition/')); if (!response.ok) {
    fail(response.status, response.data);
    return;
} const role = editionOperationalRole(response.data); enabled.value = ['profesional', 'integral'].includes(response.data.edition); canOperate.value = enabled.value && role?.can_operate_cuaderno === true; canManage.value = enabled.value && role?.can_manage_edition === true; if (!enabled.value) {
    message.value = 'Las reservas internas están disponibles en Profesional e Integral.';
    return;
} await load(); });
onUnmounted(() => { generation++; controller?.abort(); });
</script>
<style scoped>
.reservation-date{max-width:260px;min-width:200px}.reservation-wrap{overflow-wrap:anywhere;white-space:normal}.reservation-history{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:rgb(var(--v-theme-surface-variant));padding:12px;border-radius:6px} .cuaderno-reservations-page :deep(.v-card-title){white-space:normal;overflow-wrap:anywhere}
</style>
