<template>
    <v-row class="h-100">
        <v-col class="pb-0">
            <div class="d-flex flex-wrap align-center ga-3 mb-3 d-print-none">
                <v-select :model-value="weekMode ? weekCount : null" :items="[1,2,3,4,5]" label="Vista de 1 a 5 semanas" style="max-width: 220px" density="compact" hide-details @update:model-value="setWeeks" />
                <v-btn v-if="professional" :to="{path: '/cuaderno/planificacion'}" variant="tonal" prepend-icon="fa-solid fa-layer-group">Plantillas y organización</v-btn>
                <v-select v-if="professional && weekMode" v-model="selectedDiet" :items="dietOptions" item-title="label" item-value="slug" label="Consultar dieta" clearable style="max-width: 260px" density="compact" hide-details />
                <v-checkbox v-if="professional && weekMode && selectedDiet" v-model="onlySuitable" label="Solo aptos declarados" hide-details />
            </div>
            <p v-if="professional && !weekMode" class="text-body-2 mb-3">La vista actual conserva el calendario nativo. Elige una vista de 1 a 5 semanas para consultar tipos de plato, dietas y eventos del mismo periodo.</p>
            <v-alert v-if="planningError" type="warning" variant="tonal" role="alert" class="mb-3">{{ planningError }} <v-btn variant="text" @click="loadPlanning">Volver a cargar anotaciones</v-btn></v-alert>
            <p v-if="professional && weekMode && selectedDiet" class="text-body-2 mb-3">Rojo: no apto según declaración manual. «No declarado» no significa apto. Revisa ingredientes y preparación.</p>
            <v-card class="h-100 cuaderno-calendar" :loading="calendarBusy" :aria-busy="calendarBusy ? 'true' : 'false'">
                <!-- TODO add hint about CTRL key while drag/drop -->
                <!-- TODO multi selection? date range selection ? -->
                <calendar-view
                    :locale="locale"
                    :show-date="calendarDate"
                    :items="planItems"
                    class="theme-default"
                    :item-content-height="calendarItemHeight"
                    :enable-drag-drop="canOperate"
                    @dropOnDate="dropCalendarItemOnDate"
                    :display-period-uom="useUserPreferenceStore().deviceSettings.mealplan_displayPeriod"
                    :display-period-count="useUserPreferenceStore().deviceSettings.mealplan_displayPeriodCount"
                    :starting-day-of-week="useUserPreferenceStore().deviceSettings.mealplan_startingDayOfWeek"
                    :display-week-numbers="useUserPreferenceStore().deviceSettings.mealplan_displayWeekNumbers"
                    :current-period-label="$t('Today')"
                    @click-date="(date : Date, calendarItems: [], windowEvent: any) => { if (canOperate) {newPlanDialogDefaultItem.fromDate = date; newPlanDialogDefaultItem.toDate = date; newPlanDialog = true} }">
                    <template #header="{ headerProps }">
                        <!--                        <calendar-view-header :header-props="headerProps" @input="(d:Date) => calendarDate = d"></calendar-view-header>-->
                        <meal-plan-calendar-header :header-props="headerProps" @input="(d:Date) => calendarDate = d"></meal-plan-calendar-header>
                    </template>
                    <template #item="{ value, weekStartDate, top }">
                        <v-card v-if="value.originalItem.planningEvent" class="cv-item pa-1 planning-event" :class="value.classes" :style="{top, height: calendarItemHeight}" :title="eventTitle(value.originalItem.planningEvent)" :draggable="false">
                            <span class="text-caption">{{ eventTitle(value.originalItem.planningEvent) }}</span>
                        </v-card>
                        <meal-plan-calendar-item
                            v-else
                            :item-height="calendarItemHeight"
                            :value="value"
                            :item-top="top"
                            @onDragStart="currentlyDraggedMealplan = value"
                            @delete="(arg: MealPlan) => {useMealPlanStore().plans.delete(arg.id)}"
                            :detailed-items="lgAndUp"
                            :can-edit="canOperate"
                            :course-label="courseLabel(value.originalItem.mealPlan.id)"
                            :diet-status="weekMode && selectedDiet ? mealStatus(value.originalItem.mealPlan.id) : ''"
                        ></meal-plan-calendar-item>
                    </template>
                </calendar-view>
            </v-card>


            <model-edit-dialog model="MealPlan" v-model="newPlanDialog" :itemDefaults="newPlanDialogDefaultItem" :close-after-create="false"
                               @create="(arg: any) => useMealPlanStore().plans.set(arg.id, arg)"></model-edit-dialog>
        </v-col>
    </v-row>
</template>


<script setup lang="ts">
import {CalendarView, CalendarViewHeader} from "vue-simple-calendar"
import "vue-simple-calendar/dist/style.css"
import "vue-simple-calendar/dist/css/default.css"

