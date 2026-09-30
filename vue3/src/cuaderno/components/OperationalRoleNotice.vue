<template>
    <section class="mb-4" aria-label="Rol operativo">
        <h2 class="text-subtitle-1">Rol operativo</h2>
        <v-alert v-if="role === null" type="warning" variant="tonal" role="status" class="mt-2">
            No se ha podido confirmar el rol operativo de este espacio. Las capacidades se mantienen sin asumir permisos.
        </v-alert>
        <template v-else>
            <p>Rol en el espacio {{ role.space }}: <strong>{{ role.label }}</strong>.</p>
            <p v-if="role.can_operate_cuaderno">Cuaderno operativo: permitido para este rol.</p>
            <p v-else>
                Cuaderno operativo: no permitido para este rol. La consulta de costes disponible para tu cuenta permanece accesible.
            </p>
            <p v-if="role.can_manage_edition">Puede gestionar la edición comercial de este espacio.</p>
            <p v-else>La edición comercial solo puede gestionarla el rol Responsable.</p>
            <p class="text-body-2 text-medium-emphasis">
                Los permisos nativos sobre propietarios, libros, menús y listas se conservan y siguen determinando el acceso.
            </p>
        </template>
    </section>
</template>

<script setup lang="ts">
import type {OperationalRole} from '@/cuaderno/operationalRoleUi'

defineProps<{role: OperationalRole | null}>()
</script>
