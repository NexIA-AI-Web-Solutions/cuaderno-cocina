# Paquetes de trabajo

Cada tarea exige packet de paths concretos antes de delegar.

## T001 · G0 · Validar clones, contrato-premisa y modelos
Rol: `leader`. Depende de: ninguna.

Aceptación: Pins exactos; modelos/cliente registrados; no actualizar latest ni reabrir licencia.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T002 · G0 · Arrancar Tandoor sin modificaciones
Rol: `cocina_dataops`. Depende de: T001.

Aceptación: Login y receta nativa funcionan; comandos y versiones grabados.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T003 · G0 · Auditar entidades y puntos de extensión
Rol: `cocina_scout`. Depende de: T001.

Aceptación: Mapa de Recipe/Food/Unit/Spaces/props/Inventory y mutaciones con rutas reales.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T004 · G0 · Auditar Mealie KitchenOwl Grocy por capacidades
Rol: `cocina_scout`. Depende de: T001.

Aceptación: Matriz native/partial/absent, donor SHA/símbolos/tests; nada copiado aún.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T005 · G0 · Tests baseline y capturas del pin
Rol: `cocina_qa`. Depende de: T002.

Aceptación: Upstream tests y UI baseline; errores preexistentes identificados.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T006 · G0 · Congelar ADR y contratos API/modelos nuevos
Rol: `leader`. Depende de: T003, T004, T005.

Aceptación: Sin entidades duplicadas; source ownership decidido; registry con comandos reales.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T007 · G1 · Configurar Space español y modo Esencial
Rol: `cocina_backend`. Depende de: T006.

Aceptación: Privado, EUR/política precios, es-ES, menú simple; sin borrar native.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T008 · G1 · Contratos de unidades y precios manuales
Rol: `cocina_backend`. Depende de: T006.

Aceptación: Golden casos exactos; desconocidos/ambiguos rechazados; precio sin stock.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T009 · G1 · Persistir formatos y versiones de precios
Rol: `cocina_backend`. Depende de: T008.

Aceptación: Food nativo, historial, permisos y conflictos; migración nueva revisada.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T010 · G1 · Motor de escandallo y recálculo
Rol: `cocina_backend`. Depende de: T009.

Aceptación: Recipe nativa, escala sin guardar, invalidación de precios y completeness.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T011 · G1 · Pantalla ingredientes/precios Tandoor
Rol: `cocina_frontend`. Depende de: T009.

Aceptación: Crear envase y precio en móvil; validation conserva entrada; API real.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T012 · G1 · Integrar costes en receta nativa
Rol: `cocina_frontend`. Depende de: T010, T011.

Aceptación: Tandoor reconocible, selector raciones, coste/ración y warnings; no placeholders.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T013 · G1 · Gate Esencial end-to-end
Rol: `cocina_qa`. Depende de: T007, T012.

Aceptación: 5L/32→400mL=2.56; editar 35→2.80; reopen; privado; guardar receta.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T014 · G2 · Importación/exportación con preview
Rol: `cocina_dataops`. Depende de: T013.

Aceptación: Native primero; mapping, replay, informe, round-trip; sin datos reales.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T015 · G2 · Impresión y accesibilidad multi-dispositivo
Rol: `cocina_frontend`. Depende de: T013.

Aceptación: Imprimir costes completos/incompletos; cuatro viewports; keyboard.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T016 · G2 · Backup inicial y restore de Esencial
Rol: `cocina_dataops`. Depende de: T014.

Aceptación: DB+media restaurados nuevos, hashes y login/recetas correctos.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T017 · G2 · Revisión y preview local Esencial
Rol: `leader`. Depende de: T015, T016.

Aceptación: Revisor independiente y guía ejecutada; G2 evidencia, continuar desarrollo.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T018 · G3 · Subelaboraciones y rendimiento sin duplicación
Rol: `cocina_backend`. Depende de: T017.

Aceptación: Food.recipe nativo auditado, output units, ciclos y cache correctos.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T019 · G3 · Mermas y políticas de margen/presupuesto
Rol: `cocina_backend`. Depende de: T018.