import MealPlanCalendarItem from "@/components/display/MealPlanCalendarItem.vue";
import {IMealPlanCalendarItem, IMealPlanNormalizedCalendarItem} from "@/types/MealPlan";
import {computed, onMounted, ref, watch} from "vue";
import {DateTime, Duration} from "luxon";
import {useDisplay} from "vuetify";
import {useMealPlanStore} from "@/stores/MealPlanStore";
import ModelEditDialog from "@/components/dialogs/ModelEditDialog.vue";
import {MealPlan} from "@/openapi";
import {useUserPreferenceStore} from "@/stores/UserPreferenceStore";
import MealPlanCalendarHeader from "@/components/display/MealPlanCalendarHeader.vue";
import {useI18n} from "vue-i18n";
import {dietOptions, planningRequest, type PlanningData, type PlanningEvent} from '@/cuaderno/planningApi';
import {planningEndDate} from '@/cuaderno/planningUi.mjs';

const {lgAndUp} = useDisplay()
const {locale} = useI18n()

const calendarDate = ref(new Date())
const professional = ref(false), canOperate = ref(false), selectedDiet = ref<string | null>(null), onlySuitable = ref(false)
const planning = ref<PlanningData | null>(null), planningError = ref('')
const planningLoading = ref(false), editionLoading = ref(true)
const calendarBusy = computed(() => useMealPlanStore().loading || planningLoading.value || editionLoading.value)
const weekMode = computed(() => {const settings = useUserPreferenceStore().deviceSettings; return settings.mealplan_displayPeriod === 'week' && Number.isInteger(settings.mealplan_displayPeriodCount) && settings.mealplan_displayPeriodCount >= 1 && settings.mealplan_displayPeriodCount <= 5})
const weekCount = computed(() => {const count = useUserPreferenceStore().deviceSettings.mealplan_displayPeriodCount; return Number.isInteger(count) && count >= 1 && count <= 5 ? count : 1})
let planningGeneration = 0
function setWeeks(count: number) {
    if (!Number.isInteger(count) || count < 1 || count > 5) return
    useUserPreferenceStore().deviceSettings.mealplan_displayPeriod = 'week'
    useUserPreferenceStore().deviceSettings.mealplan_displayPeriodCount = count
}
function eventTitle(event: PlanningEvent) {return `${event.kind === 'absence' ? 'Ausencia' : 'Evento'} · ${event.title}${event.member_name ? ' · ' + event.member_name : ''}`}
function mealStatus(id: number) {return planning.value?.meal_plans.find(meal => meal.id === id)?.diet_status || 'unknown'}
function courseLabel(id: number) {
    const course = planning.value?.meal_plans.find(meal => meal.id === id)?.course
    return planning.value?.courses.find(row => row.id === course)?.name || ''
}
async function loadPlanning() {
    const generation = ++planningGeneration; planning.value = null; planningLoading.value = false
    if (!professional.value) return
    planningError.value = ''
    if (!weekMode.value) return
    planningLoading.value = true
    // The native completion watcher loads the annotations for the finished period.
    if (useMealPlanStore().loading) return
    const day = calendarDate.value.getDay(), first = useUserPreferenceStore().deviceSettings.mealplan_startingDayOfWeek
    const start = DateTime.fromJSDate(calendarDate.value).minus({days: (day - first + 7) % 7}).toISODate()!
    const end = planningEndDate(start, weekCount.value)
    try {
        const result = await planningRequest<PlanningData>(`planning/?from_date=${start}&to_date=${end}${selectedDiet.value ? '&diet=' + encodeURIComponent(selectedDiet.value) : ''}`)
        if (generation === planningGeneration) planning.value = result
    } catch (error) {if (generation === planningGeneration) planningError.value = 'No se pudieron cargar tipos, dietas y eventos. El calendario nativo sigue disponible. ' + (error as Error).message}
    finally {if (generation === planningGeneration) planningLoading.value = false}
}

const currentlyDraggedMealplan = ref({} as IMealPlanNormalizedCalendarItem)

const newPlanDialog = ref(false)
const newPlanDialogDefaultItem = ref({} as MealPlan)

/**
 * computed property that converts array of MealPlan object to
 * array of CalendarItems (format required/extended from vue-simple-calendar)
 */
