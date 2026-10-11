<template>
    <v-card v-if="canOperate" variant="outlined" class="mb-4">
        <details class="schedule-disclosure"><summary class="text-h6">Informes periódicos</summary>
        <v-card-text>
            <p class="text-body-2 mb-3">Guarda una revisión diaria o semanal para el trabajador y contexto seleccionados. Los informes programados son de solo lectura.</p>
            <v-alert v-if="!runnerActive" type="info" variant="tonal" class="mb-3">El ejecutor periódico no está activado. Guardar la programación no inicia revisiones automáticas. La persona que administra la instalación debe configurar su ejecución local.</v-alert>
            <v-select v-model="interval" :items="intervals" item-title="title" item-value="id" label="Intervalo previsto" :disabled="busy" hide-details class="mb-3" />
            <v-checkbox v-model="useExecutionDate" label="Usar fecha del día en cada ejecución" :disabled="busy" hide-details />
            <p class="text-body-2 mb-3">{{ useExecutionDate ? 'Cada revisión usa la fecha de ejecución y los intervalos predeterminados del informe.' : 'La programación conserva las fechas y el intervalo seleccionados en el formulario.' }}</p>
            <v-btn variant="outlined" min-height="44" block :loading="saving" :disabled="busy || !params" @click="createSchedule">Guardar programación</v-btn>
            <p v-if="validationError" class="text-body-2 mt-2">{{ validationError }}</p>
            <v-alert v-if="message" :type="succeeded ? 'success' : 'error'" variant="tonal" class="my-3" role="status">{{ message }}</v-alert>
            <v-progress-linear v-if="loading" indeterminate aria-label="Cargando programaciones" class="my-3" />
            <p v-if="!loading && !schedules.length" class="text-body-2 mt-3">No hay programaciones guardadas para tu cuenta.</p>
            <ul v-if="schedules.length" class="schedule-list mt-4">
                <li v-for="schedule in schedules" :key="schedule.id" class="mb-4">
                    <p class="font-weight-medium">{{ kindLabel(schedule.kind) }}</p>
                    <p class="text-body-2">{{ schedule.interval_hours === 24 ? 'Cada día' : 'Cada semana' }} · {{ schedule.enabled ? 'Habilitada' : 'En pausa' }}</p>
                    <p class="text-caption">Próxima fecha prevista: {{ dateLabel(schedule.next_run) }}</p>
                    <p v-if="schedule.last_run_id" class="text-caption">Último informe: #{{ schedule.last_run_id }}. Actualiza los informes recientes para consultarlo.</p>
                    <p v-if="schedule.last_error" class="text-body-2 mt-2" role="status">Última revisión: {{ schedule.last_error }}</p>
                    <details v-if="Object.keys(schedule.params).length" class="schedule-context"><summary>Contexto guardado</summary><worker-value :value="schedule.params" /></details>
                    <v-btn variant="text" min-height="44" :disabled="busy" @click="toggleSchedule(schedule)">{{ schedule.enabled ? 'Pausar' : 'Habilitar' }}</v-btn>
                </li>
            </ul>
            <v-btn variant="text" min-height="44" :disabled="busy" @click="loadSchedules">Actualizar programaciones</v-btn>
        </v-card-text>
        </details>
    </v-card>
</template>
<script setup lang="ts">
import {computed, onBeforeUnmount, ref, watch} from 'vue'
import {cuadernoFetch, readJson} from '@/cuaderno/api'
import {apiError} from '@/cuaderno/forms'
import {WORKER_KINDS, workerScheduleBody, workerScheduleRows, type WorkerKind, type WorkerSchedule} from '@/cuaderno/workerUi'
import WorkerValue from '@/cuaderno/components/WorkerValue.vue'
const props = defineProps<{kind: WorkerKind; params: Record<string, unknown> | null; canOperate: boolean; validationError?: string}>()
const schedules = ref<WorkerSchedule[]>([]), interval = ref(24), useExecutionDate = ref(true)
const loading = ref(false), saving = ref(false), runnerActive = ref(false), succeeded = ref(false), message = ref('')
const busy = computed(() => loading.value || saving.value)
const intervals = [{id: 24, title: 'Cada día (24 horas)'}, {id: 168, title: 'Cada semana (168 horas)'}]
let disposed = false
onBeforeUnmount(() => {disposed = true})
watch(() => props.canOperate, enabled => {if (enabled) loadSchedules()}, {immediate: true})
function kindLabel(kind: WorkerKind) {return WORKER_KINDS.find(item => item.id === kind)?.title ?? kind}
function dateLabel(value: string) {return new Date(value).toLocaleString('es-ES')}
async function loadSchedules() {
    if (busy.value || !props.canOperate) return
    loading.value = true; message.value = ''
    try {
        const response = await readJson(await cuadernoFetch('/api/cuaderno/workers/schedules/'))
        if (disposed) return
        if (!response.ok) {succeeded.value = false; message.value = apiError(response.status, response.data); return}
        const parsed = workerScheduleRows(response.data)
        if (!parsed) {succeeded.value = false; message.value = 'No se pudieron confirmar las programaciones. Actualiza para reintentar.'; return}
        schedules.value = parsed; runnerActive.value = response.data.runner_active === true
    } finally {if (!disposed) loading.value = false}
}
async function createSchedule() {
    if (busy.value || !props.canOperate) return
    const body = workerScheduleBody(props.kind, props.params, interval.value, useExecutionDate.value)
    if (!body) {succeeded.value = false; message.value = props.validationError || 'Revisa el contexto del informe antes de programarlo.'; return}
    await saveSchedule('/api/cuaderno/workers/schedules/', body)
}
async function toggleSchedule(schedule: WorkerSchedule) {
    if (busy.value || !props.canOperate) return
    await saveSchedule(`/api/cuaderno/workers/schedules/${schedule.id}/`, {enabled: !schedule.enabled}, schedule.id)
}
async function saveSchedule(url: string, body: Record<string, unknown>, expectedId?: number) {
    saving.value = true; message.value = ''; succeeded.value = false
    try {
        const response = await readJson(await cuadernoFetch(url, {method: 'POST', body: JSON.stringify(body)}))
        if (disposed) return
        if (!response.ok) {message.value = apiError(response.status, response.data); return}
        const row = workerScheduleRows({schedules: [response.data]})?.[0]
        if (!row || (expectedId !== undefined && row.id !== expectedId)) {message.value = 'El servidor no confirmó la programación. Actualiza antes de reintentar.'; return}
        schedules.value = [row, ...schedules.value.filter(previous => previous.id !== row.id)]
        succeeded.value = true; message.value = row.enabled ? 'Programación guardada. La ejecución depende del ejecutor local.' : 'Programación en pausa.'
    } finally {if (!disposed) saving.value = false}
}
</script>
<style scoped>
.schedule-list {list-style: none; padding: 0;}
.schedule-disclosure > summary {cursor: pointer; min-height: 44px; padding: 16px;}
.schedule-disclosure > summary:focus-visible {outline: 3px solid rgb(var(--v-theme-primary)); outline-offset: -3px;}
.schedule-list > li {padding-bottom: 12px; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .15);}
.schedule-context summary {cursor: pointer; min-height: 44px; display: flex; align-items: center; text-decoration: underline;}
.schedule-context summary:focus-visible {outline: 3px solid rgb(var(--v-theme-primary)); outline-offset: 2px;}
</style>
