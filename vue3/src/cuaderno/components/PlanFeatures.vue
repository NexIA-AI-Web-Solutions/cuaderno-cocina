<template>
    <section v-if="authenticated" class="plan-features mt-6" aria-labelledby="plan-features-title">
        <h2 id="plan-features-title" class="text-h6 mb-2">Ediciones de Cuaderno de cocina</h2>
        <p v-if="current" class="mb-3">Edición de este espacio: <strong>{{ current.label }}</strong>. Tu rol determina qué puedes modificar.</p>
        <p v-else-if="loading" role="status" class="mb-3">Consultando la edición del espacio…</p>
        <v-alert v-if="error" type="warning" variant="tonal" role="alert" class="mb-3">{{ error }}</v-alert>
        <details class="plan-comparison">
            <summary>Comparar funciones y precios informativos</summary>
            <p class="ma-3 text-body-2">Importes informativos: esta pantalla no realiza contrataciones ni cobros.</p>
            <table class="plan-table">
                <caption class="sr-only">Funciones incluidas en Esencial, Profesional e Integral</caption>
                <thead><tr><th scope="col">Función</th><th v-for="plan in plans" :key="plan.id" scope="col" :class="{'current-plan': current?.id === plan.id}"><span>{{ plan.label }}</span><small>{{ plan.initial }} €<br>+ {{ plan.monthly }} €/mes</small><small v-if="current?.id === plan.id">Tu edición</small></th></tr></thead>
                <tbody><tr v-for="feature in rows" :key="feature.key" :data-feature="feature.key"><th scope="row">{{ feature.label }}</th><td v-for="plan in plans" :key="plan.id" :data-plan="plan.id">{{ inclusion(feature, plan) }}</td></tr></tbody>
            </table>
            <p class="ma-3 text-body-2">Las declaraciones dietéticas son manuales. «No declarado» no significa apto. Las ausencias las gestiona Responsable; las favoritas son personales.</p>
            <p class="ma-3 text-body-2">Las funciones existentes de recetas, compras y costes básicos se conservan en todas las ediciones. La planificación no descuenta existencias.</p>
        </details>
    </section>
</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, ref, watch} from 'vue'
import {planningRequest} from '@/cuaderno/planningApi'
const props = withDefaults(defineProps<{authenticated?: boolean}>(), {authenticated: false})
const plans = [
    {id: 'esencial', label: 'Esencial', rank: 0, initial: '500', monthly: '17'},
    {id: 'profesional', label: 'Profesional', rank: 1, initial: '1000', monthly: '20'},
    {id: 'integral', label: 'Integral', rank: 2, initial: '1500', monthly: '30'},
]
type FeatureRow = {key: string; label: string; rank: number; native?: boolean}
const rows: FeatureRow[] = [
    {key: 'native_core', label: 'Recetas, lista de compra y costes básicos', rank: 0, native: true},
    {key: 'recipe_gallery', label: 'Galería de fotos', rank: 0},
    {key: 'recipe_favorites', label: 'Favoritas personales', rank: 0},
    {key: 'recipe_variants', label: 'Variantes vinculadas', rank: 0},
    {key: 'diet_declarations', label: '8 declaraciones dietéticas manuales', rank: 0},
    {key: 'menu_five_weeks', label: 'Calendario de 1 a 5 semanas', rank: 0},
    {key: 'menu_courses', label: 'Tipos de plato', rank: 1},
    {key: 'menu_templates', label: 'Plantillas de menús con nombre', rank: 1},
    {key: 'menu_diet_filter', label: 'Filtro dietético y aviso de no aptos', rank: 1},
    {key: 'calendar_events', label: 'Eventos del calendario', rank: 1},
    {key: 'staff_absences', label: 'Ausencias del equipo', rank: 1},
    {key: 'menu_print', label: 'Impresión individual vertical u horizontal', rank: 1},
    {key: 'native_production', label: 'Producción, mermas y necesidades', rank: 1, native: true},
    {key: 'merged_menu_print', label: 'Varios menús en un documento', rank: 2},
    {key: 'native_stock', label: 'Pedidos, recepciones y existencias', rank: 2, native: true},
    {key: 'native_prices', label: 'Evolución de precios e impacto en costes', rank: 2, native: true},
]
const edition = ref(''), flags = ref<Record<string, boolean>>({}), loading = ref(false), error = ref('')
const current = computed(() => plans.find(plan => plan.id === edition.value))
function inclusion(feature: FeatureRow, plan: typeof plans[number]) {
    if (current.value?.id === plan.id && !feature.native) return flags.value[feature.key] === true ? 'Incluido' : 'No habilitado'
    return plan.rank >= feature.rank ? 'Incluido' : '—'
}
let generation = 0
watch(() => props.authenticated, async authenticated => {
    const request = ++generation; edition.value = ''; flags.value = {}; error.value = ''; loading.value = false
    if (!authenticated) return
    loading.value = true
    try {
        const value = await planningRequest<{edition: string; features: Record<string, boolean>}>('edition/')
        if (request !== generation) return
        if (!plans.some(plan => plan.id === value.edition) || !value.features || rows.some(row => !row.native && typeof value.features[row.key] !== 'boolean')) throw new Error('Incomplete edition')
        edition.value = value.edition; flags.value = value.features
    } catch {
        if (request === generation) error.value = 'No se pudo confirmar la edición del espacio. La comparación es informativa; no cambia tus permisos.'
    } finally {if (request === generation) loading.value = false}
}, {immediate: true})
onBeforeUnmount(() => {generation++})
</script>

<style scoped>
.plan-comparison {border: 1px solid rgba(var(--v-theme-on-surface), .16); border-radius: 12px; overflow: hidden;}
.plan-comparison summary {cursor: pointer; font-weight: 600; padding: 16px; min-height: 48px;}
.plan-table {width: 100%; border-collapse: collapse; table-layout: fixed; font-size: .875rem;}
.plan-table th, .plan-table td {padding: 10px 6px; border-top: 1px solid rgba(var(--v-theme-on-surface), .12); vertical-align: top; overflow-wrap: anywhere;}
.plan-table th:first-child {width: 40%; text-align: left; font-weight: 500;}
.plan-table td, .plan-table thead th {text-align: center;}
.plan-table thead {background: rgba(var(--v-theme-secondary), .10);}
.plan-table small {display: block; margin-top: 4px; font-weight: 400;}
.current-plan {border-bottom: 3px solid rgb(var(--v-theme-primary));}
@media (max-width: 480px) {.plan-table {font-size: .75rem;} .plan-table th, .plan-table td {padding: 8px 4px;} .plan-table th:first-child {width: 34%;}}
</style>
