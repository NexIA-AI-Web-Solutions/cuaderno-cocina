import {cuadernoFetch} from '@/cuaderno/api'
import {csrfHeadersForUrl, resolveDjangoUrl} from '@/utils/djangoConfig'

export type DietStatus = 'unknown' | 'suitable' | 'unsuitable'
export const dietOptions = [
    {slug: 'celiacos', label: 'Celíacos'}, {slug: 'colesterol', label: 'Colesterol'},
    {slug: 'diabetes', label: 'Diabetes'}, {slug: 'hiposodica', label: 'Hiposódica'},
    {slug: 'gastrica', label: 'Gástrica'}, {slug: 'fibra', label: 'Fibra'},
    {slug: 'sinfructosa', label: 'Sin fructosa'}, {slug: 'sinlactosa', label: 'Sin lactosa'},
] as const
export interface DietDeclaration {slug: string; label: string; status: DietStatus; note: string}
export interface RecipeExtras {
    recipe_id: number; revision: string; can_edit: boolean; is_favorite: boolean
    gallery: {id: number; url: string; caption: string; position: number}[]
    diets: DietDeclaration[]; variant_of: {id: number; name: string} | null; variants: {id: number; name: string}[]; variants_truncated?: boolean
}
export interface PlanningCourse {id: number; revision: string; name: string; meal_type: number; position: number}
export interface PlanningMeal {
    id: number; title: string; recipe: {id: number; name: string} | null; meal_type: {id: number; name: string}
    course: number | null; servings: string; from_date: string; to_date: string | null; note: string
    source_url?: string; course_name?: string | null; diet_status: DietStatus
}
export interface PlanningEvent {id: number; revision: string; kind: 'event' | 'absence'; title: string; member_name: string; start_date: string; end_date: string; note: string}
export interface PlanningData {courses: PlanningCourse[]; meal_plans: PlanningMeal[]; events: PlanningEvent[]; can_edit: boolean; can_manage_absences: boolean; can_merge_print: boolean}
export interface TemplateEntry {id?: number; day_index: number; meal_type: number; course: number | null; recipe: number | null; title: string; source_url: string; servings: string; recipe_name?: string; meal_type_name?: string; course_name?: string}
export interface EntityImage {url: string; caption: string}
export interface EntityImageData {image: EntityImage | null; can_edit: boolean; revision?: string}
export interface MenuTemplate {image?: EntityImage | null; id: number; name: string; weeks: number; revision: string; entries: TemplateEntry[]}
export interface PrintedMenus {orientation: 'portrait' | 'landscape'; merged: boolean; menus: {name: string; entries: PlanningMeal[]; image?: EntityImage | null}[]; declaration: string; diet: string | null; diet_label: string | null}

export class PlanningError extends Error {
    constructor(public status: number, message: string) {super(message)}
}
export async function planningRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const response = await cuadernoFetch('/api/cuaderno/' + path, {method, ...(body === undefined ? {} : {body: JSON.stringify(body)})})
    const value = await response.json().catch(() => ({}))
    if (!response.ok) throw new PlanningError(response.status, response.status === 409
        ? 'Los datos han cambiado o el periodo ya tiene platos. Actualiza antes de continuar; no se han sobrescrito tus cambios.'
        : planningErrorMessage(value, 'No se pudo guardar. Revisa los campos y tus permisos; el formulario conserva los datos.'))
    return value as T
}

export async function uploadRecipeGallery(recipeId: number, file: File, caption: string): Promise<RecipeExtras> {
    if (file.size > 5 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) {
        throw new Error('Elige una imagen JPG, PNG, WebP o GIF de hasta 5 MiB.')
    }
    const body = new FormData(); body.append('image', file); body.append('caption', caption)
    const url = resolveDjangoUrl(`/api/cuaderno/recipes/${recipeId}/gallery/`)
    // Let the browser generate the multipart boundary; reuse the native scoped CSRF policy.
    let response: Response
    try {response = await fetch(url, {method: 'POST', body, headers: csrfHeadersForUrl(url), credentials: 'same-origin', redirect: 'error'})}
    catch {throw new Error('No hay conexión. Conservamos la imagen seleccionada para que puedas reintentar.')}
    const value = await response.json().catch(() => ({}))
    if (!response.ok) throw new PlanningError(response.status, typeof value.detail === 'string' ? value.detail : 'No se pudo añadir la imagen. Revisa el formato, tamaño y permisos.')
    return value as RecipeExtras
}

/** DRF field errors should remain actionable in Spanish, including multipart validation. */
export function planningErrorMessage(value: unknown, fallback: string): string {
    if (!value || typeof value !== 'object') return fallback
    const detail = (value as {detail?: unknown}).detail
    if (typeof detail === 'string') return detail
    const labels: Record<string,string> = {image: 'Imagen', caption: 'Descripción', name: 'Nombre', non_field_errors: 'Formulario', template_id: 'Portada', menus: 'Menús', entries: 'Platos'}
    const parts = Object.entries(value).flatMap(([key, messages]) => {
        const list = Array.isArray(messages) ? messages : [messages]
        return list.filter(message => typeof message === 'string').map(message => `${labels[key] || key}: ${message}`)
    })
    return parts.length ? parts.join(' ') : fallback
}
export function validateEntityImage(file: File): void {
    if (file.size > 5 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) throw new Error('Elige una imagen JPG, PNG, WebP o GIF sin animación de hasta 5 MiB.')
}
export async function uploadEntityImage(path: string, file: File, caption: string): Promise<EntityImageData> {
    validateEntityImage(file)
    if (!/^(foods|planning\/templates)\/\d+\/image\/$/.test(path)) throw new Error('No se reconoce el destino de la imagen.')
    const url = resolveDjangoUrl('/api/cuaderno/' + path)
    const body = new FormData(); body.append('image', file); body.append('caption', caption)
    let response: Response
    try {response = await fetch(url, {method: 'PUT', body, headers: csrfHeadersForUrl(url), credentials: 'same-origin', redirect: 'error'})}
    catch {throw new Error('No hay conexión. Conservamos la imagen seleccionada para que puedas reintentar.')}
    const value = await response.json().catch(() => ({}))
    if (!response.ok) throw new PlanningError(response.status, planningErrorMessage(value, 'No se pudo guardar la imagen. Revisa el formato, tamaño y permisos.'))
    return value as EntityImageData
}