const planItems = computed(() => {
    let items = [] as Array<IMealPlanCalendarItem | {id: string; startDate: Date; endDate: Date; planningEvent: PlanningEvent}>
    useMealPlanStore().planList.forEach(mp => {
        if (professional.value && weekMode.value && selectedDiet.value && onlySuitable.value && mealStatus(mp.id!) !== 'suitable') return
        items.push({
            startDate: mp.fromDate,
            endDate: mp.toDate ? mp.toDate : mp.fromDate,
            id: mp.id,
            mealPlan: mp,
        } as IMealPlanCalendarItem)
    })
    for (const event of planning.value?.events || []) items.push({id: `cuaderno-event-${event.id}`, startDate: DateTime.fromISO(event.start_date).toJSDate(), endDate: DateTime.fromISO(event.end_date).endOf('day').toJSDate(), planningEvent: event})
    return items
})

/**
 * determine item height (one or two rows) based on how much space is available and how many days are shown
 */
const calendarItemHeight = computed(() => {
    if (professional.value && weekMode.value) return lgAndUp.value ? '4.5rem' : '3rem'
    if (lgAndUp.value && useUserPreferenceStore().deviceSettings.mealplan_displayPeriod == 'week') {
        return '3.5rem'
    } else {
        return '1.6rem'
    }
})

/**
 * watch calendar date and load entries accordingly
 */
watch(calendarDate, () => {
    refreshVisiblePeriod(false)
    void loadPlanning()
})
watch(() => [useUserPreferenceStore().deviceSettings.mealplan_displayPeriod, useUserPreferenceStore().deviceSettings.mealplan_displayPeriodCount, useUserPreferenceStore().deviceSettings.mealplan_startingDayOfWeek], () => {refreshVisiblePeriod(true); void loadPlanning()})
watch(selectedDiet, () => {onlySuitable.value = false; void loadPlanning()})
watch(() => useMealPlanStore().loading, loading => {if (!loading) void loadPlanning()})

onMounted(() => {
    refreshVisiblePeriod(true)
    planningRequest<{edition: string; operational_role: {can_operate_cuaderno: boolean}}>('edition/').then(edition => {
        professional.value = ['profesional', 'integral'].includes(edition.edition)
        canOperate.value = edition.operational_role?.can_operate_cuaderno === true
        if (professional.value) void loadPlanning()
    }).catch(() => {planningError.value = 'No se pudieron comprobar los permisos. El calendario permanece en modo lectura.'})
        .finally(() => {editionLoading.value = false})
})

/**
 * refresh data for the currently visible period
 * @param startDateUnknown when the calendar initially loads the date is set to today but the visible period might be larger. If set loads the period day count for the past as well
 */
function refreshVisiblePeriod(startDateUnknown: boolean) {
    let daysInPeriod = 7
    if (useUserPreferenceStore().deviceSettings.mealplan_displayPeriod == 'month') {
        daysInPeriod = 31
    } else if (useUserPreferenceStore().deviceSettings.mealplan_displayPeriod == 'year') {
        daysInPeriod = 365
    }

    let days = useUserPreferenceStore().deviceSettings.mealplan_displayPeriodCount * daysInPeriod

    // load backwards to as on initial
    if (startDateUnknown) {
        useMealPlanStore().refreshFromAPI(DateTime.fromJSDate(calendarDate.value).minus({days: days}).toJSDate(), DateTime.fromJSDate(calendarDate.value).plus({days: days}).toJSDate())
    } else {
        useMealPlanStore().refreshFromAPI(calendarDate.value, DateTime.fromJSDate(calendarDate.value).plus({days: days}).toJSDate())
    }
}

/**
 * handle drop event for calendar items on fields
 * @param undefinedItem
 * @param targetDate
 * @param event
 */
function dropCalendarItemOnDate(undefinedItem: IMealPlanNormalizedCalendarItem, targetDate: Date, event: DragEvent) {
    if (!canOperate.value) return
    //The item argument (first) is undefined because our custom calendar item cannot manipulate the calendar state so the item is unknown to the calendar (probably fixable by somehow binding state to the item)
    if (currentlyDraggedMealplan.value.originalItem.mealPlan.id != undefined) {
        let mealPlan = useMealPlanStore().plans.get(currentlyDraggedMealplan.value.originalItem.mealPlan.id)
        if (mealPlan != undefined) {
            let fromToDiff = {days: 0}
            if (mealPlan.toDate && mealPlan.toDate > mealPlan.fromDate) {
                fromToDiff = DateTime.fromJSDate(mealPlan.toDate).diff(DateTime.fromJSDate(mealPlan.fromDate), 'days')
            }

            const existingTime = DateTime.fromJSDate(mealPlan.fromDate)
            const newFrom = DateTime.fromJSDate(targetDate).set({
                hour: existingTime.hour, minute: existingTime.minute, second: existingTime.second
            }).toJSDate()
            const newTo = DateTime.fromJSDate(targetDate).plus(fromToDiff).set({
                hour: existingTime.hour, minute: existingTime.minute, second: existingTime.second
            }).toJSDate()

            // create copy of item if control is pressed
            if (event.ctrlKey) {
                useMealPlanStore().createObject({
                    ...mealPlan,
                    fromDate: newFrom,
                    toDate: newTo,
                    addshopping: mealPlan.shopping,
                })
            } else {
                mealPlan.fromDate = newFrom
                mealPlan.toDate = newTo
                useMealPlanStore().updateObject(mealPlan)
            }
        }
    }
}

