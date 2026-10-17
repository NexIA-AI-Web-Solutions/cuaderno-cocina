# Flujos de cocina y existencias · 2026-10-17

Segunda revisión solicitada por el usuario después de la reparación visual. Tres agentes reales: recetas/Esencial, módulos profesionales y auditor independiente/Integral. Se conserva Vue/Vuetify y el backend productivo; los cambios son de interfaz y estado del cliente.

## Problemas corregidos

- Búsqueda rápida: Avanzada conserva la consulta; Enter sobre Cerrar no navega a una receta; teclado de selección limitado al buscador, compatible con composición de texto y Cmd+K. La tarjeta completa abre el resultado.
- Raciones: control visible de 44 px, explicación de que el ajuste es temporal, validación positiva y cancelación sin conservar un borrador descartado. Enlaces con `?servings=2.5` mantienen la fracción en vez de truncarla a 2.
- Editor: acciones «Añadir ingrediente» y «Pegar lista» con texto y tamaño táctil; ejemplo por líneas y envío vacío desactivado.
- Precios: ejemplo de envase completo; guardar con éxito limpia/cierra el formulario y muestra el formato creado, sin borrar un borrador o filtro cambiado durante la solicitud. Los errores conservan el formulario.
- Producción: Servicio aparece antes que las herramientas especializadas. Reservas: notas y motivo compactos, ampliables y con requisito visible.
- Despensa: retirar comienza con cantidad vacía, muestra disponible/unidad y requiere indicar cuánto; mover explica que traslada toda la existencia. Acciones explícitas y ayuda pertinente.
- Compras: cancelar/revertir exige revisar su efecto sobre existencias; abrir o volver no envía una escritura. Recepción filtra por alimento e incluye saldos cero, con comprobación previa de alimento/hogar. Ofertas esperan formato/proveedor y cantidades se presentan sin ceros sobrantes mediante aritmética exacta.

## Verificación

- 95/95 pruebas focalizadas, sin omitidas: búsqueda/presentación, roles/precios, cocina nativa, compras/stock y pruebas funcionales de raciones, selector y confirmaciones.
- Vue typecheck completo y Vite build: exit 0. Se corrigió el error de tipo del saldo opcional detectado en la primera compilación de tipos.
- Evidencia roja/verde: query perdida y Enter en botones; borrador/raciones cero/fraccionarias; formulario de precio; retirada total predeterminada; confirmaciones y destinos.
- Navegador Chromium con API autenticada real y estáticos del candidato: móvil/tableta/escritorio, 390×844, 768×1024, 1024×768, 1440×900; auditor añade 360 px.
- Las escrituras de confirmaciones se prueban con interceptación o harness local; ninguna recepción, cancelación, precio, servicio o retirada real se guarda para validar estos cambios. Los registros automáticos de visita a recetas se bloquean en la comprobación final.

Capturas, scripts y logs extensos: `/home/kripta/cuaderno-ux-round2-20261017/`. Estados de autenticación fuera de Git. Ver los JSON adjuntos para aceptación y revisión finales.

Comandos desde la raíz del worktree:

```sh
/opt/jaautomation/runtime/node-v24.19.0/bin/node --test --test-concurrency=1 vue3/src/cuaderno/globalSearchWorkflow.test.mjs vue3/src/cuaderno/modernPresentation.test.mjs vue3/src/cuaderno/operationalRolePage.test.mjs vue3/src/cuaderno/nativeKitchenUx.test.mjs vue3/src/cuaderno/purchasingPanel.test.mjs vue3/src/cuaderno/purchasingUi.test.mjs vue3/src/cuaderno/nativePurchasingUx.test.mjs vue3/src/cuaderno/stockMovementUi.test.mjs vue3/src/cuaderno/functional/recipeScalingFunctional.test.mjs vue3/src/cuaderno/functional/modelSelectFunctional.test.mjs vue3/src/cuaderno/functional/purchaseActionsFunctional.test.mjs vue3/src/cuaderno/functional/nativeRecipeWriteFunctional.test.mjs
cd vue3
/opt/jaautomation/runtime/node-v24.19.0/bin/node node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.app.json --pretty false
/opt/jaautomation/runtime/node-v24.19.0/bin/node node_modules/vite/bin/vite.js build
```

## Entrega y límites

Sólo activos Vue sobre la imagen productiva anterior `cuaderno-ui:20261017-80d671f`. Sin modelos, migraciones, permisos o aritmética de backend nuevos. Backup de configuración y dump PostgreSQL validado: `/var/backups/cuaderno-cocina/ux-round2-20261017` con permisos restringidos.

Rollback de interfaz: restaurar sólo `CUADERNO_IMAGE=cuaderno-ui:20261017-80d671f` en el env productivo y recrear exclusivamente web con el Compose existente (`up -d --no-deps --pull never web`). No restaurar la BD para revertir estos estáticos.

No certifica todos los flujos, Firefox/WebKit ni iPad físico. No se probaron escrituras de negocio contra producción. El selector nativo mantiene su paginación/búsqueda heredada; este cambio limita el destino por alimento, no rediseña toda la gestión de inventario.
