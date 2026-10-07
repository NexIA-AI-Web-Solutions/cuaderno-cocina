import type {PlanningMeal, TemplateEntry} from './planningApi'
export function dietPresentation(status: unknown): {label: string, color: string}
export function planningEndDate(start: string, weeks: number): string
export function templateEntriesFromPlans(plans: PlanningMeal[], start: string, weeks: number): TemplateEntry[]
