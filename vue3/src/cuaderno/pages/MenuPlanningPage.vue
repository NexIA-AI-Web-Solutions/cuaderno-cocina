<template>
    <v-container class="menu-planning">
        <div class="d-print-none">
            <v-btn :to="{name: 'MealPlanPage'}" variant="text" prepend-icon="fa-solid fa-calendar-days" class="mb-3">Abrir calendario de comidas</v-btn>
            <h1 class="text-h4 mb-2">Organización de menús</h1>
            <p class="mb-4">Guarda periodos del calendario como plantillas, organiza tipos de plato y anota eventos del equipo.</p>
            <v-alert v-if="error" type="error" role="alert" class="mb-4">{{ error }}</v-alert>
            <v-alert v-if="notice" type="info" role="status" class="mb-4">{{ notice }}</v-alert>
            <v-progress-linear v-if="loading || loadingTemplates" indeterminate aria-label="Cargando planificación" />
            <p v-if="editionChecked && !enabled" class="my-4">La organización profesional de menús está disponible en Profesional e Integral. El calendario de comidas sigue disponible en todas las ediciones.</p>
            <template v-if="enabled">
                <v-row align="center"><v-col cols="12" sm="4"><v-text-field v-model="startDate" label="Primer día" type="date" :disabled="busy" /></v-col><v-col cols="6" sm="3"><v-select v-model="weeks" :items="[1,2,3,4,5]" label="Semanas" :disabled="busy" /></v-col><v-col cols="6" sm="5"><v-btn :loading="loading" :disabled="busy || loadingTemplates" @click="loadPeriod">Actualizar periodo</v-btn></v-col></v-row>
                <p class="mb-4">Periodo cargado: {{ loadedStart || 'pendiente' }} — {{ loadedEnd || 'pendiente' }}. Crear o aplicar una plantilla no descuenta existencias.</p>
                <v-tabs v-model="tab" show-arrows><v-tab value="templates">Plantillas</v-tab><v-tab value="courses">Tipos de plato</v-tab><v-tab value="events">Eventos y ausencias</v-tab><v-tab value="print">Impresión</v-tab></v-tabs>
                <v-tabs-window v-model="tab" class="mt-4">
                    <v-tabs-window-item value="templates">
                        <v-card class="mb-4" title="Guardar el periodo como plantilla">
                            <v-card-text><p class="mb-3">Usa el calendario de comidas para añadir o modificar recetas. Se guardarán los platos visibles del periodo cargado, conservando receta, raciones, día, comida y tipo de plato.</p><v-text-field v-model="templateName" label="Nombre de la plantilla" maxlength="120" :disabled="!canEdit || busy" /><v-btn color="primary" :disabled="!canEdit || busy || !templateName.trim() || !planning?.meal_plans.length" :loading="busy" @click="saveTemplate">Guardar nueva plantilla</v-btn></v-card-text>
                        </v-card>
                        <v-card v-for="template in templates" :key="template.id" class="mb-3">
                            <v-card-title class="text-wrap">{{ template.name }}</v-card-title>
                            <v-card-text><p>{{ template.weeks }} semanas · {{ template.entries.length }} platos</p><v-expansion-panels class="mt-3"><v-expansion-panel title="Ver platos"><v-expansion-panel-text><v-list density="compact"><v-list-item v-for="(entry,index) in template.entries" :key="index" :title="entry.recipe_name || entry.title || 'Plato sin receta'" :subtitle="`Día ${entry.day_index + 1} · ${entry.meal_type_name || 'Comida'} · ${entry.servings} raciones`" /></v-list></v-expansion-panel-text></v-expansion-panel></v-expansion-panels></v-card-text>
                            <v-card-actions class="flex-wrap"><v-btn :disabled="!canEdit || busy" color="primary" @click="applyTarget = template; applyDate = startDate; overwrite = false">Aplicar al calendario</v-btn><v-btn :disabled="!canEdit || busy" @click="renameTarget = template; renameValue = template.name">Cambiar nombre</v-btn><v-btn :disabled="!canEdit || busy" color="error" @click="deleteTarget = template">Eliminar plantilla</v-btn></v-card-actions>
                        </v-card>
                        <p v-if="!templates.length && !loading">Todavía no hay plantillas guardadas.</p>
                        <div v-if="templateCount > 50" class="d-flex flex-wrap align-center ga-3 my-3"><v-btn :disabled="busy || loading || loadingTemplates || templateOffset === 0" @click="loadTemplatePage(templateOffset - 50)">Plantillas anteriores</v-btn><span>{{ templateOffset + 1 }}–{{ templateOffset + templates.length }} de {{ templateCount }}</span><v-btn :disabled="busy || loading || loadingTemplates || templateOffset + templates.length >= templateCount" @click="loadTemplatePage(templateOffset + 50)">Más plantillas</v-btn></div>
                    </v-tabs-window-item>
                    <v-tabs-window-item value="courses">
                        <v-card title="Tipos de plato" class="mb-4"><v-card-text><p class="mb-3">Por ejemplo: primero, segundo y postre. Cada tipo pertenece a una comida del calendario.</p><v-text-field v-model="courseName" label="Nombre" :disabled="!canEdit || busy" /><v-model-select v-if="canEdit" v-model="courseMealType" model="MealType" label="Comida" search-on-load :disabled="busy" /><v-text-field v-else label="Comida" disabled /><v-text-field v-model="coursePosition" label="Orden" type="number" min="0" :disabled="!canEdit || busy" /><v-btn color="primary" :disabled="!canEdit || busy || !courseName.trim() || !courseMealType?.id" @click="saveCourse">{{ editingCourse ? 'Guardar tipo de plato' : 'Añadir tipo de plato' }}</v-btn><v-btn v-if="editingCourse" variant="text" :disabled="busy" @click="resetCourse">Cancelar edición</v-btn></v-card-text></v-card>
                        <v-list><v-list-item v-for="course in planning?.courses || []" :key="course.id" :title="course.name" :subtitle="'Orden ' + course.position"><template #append><v-btn variant="text" :disabled="!canEdit || busy" @click="editCourse(course)">Editar</v-btn><v-btn variant="text" color="error" :disabled="!canEdit || busy" @click="deleteCourse = course">Eliminar</v-btn></template></v-list-item></v-list>
                        <h2 class="text-h6 mt-5 mb-3">Asignar tipos a los platos del calendario</h2>
                        <v-card v-for="meal in planning?.meal_plans || []" :key="meal.id" class="mb-2"><v-card-text><strong>{{ meal.recipe?.name || meal.title }}</strong><p>{{ meal.from_date.slice(0,10) }} · {{ meal.meal_type.name }}</p><v-select :model-value="meal.course" :items="planning?.courses.filter(course => course.meal_type === meal.meal_type.id) || []" item-title="name" item-value="id" label="Tipo de plato" clearable :disabled="!canEdit || busy" @update:model-value="value => assignCourse(meal.id, value)" /></v-card-text></v-card>
                    </v-tabs-window-item>
                    <v-tabs-window-item value="events">
                        <v-card :title="editingEvent ? 'Editar anotación' : 'Nueva anotación'" class="mb-4"><v-card-text>
                            <v-select v-model="eventDraft.kind" :items="eventKinds" item-title="label" item-value="value" label="Tipo" :disabled="!canEdit || busy" />
                            <v-text-field v-model="eventDraft.title" label="Título" :disabled="!canEdit || busy" maxlength="128" />
                            <v-text-field v-if="eventDraft.kind === 'absence'" v-model="eventDraft.member_name" label="Persona del equipo" :disabled="!planning?.can_manage_absences || busy" maxlength="120" />
                            <v-row><v-col cols="12" sm="6"><v-text-field v-model="eventDraft.start_date" label="Desde" type="date" :disabled="!canEdit || busy" /></v-col><v-col cols="12" sm="6"><v-text-field v-model="eventDraft.end_date" label="Hasta" type="date" :disabled="!canEdit || busy" /></v-col></v-row>
                            <v-textarea v-model="eventDraft.note" label="Notas de organización" :disabled="!canEdit || busy" maxlength="1000" rows="2" />
                            <p class="text-body-2 mb-3">Anota solo lo necesario para organizar el trabajo. Las ausencias las gestiona Responsable.</p>
                            <v-btn color="primary" :disabled="!canEdit || busy || !eventDraft.title.trim() || (eventDraft.kind === 'absence' && !planning?.can_manage_absences)" @click="saveEvent">Guardar anotación</v-btn><v-btn v-if="editingEvent" variant="text" :disabled="busy" @click="resetEvent">Cancelar edición</v-btn>
                        </v-card-text></v-card>
                        <v-card v-for="event in planning?.events || []" :key="event.id" class="mb-3"><v-card-title class="text-wrap">{{ event.kind === 'absence' ? 'Ausencia · ' : '' }}{{ event.title }}</v-card-title><v-card-text><p>{{ event.start_date }} — {{ event.end_date }} <span v-if="event.member_name">· {{ event.member_name }}</span></p><p>{{ event.note }}</p></v-card-text><v-card-actions><v-btn :disabled="!canEdit || busy || (event.kind === 'absence' && !planning?.can_manage_absences)" @click="editEvent(event)">Editar</v-btn><v-btn color="error" :disabled="!canEdit || busy || (event.kind === 'absence' && !planning?.can_manage_absences)" @click="deleteEvent = event">Eliminar</v-btn></v-card-actions></v-card>
                    </v-tabs-window-item>
                    <v-tabs-window-item value="print">
                        <v-alert type="info" variant="tonal" class="mb-3">La impresión usa los platos autorizados que devuelve el servidor. Las dietas son declaraciones manuales; lo desconocido se muestra como «No declarado».</v-alert>
                        <v-text-field v-model="printName" label="Nombre del menú" maxlength="120" />
                        <v-select v-model="printSelection" :items="mealChoices" label="Platos del periodo" multiple chips item-title="label" item-value="id" />
                        <v-btn :disabled="busy || !printSelection.length || !printName.trim() || printGroups.length >= (planning?.can_merge_print ? 5 : 1)" @click="addPrintGroup">Añadir menú a la impresión</v-btn>
                        <v-list class="my-3"><v-list-item v-for="(group,index) in printGroups" :key="index" :title="group.name" :subtitle="group.meal_plan_ids.length + ' platos'"><template #append><v-btn variant="text" :aria-label="'Quitar menú ' + group.name" @click="printGroups.splice(index,1)">Quitar</v-btn></template></v-list-item></v-list>
                        <p v-if="!planning?.can_merge_print" class="mb-3">Profesional imprime un menú. Integral permite reunir hasta cinco menús en un documento.</p>
                        <v-select v-model="orientation" :items="[{value:'portrait',label:'Vertical'},{value:'landscape',label:'Horizontal'}]" item-title="label" item-value="value" label="Orientación" />
                        <v-select v-model="printDiet" :items="dietOptions" item-title="label" item-value="slug" label="Declaración dietética en el documento (opcional)" clearable />
                        <v-btn color="primary" :disabled="busy || !printGroups.length" :loading="busy" @click="preparePrint">Preparar documento</v-btn>
                    </v-tabs-window-item>
                </v-tabs-window>
                <p v-if="planning && !canEdit" class="mt-4">Modo Consulta: puedes revisar los menús e imprimirlos. Los cambios los realiza Cocina o Responsable.</p>
            </template>
        </div>
        <section v-if="printed" class="menu-print-document mt-5" aria-label="Documento de menús">
            <div class="d-flex flex-wrap ga-2 mb-4 d-print-none"><v-btn color="primary" prepend-icon="fa-solid fa-print" @click="printDocument">Imprimir {{ printed.orientation === 'landscape' ? 'en horizontal' : 'en vertical' }}</v-btn><v-btn variant="text" @click="printed = null">Cerrar documento</v-btn></div>
            <article v-for="(menu,index) in printed.menus" :key="index" class="menu-sheet mb-5"><h2 class="text-h5 mb-3">{{ menu.name }}</h2><p class="text-body-2 mb-3">{{ printed.declaration }}</p><p v-if="printed.diet" class="mb-3">Declaración consultada: {{ printed.diet_label || printed.diet }}</p><table class="menu-print-table"><thead><tr><th>Fecha / comida</th><th>Plato</th><th>Raciones</th><th v-if="printed.diet">Declaración</th></tr></thead><tbody><tr v-for="entry in menu.entries" :key="entry.id" :class="{'menu-diet-unsuitable': printed.diet && entry.diet_status === 'unsuitable'}"><td>{{ entry.from_date.slice(0,10) }}<br>{{ entry.meal_type.name }}<span v-if="entry.course_name"><br>{{ entry.course_name }}</span></td><td>{{ entry.recipe?.name || entry.title }}</td><td>{{ entry.servings }}</td><td v-if="printed.diet">{{ dietPresentation(entry.diet_status).label }}</td></tr></tbody></table></article>
        </section>
        <v-dialog :model-value="applyTarget !== null" max-width="560" @update:model-value="value => {if (!value && !busy) applyTarget = null}"><v-card v-if="applyTarget" title="Aplicar plantilla al calendario"><v-card-text><p class="mb-3">{{ applyTarget?.name }} · {{ applyTarget?.weeks }} semanas. Se crearán platos en el calendario de comidas.</p><v-text-field v-model="applyDate" label="Primer día de la plantilla" type="date" :disabled="busy" /><v-checkbox v-model="overwrite" :disabled="busy" label="Sustituir solo mi aplicación anterior de esta misma plantilla y fecha" /><p class="text-body-2">No se sustituyen otros platos ni entradas vinculadas a compras o producción.</p></v-card-text><v-card-actions><v-btn :disabled="busy" @click="applyTarget = null">Cancelar</v-btn><v-btn color="primary" :loading="busy" :disabled="!canEdit || busy" @click="applyTemplate">Aplicar plantilla</v-btn></v-card-actions></v-card></v-dialog>
        <v-dialog :model-value="renameTarget !== null" max-width="440" @update:model-value="value => {if (!value && !busy) renameTarget = null}"><v-card title="Cambiar nombre"><v-card-text><v-text-field v-model="renameValue" label="Nombre" maxlength="120" :disabled="busy" /></v-card-text><v-card-actions><v-btn :disabled="busy" @click="renameTarget = null">Cancelar</v-btn><v-btn :loading="busy" :disabled="!renameValue.trim()" @click="renameTemplate">Guardar</v-btn></v-card-actions></v-card></v-dialog>
        <v-dialog :model-value="Boolean(deleteTarget || deleteCourse || deleteEvent)" max-width="460" persistent><v-card title="Confirmar eliminación"><v-card-text>{{ deleteTarget ? 'Se eliminará la plantilla, sin borrar los platos ya creados en el calendario.' : deleteCourse ? 'Se eliminará este tipo de plato si no tiene referencias que lo impidan.' : 'Se eliminará esta anotación del calendario.' }}</v-card-text><v-card-actions><v-btn :disabled="busy" @click="deleteTarget = null; deleteCourse = null; deleteEvent = null">Cancelar</v-btn><v-btn color="error" :loading="busy" @click="confirmDelete">Eliminar</v-btn></v-card-actions></v-card></v-dialog>
    </v-container>
