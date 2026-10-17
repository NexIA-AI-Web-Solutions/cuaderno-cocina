<template>
    <v-dialog width="500" activator="parent" v-model="dialog" :aria-label="title">

        <v-card>
            <v-closable-card-title :title="title" v-model="dialog"></v-closable-card-title>

            <v-card-text>
                <p v-if="props.text">{{ props.text }}</p>
                <p class="mb-4">Ajusta las cantidades y el coste para cocinar. La receta guardada no cambia.</p>
                <v-number-input label="Raciones para cocinar" inputmode="decimal" :error-messages="validServings ? [] : ['Introduce un número de raciones mayor que cero.']" :precision="2" v-model="mutableNumber" @update:modelValue="updateNumber('set')" control-variant="split" :min="0">
                </v-number-input>

                <v-btn-group divided class="d-flex">
                    <v-btn variant="tonal" class="flex-grow-1" min-height="44" aria-label="La mitad de raciones" @click="updateNumber( 'half')">
                        <i class="fas fa-divide"></i> 2
                    </v-btn>
                    <v-btn variant="tonal" class="flex-grow-1" min-height="44" aria-label="El doble de raciones" @click="updateNumber('double')">
                        <i class="fas fa-times"></i> 2
                    </v-btn>
                </v-btn-group>

                <template v-if="props.recipe.diameter">
                    <v-number-input class="mt-4" :label="$t('Diameter')" v-model="diameter" @update:modelValue="changeDiameter">
                        <template #append-inner>
                            <span class="pa-2">{{ props.recipe?.diameterText }}</span>
                        </template>
                    </v-number-input>
                </template>

            </v-card-text>
            <v-card-actions class="flex-wrap ga-2">
                <v-btn variant="text" min-height="44" prepend-icon="$reset" @click="mutableNumber=props.recipe?.servings ?? 1; diameter = props.recipe?.diameter ?? 0; updateNumber('set')">{{ $t('Reset') }}</v-btn>
                <v-btn color="primary" variant="flat" min-height="44" :disabled="!validServings" @click="confirmServings">Aplicar raciones</v-btn>
            </v-card-actions>
        </v-card>

    </v-dialog>
</template>

<script setup lang="ts">

import {computed, onMounted, PropType, ref, watch} from 'vue'
import VClosableCardTitle from "@/components/dialogs/VClosableCardTitle.vue";
import {Recipe} from "@/openapi";

const emit = defineEmits({
    change(payload: number) {
        return payload
    },
    confirm(payload: number) {
        return payload
    }
})

const props = defineProps({
    recipe: {type: {} as PropType<Recipe>, required: true},
    number: {type: Number, default: 0},
    title: {type: String, default: 'Cantidad'},
    text: {type: String, default: ''},
})

const dialog = ref(false)
const mutableNumber = ref<number | null>(props.number)
const diameter = ref(props.recipe?.diameter ?? 0)
const validServings = computed(() => typeof mutableNumber.value === 'number' && Number.isFinite(mutableNumber.value) && mutableNumber.value > 0)

function confirmServings() {
    if (!validServings.value) return
    emit('confirm', mutableNumber.value!)
    dialog.value = false
}

// Closing cancels the draft; each new opening starts from the applied view.
watch(dialog, open => {
    if (open) {
        mutableNumber.value = props.number
        diameter.value = props.recipe?.diameter ?? 0
    }
})

watch(() => props.number, (newVal) => {
    mutableNumber.value = newVal
})

onMounted(() => {
    mutableNumber.value = props.number
})

/**
 * perform given operation on linked number
 * @param operation update mode
 */
function updateNumber(operation: string) {
    if (operation === 'half') {
        mutableNumber.value = (mutableNumber.value ?? 0) / 2
    }
    if (operation === 'double') {
        mutableNumber.value = (mutableNumber.value ?? 0) * 2
    }
    if (operation === 'add') {
        mutableNumber.value = (mutableNumber.value ?? 0) + 1
    }
    if (operation === 'sub') {
        mutableNumber.value = (mutableNumber.value ?? 0) - 1
    }

    if (validServings.value) emit('change', mutableNumber.value!)
}

/**
 * adjust the servings value according to the diameter difference
 * @param value
 */
function changeDiameter(value: number) {
    if (props.recipe && props.recipe.diameter && props.recipe.diameter > 0) {
        mutableNumber.value = (props.recipe.servings ? props.recipe.servings : 1) * Math.round(Math.pow(value / props.recipe?.diameter!, 2) * 100) / 100
        updateNumber('set')
    }
}

</script>


<style scoped>

</style>