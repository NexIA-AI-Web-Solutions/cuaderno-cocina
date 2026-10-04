declare module 'vue-simple-calendar' {
    import type {DefineComponent} from 'vue'

    export interface ICalendarItem {
        id: string
        startDate: Date
        title: string
        tooltip?: string
        endDate?: Date
        url?: string
        classes?: string[] | null
        style?: string
    }

    export interface IHeaderProps {
        periodStart: Date
        periodEnd: Date
        previousYear: Date | null
        previousPeriod: Date | null
        nextPeriod: Date | null
        previousFullPeriod: Date | null
        nextFullPeriod: Date | null
        nextYear: Date | null
        currentPeriod: Date
        currentPeriodLabel: string
        periodLabel: string
        displayLocale: string
        displayFirstDate: Date
        displayLastDate: Date
        monthNames: string[]
        fixedItems: ICalendarItem[]
    }

    export const CalendarView: DefineComponent<Record<string, unknown>>
    export const CalendarViewHeader: DefineComponent<Record<string, unknown>>
}
