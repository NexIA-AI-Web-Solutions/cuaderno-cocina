<template>
    <span v-if="depth >= 4 || (!Array.isArray(value) && !objectValue)">{{ displayValue(value) }}</span>
    <div v-else-if="costValue" class="worker-cost-result">
        <dl class="worker-nested-values">
            <div><dt>Estado</dt><dd>{{ formatWorkerValue(costValue.status) }}</dd></div>
            <div><dt>Total</dt><dd>{{ displayValue(costValue.display) }}</dd></div>
            <div v-if="'per_serving' in costValue"><dt>Coste por ración</dt><dd>{{ displayValue(costValue.per_serving) }}</dd></div>
            <div v-if="costValue.status !== 'complete'"><dt>Subtotal conocido</dt><dd>{{ displayValue(costValue.known_subtotal) }}</dd></div>
        </dl>
        <details v-if="Object.keys(costDetails).length" class="worker-calculation-details"><summary>Detalle del cálculo</summary><worker-value :value="costDetails" :depth="depth + 1" /></details>
    </div>
    <ul v-else-if="Array.isArray(value) && value.length" class="worker-nested-list"><li v-for="(item, index) in value" :key="index"><worker-value :value="item" :depth="depth + 1" /></li></ul>
    <span v-else-if="Array.isArray(value)">Sin registros</span>
    <dl v-else-if="objectValue && Object.keys(objectValue).length" class="worker-nested-values"><div v-for="(item, key) in objectValue" :key="key"><dt>{{ workerFieldLabel(String(key)) }}</dt><dd><v-btn v-if="key === 'action_url' && workerActionUrl(item)" :to="workerActionUrl(item) ?? undefined" variant="outlined" min-height="44">Abrir para revisar</v-btn><worker-value v-else :value="item" :depth="depth + 1" /></dd></div></dl>
    <span v-else>Sin datos adicionales</span>
</template>
<script setup lang="ts">
import {computed} from 'vue'
import {workerActionUrl, workerFieldLabel, workerValue as formatWorkerValue} from '@/cuaderno/workerUi'
defineOptions({name: 'WorkerValue'})
const props = withDefaults(defineProps<{value: unknown; depth?: number}>(), {depth: 0})
const objectValue = computed(() => props.value && typeof props.value === 'object' && !Array.isArray(props.value) ? props.value as Record<string, unknown> : null)
const costValue = computed(() => objectValue.value && typeof objectValue.value.status === 'string' && 'display' in objectValue.value && 'unrounded' in objectValue.value && 'known_subtotal' in objectValue.value ? objectValue.value : null)
// Exclude the summary's identifying fields so recursion cannot detect this as
// the same cost result again. Full source values remain in the downloaded JSON.
const costDetails = computed(() => Object.fromEntries(Object.entries(costValue.value ?? {}).filter(([key]) => !['status', 'display', 'per_serving', 'known_subtotal', 'total'].includes(key))))
function displayValue(value: unknown) {
    if (typeof value === 'string' && /^-?\d+\.\d{3,}$/.test(value)) return value.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
    return formatWorkerValue(value)
}
</script>
<style scoped>
.worker-nested-values {margin: 0;}
.worker-nested-values > div {margin-bottom: 8px;}
.worker-nested-values dt {font-weight: 600; font-size: .875rem;}
.worker-nested-values dd {margin: 2px 0 0; overflow-wrap: anywhere;}
.worker-nested-list {padding-left: 20px; margin: 0;}
.worker-nested-list > li {margin: 4px 0 12px; overflow-wrap: anywhere;}
.worker-calculation-details > summary {cursor: pointer; min-height: 44px; display: flex; align-items: center; text-decoration: underline;}
.worker-calculation-details > summary:focus-visible {outline: 3px solid rgb(var(--v-theme-primary)); outline-offset: 2px;}
</style>