</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref} from 'vue'
import {DateTime} from 'luxon'
import VModelSelect from '@/components/inputs/VModelSelect.vue'
import {dietOptions, planningRequest, type PlanningData, type MenuTemplate, type PlanningCourse, type PlanningEvent, type PrintedMenus} from '@/cuaderno/planningApi'
import {planningEndDate, templateEntriesFromPlans, dietPresentation} from '@/cuaderno/planningUi.mjs'
const enabled = ref(false), editionChecked = ref(false), loading = ref(false), busy = ref(false), error = ref(''), notice = ref(''), tab = ref('templates')
const startDate = ref(DateTime.local().toISODate()!), weeks = ref(1), loadedStart = ref(''), loadedEnd = ref(''), loadedWeeks = ref(1)
const planning = ref<PlanningData | null>(null), templates = ref<MenuTemplate[]>([]), templateName = ref('')
const templateOffset = ref(0), templateCount = ref(0), loadingTemplates = ref(false)
const canEdit = computed(() => planning.value?.can_edit === true)
const applyTarget = ref<MenuTemplate | null>(null), applyDate = ref(startDate.value), overwrite = ref(false)
const renameTarget = ref<MenuTemplate | null>(null), renameValue = ref(''), deleteTarget = ref<MenuTemplate | null>(null)
const courseRevision = ref(''), eventRevision = ref('')
const courseName = ref(''), courseMealType = ref<{id?: number; name?: string} | undefined>(), coursePosition = ref('0'), editingCourse = ref<number | null>(null), deleteCourse = ref<PlanningCourse | null>(null)
const blankEvent = () => ({kind: 'event' as 'event' | 'absence', title: '', member_name: '', start_date: startDate.value, end_date: startDate.value, note: ''})
const eventDraft = ref(blankEvent()), editingEvent = ref<number | null>(null), deleteEvent = ref<PlanningEvent | null>(null)
const eventKinds = computed(() => [{value: 'event', label: 'Evento'}, ...(planning.value?.can_manage_absences ? [{value: 'absence', label: 'Ausencia'}] : [])])
const orientation = ref<'portrait' | 'landscape'>('portrait'), printed = ref<PrintedMenus | null>(null), printName = ref('Menú'), printSelection = ref<number[]>([]), printGroups = ref<{name: string; meal_plan_ids: number[]}[]>([])
const printDiet = ref<string | null>(null)
const mealChoices = computed(() => (planning.value?.meal_plans || []).map(meal => ({id: meal.id, label: `${meal.from_date.slice(0,10)} · ${meal.meal_type.name} · ${meal.recipe?.name || meal.title}`})))
let printStyle: HTMLStyleElement | null = null
async function loadPeriod() {
    if (!enabled.value || loading.value || loadingTemplates.value) return
    loading.value = true; error.value = ''; planning.value = null
    try {
        const start = startDate.value, count = weeks.value, end = planningEndDate(start, count)
        const [data, saved] = await Promise.all([planningRequest<PlanningData>(`planning/?from_date=${start}&to_date=${end}`), planningRequest<{count: number; results: MenuTemplate[]}>('planning/templates/?offset=0&limit=50')])
        planning.value = data; templates.value = saved.results; templateOffset.value = 0; templateCount.value = saved.count; loadedStart.value = start; loadedEnd.value = end; loadedWeeks.value = count
    } catch (failure) {error.value = (failure as Error).message} finally {loading.value = false}
}
async function loadTemplatePage(offset: number) {
    if (loadingTemplates.value || loading.value || busy.value || offset < 0 || offset >= templateCount.value) return
    loadingTemplates.value = true; error.value = ''
    try {
        const page = await planningRequest<{count: number; results: MenuTemplate[]}>(`planning/templates/?offset=${offset}&limit=50`)
        templates.value = page.results; templateCount.value = page.count; templateOffset.value = offset
    } catch (failure) {error.value = (failure as Error).message} finally {loadingTemplates.value = false}
}
async function mutate(action: () => Promise<void>, message: string, refresh = true) {
    if (busy.value || loading.value || loadingTemplates.value) return
    busy.value = true; error.value = ''; notice.value = ''
    try {await action(); if (refresh) await loadPeriod(); notice.value = message} catch (failure) {error.value = (failure as Error).message} finally {busy.value = false}
}
function saveTemplate() {
    if (!canEdit.value || !planning.value) return
    return mutate(async () => {const entries = templateEntriesFromPlans(planning.value!.meal_plans, loadedStart.value, loadedWeeks.value); await planningRequest('planning/templates/', 'POST', {name: templateName.value.trim(), weeks: loadedWeeks.value, entries}); templateName.value = ''}, 'Plantilla guardada.')
}
function applyTemplate() {
    if (!canEdit.value || !applyTarget.value) return
    const template = applyTarget.value
    return mutate(async () => {await planningRequest(`planning/templates/${template.id}/apply/`, 'POST', {revision: template.revision, start_date: applyDate.value, overwrite: overwrite.value}); applyTarget.value = null}, 'Plantilla aplicada al calendario de comidas.')
}
function renameTemplate() {
    if (!canEdit.value || !renameTarget.value) return
    const template = renameTarget.value
    return mutate(async () => {await planningRequest(`planning/templates/${template.id}/`, 'PUT', {revision: template.revision, name: renameValue.value.trim(), weeks: template.weeks, entries: template.entries.map(({day_index, meal_type, course, recipe, title, source_url, servings}) => ({day_index, meal_type, course, recipe, title, source_url, servings}))}); renameTarget.value = null}, 'Nombre actualizado.')
}
function resetCourse() {editingCourse.value = null; courseRevision.value = '';  courseName.value = ''; courseMealType.value = undefined; coursePosition.value = '0'}
function editCourse(course: PlanningCourse) {editingCourse.value = course.id; courseRevision.value = course.revision; courseName.value = course.name; courseMealType.value = {id: course.meal_type, name: 'Comida guardada'}; coursePosition.value = String(course.position)}
function saveCourse() {
    if (!canEdit.value || !courseMealType.value?.id) return
    const position = Number(coursePosition.value)
    if (!Number.isSafeInteger(position) || position < 0) {error.value = 'El orden debe ser un número entero no negativo.'; return}
    return mutate(async () => {await planningRequest(`planning/courses/${editingCourse.value ? editingCourse.value + '/' : ''}`, editingCourse.value ? 'PUT' : 'POST', {name: courseName.value.trim(), meal_type: courseMealType.value!.id, position, ...(editingCourse.value ? {revision: courseRevision.value} : {})}); resetCourse()}, 'Tipo de plato guardado.')
}
function assignCourse(id: number, course: number | null) {
    if (!canEdit.value) return
    return mutate(async () => {
        const saved = await planningRequest<PlanningData['meal_plans'][number]>(`planning/meal-plans/${id}/`, 'PUT', {course: course ?? null})
        // The server returns the authorized row; avoid a reload that navigation would cancel.
        if (planning.value) planning.value.meal_plans = planning.value.meal_plans.map(meal => meal.id === id ? saved : meal)
    }, 'Tipo de plato asignado.', false)
}
function resetEvent() {editingEvent.value = null; eventRevision.value = '';  eventDraft.value = blankEvent()}
function editEvent(event: PlanningEvent) {editingEvent.value = event.id; const {id, revision, ...draft} = event; eventRevision.value = revision; eventDraft.value = {...draft}}
function saveEvent() {
    if (!canEdit.value || (eventDraft.value.kind === 'absence' && !planning.value?.can_manage_absences)) return
    return mutate(async () => {await planningRequest(`planning/events/${editingEvent.value ? editingEvent.value + '/' : ''}`, editingEvent.value ? 'PUT' : 'POST', {...eventDraft.value, ...(editingEvent.value ? {revision: eventRevision.value} : {}), member_name: eventDraft.value.kind === 'absence' ? eventDraft.value.member_name : ''}); resetEvent()}, 'Anotación guardada.')
}
function confirmDelete() {
    if (!canEdit.value || (deleteEvent.value?.kind === 'absence' && !planning.value?.can_manage_absences)) return
    return mutate(async () => {
        if (deleteTarget.value) await planningRequest(`planning/templates/${deleteTarget.value.id}/?revision=${encodeURIComponent(deleteTarget.value.revision)}`, 'DELETE')
        else if (deleteCourse.value) await planningRequest(`planning/courses/${deleteCourse.value.id}/?revision=${encodeURIComponent(deleteCourse.value.revision)}`, 'DELETE')
        else if (deleteEvent.value) await planningRequest(`planning/events/${deleteEvent.value.id}/?revision=${encodeURIComponent(deleteEvent.value.revision)}`, 'DELETE')
        deleteTarget.value = null; deleteCourse.value = null; deleteEvent.value = null
    }, 'Eliminado.')
}
function addPrintGroup() {
    if (!planning.value || !printSelection.value.length || printSelection.value.length > 100 || printGroups.value.length >= (planning.value.can_merge_print ? 5 : 1)) return
    printGroups.value.push({name: printName.value.trim(), meal_plan_ids: [...new Set(printSelection.value)]}); printSelection.value = []
}
async function preparePrint() {
    if (busy.value || !planning.value || !printGroups.value.length) return
    busy.value = true; error.value = ''; printed.value = null
    try {printed.value = await planningRequest<PrintedMenus>('planning/print/', 'POST', {orientation: orientation.value, menus: printGroups.value, ...(printDiet.value ? {diet: printDiet.value} : {})})}
    catch (failure) {error.value = (failure as Error).message} finally {busy.value = false}
}
function printDocument() {
    if (!printed.value) return
    printStyle?.remove(); printStyle = document.createElement('style'); printStyle.textContent = `@page {size: A4 ${printed.value.orientation === 'landscape' ? 'landscape' : 'portrait'}; margin: 12mm}`; document.head.append(printStyle); window.print()
}
onBeforeUnmount(() => printStyle?.remove())
onMounted(async () => {
    loading.value = true
    try {const edition = await planningRequest<{edition: string}>('edition/'); enabled.value = ['profesional', 'integral'].includes(edition.edition)}
    catch (failure) {error.value = (failure as Error).message}
    finally {editionChecked.value = true; loading.value = false}
    if (enabled.value) await loadPeriod()
})
</script>

<style scoped>
.menu-planning :deep(.v-card-title) {white-space: normal;}
.menu-print-table {width: 100%; border-collapse: collapse;}
.menu-print-table th, .menu-print-table td {padding: 10px; text-align: left; border-bottom: 1px solid #b4aa98; vertical-align: top; overflow-wrap: anywhere;}
.menu-print-table th {background: #eee8dd; color: #34382c;}
.menu-diet-unsuitable {border-left: 4px solid #a32323; color: #8c1b1b;}
@media print {.menu-sheet {break-after: page;} .menu-sheet:last-child {break-after: auto;} tr {break-inside: avoid;} .menu-planning {max-width: none; padding: 0;} .menu-print-table {font-size: 10pt;}}
</style>