</script>


<style scoped>
.planning-event {background: rgba(var(--v-theme-secondary), .13); border-left: 3px solid rgb(var(--v-theme-secondary)); white-space: normal; overflow: hidden;}
.cuaderno-calendar :deep(.cv-header-day) { background: rgb(var(--v-theme-surface)); color: rgb(var(--v-theme-on-surface)); padding-block: 8px; font-weight: 600; }
.cuaderno-calendar :deep(.cv-day) { border-color: rgba(var(--v-theme-on-surface), .14); }
.cuaderno-calendar :deep(.cv-day.today) { background: rgba(var(--v-theme-primary), .12); color: rgb(var(--v-theme-on-surface)); }
.cuaderno-calendar :deep(.cv-day.today .cv-day-number) { font-weight: 700; border-bottom: 3px solid rgb(var(--v-theme-primary)); }

/* TODO remove unused styles */

.slide-fade-enter-active {
    transition: all 0.3s ease;
}

.slide-fade-leave-active {
    transition: all 0.1s cubic-bezier(1, 0.5, 0.8, 1);
}

.slide-fade-enter,
.slide-fade-leave-to {
    transform: translateY(10px);
    opacity: 0;
}

.calender-row {
    height: calc(100vh - 140px);
}

.calender-parent {
    display: flex;
    flex-direction: column;
    flex-grow: 1;
    overflow-x: hidden;
    overflow-y: hidden;
    height: 100%
}

.cv-item {
    white-space: inherit !important;
    padding: 0;
    border-radius: 3px !important;
}


.isHovered {
    box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15) !important;
}

.cv-day.draghover {
    box-shadow: inset 0 0 0.2em 0.2em rgb(221, 191, 134) !important;
}

.modal-backdrop {
    opacity: 0.5;
}

/*
**************************************************************
This theme is the default shipping theme, it includes some
decent defaults, but is separate from the calendar component
to make it easier for users to implement their own themes w/o
having to override as much.
**************************************************************
*/

/* Header */

.theme-default .cv-header,
.theme-default .cv-header-day {
    background-color: #f0f0f0;
}

.theme-default .cv-header .periodLabel {
    font-size: 1.5em;
}

/* Grid */

.theme-default .cv-weeknumber {
    background-color: #e0e0e0;
    border-color: #ccc;
    color: #808080;
}

.theme-default .cv-weeknumber span {
    margin: 0;
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
}

.theme-default .cv-day.past {
    background-color: #fafafa;
}

.theme-default .cv-day.outsideOfMonth {
    background-color: #f7f7f7;
}

.theme-default .cv-day.today {
    background-color: #ffe;
}

.theme-default .cv-day[aria-selected] {
    background-color: #ffc;
}

/* Events */

.theme-default .cv-item {
    border-color: #e0e0f0;
    border-radius: 0.5em;
    background-color: #fff;
    text-overflow: ellipsis;
}

.theme-default .cv-item.purple {
    background-color: #f0e0ff;
    border-color: #e7d7f7;
}

.theme-default .cv-item.orange {
    background-color: #ffe7d0;
    border-color: #f7e0c7;
}

.theme-default .cv-item.continued::before,
.theme-default .cv-item.toBeContinued::after {
    /*
    removed because it breaks a line and would increase item size https://github.com/TandoorRecipes/recipes/issues/2678
    content: " \21e2 ";
    color: #999;
     */
    content: "";
}

.theme-default .cv-item.toBeContinued {
    border-right-style: none;
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
}

.theme-default .cv-item.isHovered.hasUrl {
    text-decoration: underline;
}

.theme-default .cv-item.continued {
    border-left-style: none;
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
}

.cv-item.span3,
.cv-item.span4,
.cv-item.span5,
.cv-item.span6,
.cv-item.span7 {
    text-align: center;
}

/* Event Times */

.theme-default .cv-item .startTime,
.theme-default .cv-item .endTime {
    font-weight: bold;
    color: #666;
}

/* Drag and drop */

.theme-default .cv-day.draghover {
    box-shadow: inset 0 0 0.2em 0.2em yellow;
}

.ghost {
    opacity: 0.5;
    background: #c8ebfb;
}

@media (max-width: 767.9px) {
    .periodLabel {
        font-size: 18px !important;
    }
}

.b-calendar-grid-help {
    padding: 0.25rem;
}
</style>