Aceptación: Merma una vez, precio base homogéneo, no beneficio neto falso.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T020 · G3 · Menús, servicios y reservas internas
Rol: `cocina_backend`. Depende de: T017.

Aceptación: Extiende MealPlan, comensales/estado/snapshot, timezone correcta.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T021 · G3 · UX lista compartida inspirada en KitchenOwl
Rol: `cocina_frontend`. Depende de: T020.

Aceptación: Agrupación/rápido/deshacer, estado explícito y conflicto; sin offline writes.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T022 · G3 · Fichas producción y alérgenos declarados
Rol: `cocina_frontend`. Depende de: T019, T020.

Aceptación: Necesidades consolidadas y desconocidos visibles; no afirmación seguridad alimentaria.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T023 · G3 · Gate Profesional end-to-end
Rol: `cocina_qa`. Depende de: T021, T022.

Aceptación: Servicio 45 personas, salsa compartida, presupuesto/fichas; sin consumo automático.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T024 · G4 · ADR ledger único e integración stock nativo
Rol: `leader`. Depende de: T023.

Aceptación: InventoryEntry/Log existentes y todos escritores cubiertos; sin doble autoridad.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T025 · G4 · Proveedores formatos ofertas y pedidos
Rol: `cocina_backend`. Depende de: T024.

Aceptación: Food nativo, pedido no altera stock; cantidades/precios por formato.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T026 · G4 · Recepciones y movimientos idempotentes
Rol: `cocina_backend`. Depende de: T025.

Aceptación: Transacciones/locks, retry mismo payload vs diferente, parcial/reversión.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T027 · G4 · Consumo producción, desperdicio y auditoría
Rol: `cocina_backend`. Depende de: T026.

Aceptación: No doble consumo subreceta; permisos; saldo/ledger coherente con concurrencia.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T028 · G4 · Reposición e impacto de subidas
Rol: `cocina_backend`. Depende de: T027.

Aceptación: Disponible útil, envases al alza, precios nuevos sin reescribir snapshots.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T029 · G4 · Interfaz Integral integrada en Tandoor
Rol: `cocina_frontend`. Depende de: T028.

Aceptación: Recibir distinto pedir, stocks mínimos, historial; roles y mobile.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T030 · G4 · Gate Integral y regresión de ediciones
Rol: `cocina_qa`. Depende de: T029.

Aceptación: Recibir/reintentar/consumir simultáneo/desperdicio/revertir; T1/T2 no rompen.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T031 · G5 · Privacidad Spaces API/media/import hardening
Rol: `cocina_qa`. Depende de: T030.

Aceptación: Regresiones advisories y rutas nuevas, csrf/idor/zip/ssrf; sin secretos.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T032 · G5 · Performance índices bundle y almacenamiento
Rol: `cocina_backend`. Depende de: T030.

Aceptación: Dataset declarado, métricas antes/después, no regresión ocultada.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T033 · G5 · Diseño final y compatibilidad navegadores
Rol: `cocina_frontend`. Depende de: T031, T032.

Aceptación: Tandoor visual preservado; Chromium/Firefox/WebKit; sin fake iPad claim.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T034 · G6 · Imagen release y migración desde pin
Rol: `cocina_dataops`. Depende de: T033.

Aceptación: Build limpio, prod profile local, no donantes/tooling de test en runtime.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T035 · G6 · Restore completo, actualización y rollback
Rol: `cocina_dataops`. Depende de: T034.

Aceptación: Conteos/hashes/costes/saldos restaurados en destino nuevo; rollback ensayado.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T036 · G6 · Manual usuario/admin, SBOM y procedencia
Rol: `cocina_dataops`. Depende de: T035.

Aceptación: Comandos reales, screenshots sintéticas, source ledger y external pending.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T037 · G7 · Revisión independiente final
Rol: `cocina_reviewer`. Depende de: T036.

Aceptación: Inspección diffs, tests, claims, UX y datos; hallazgos cerrados o gate falla.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.

## T038 · G7 · Rerun limpio y paquete final
Rol: `leader`. Depende de: T037.

Aceptación: Todos gates con evidencia; start real, limitaciones y no despliegue sin permiso.

Usar TDD o caracterización/validación según tipo; adjuntar review y evidencia.
