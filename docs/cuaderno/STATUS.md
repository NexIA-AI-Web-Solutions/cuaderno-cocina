# Estado del producto

Estado actual: el motor y las pantallas nuevas están en el sitio local.
La revisión independiente pedida con otros modelos no se puede firmar aquí:
esos modelos no están en este runtime. No hay iPad físico, migración de cliente
ni despliegue VPS. El pytest upstream del pin sigue sin ejecutarse.

| Gate | Estado | Evidencia |
|---|---|---|
| G0 | PARCIAL | Pin y arranque: `evidence/T002-baseline.md`. Pytest upstream del pin no se ejecutó: la imagen no trae `cookbook/tests`. |
| G1 | PROBADO | 27 tests de dominio. Coste de la receta 1 sigue completo (`2.80`) y no guarda la receta. El bundle nuevo se sirve: `evidence/T011-vue-bundle.md`. |
| G2 | PARCIAL | Importación rechaza URL, exporta sin privadas, CSRF 403/200. Backup y restore con los mismos conteos en `cuaderno_restore_g6` (recetas 9, precios 2, movimientos 5, inventario 1). Impresión en CSS, no vista en navegador. |
| G3 | PROBADO EN API | Servicio 45 comensales sobre `MealPlan`, sin pago y sin mover stock. Salsa 300. Ciclo rechazado. Alérgeno desconocido no significa ausente. Lista nativa: marcar y deshacer. |
| G4 | PROBADO EN API | Pedido no mueve stock. Recepción idempotente y conflicto 409. Carrera de dos procesos: uno gana, saldo 0. Reversión y merma en negativo. Reposición 2 envases. |
| G5 | PARCIAL | Otro espacio no lee el coste ni mueve el saldo. CSRF comprobado. No hay barrido de dependencias ni prueba de subida de ficheros. |
| G6 | PARCIAL | Migraciones `cuaderno` 0001–0003 en la base aislada. Restore nuevo comprobado. `http://127.0.0.1:18080/setup/` respondió 200. El bundle Vue nuevo ya está en lo que sirve nginx. |
| G7 | NO FIRMADO | Falta la revisión independiente. No se marca DONE en `tasks.json`. |

Base: `7e1c427a` (`2.6.15`). Local, cuando el contenedor está en marcha: `http://127.0.0.1:18080`, usuario `demo`.
El espacio demo quedó en edición Integral tras la prueba. Esencial rechaza el almacén con 403.
El VPS usará el Caddyfile existente (ADR 0001); no está desplegado.
