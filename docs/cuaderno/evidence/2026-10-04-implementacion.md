# Implementación de los hallazgos de auditoría — 4 de octubre de 2026

Este documento registra la implementación realizada después de [AUDITORIA_2026-10-04](../AUDITORIA_2026-10-04.md) y separa tres estados: código incorporado, evidencia ya obtenida y certificación todavía pendiente. Es un checkpoint de trabajo verificable. **No declara DONE, G7, release final ni autorización para producción.** El candidato ejecutable completo todavía se está construyendo y debe superar navegador, rendimiento, scan, upgrade y recuperación con una misma identidad de fuente e imagen.

## Resultado técnico incorporado

La revisión independiente posterior al primer build encontró un bloqueo de lectura en Producción: el `fieldset` deshabilitado también impedía a Consulta actualizar, imprimir y abrir la preparación. Se sustituyó por controles mutantes deshabilitados individualmente y guardas en handlers. El panel de preparación recibe el permiso operativo y conserva GET/recarga; su checkbox y PUT quedan bloqueados para Consulta. TDD: página 1/1 y preparación 4/4 PASS, con rojo previo tanto del fieldset heredado como del checkbox. Compras restringe también el cálculo POST de reposición: componente 2/2 PASS, con rojo previo. La aceptación Playwright incorpora estas lecturas y la restricción de reposición. El candidato final se reconstruye después de esas correcciones; el primer build no certifica la nueva fuente.

La primera tanda Playwright multiagente sobre `088b44a0` encontró una petición incorrecta real: los dos selectores de proveedor deshabilitados seguían consultando `Supermarket` para Consulta. Ahora solo buscan al cargar cuando el rol puede operar; componente RED→GREEN 2/2 cubre ambos selectores y mantiene las búsquedas para operadores. El arnés tenía además tres errores contrastados por los revisores: un locator genérico colisionaba con el enlace accesible «Recetas»; el PDF se capturaba antes de renderizar la SPA; y una escritura sobre ID nativo fijo suponía 403 para todo guest. El contrato nativo verificado permite escrituras del propietario/hogar y oculta filas ajenas: no se cambian permisos para satisfacer esa suposición. La prueba concurrente usa filas visibles del fixture y conserva comprobaciones independientes de denegación Cuaderno. Los fallos, trazas y PDF vacío se conservan; la aceptación completa debe repetirse con la fuente corregida.

### Arquitectura, permisos y contratos

- Las APIs Cuaderno comparten una base que resuelve el contexto de Space/Hogar y aplica lectura operativa acotada. Consulta puede leer los recursos permitidos de su contexto; las mutaciones siguen exigiendo Cocina/Responsable y autorización de servidor. Los filtros conservan privacidad de recetas, alimentos, existencias, servicios y grafos privados. El middleware de scope toma un snapshot por petición y evita consultas repetidas.
- Las responsabilidades de precios, historial, compras, mínimos, preparación, rendimientos y visibilidad se han separado en módulos de API/servicio. La lógica de dominio sigue fuera de las vistas para producción, stock, subrecetas y planes de servicio.
- Los límites HTTP validan objetos raíz, claves admitidas, arrays, IDs seguros, estados, revisiones, fechas y envelopes completos. Un `2xx` malformado ya no reemplaza estado válido en el cliente. Los errores de dominio de la ficha de producción se traducen a respuestas 400 en lugar de escapar como `KeyError`/500.
- El schema OpenAPI se genera sin errores ni avisos. Se activó la separación request/response y el hook conserva IDs obligatorios en respuestas y opcionales/escribibles en requests anidados. El SDK Vue fue regenerado con el generador fijado; incluye modelos Cuaderno, requests nativos, decimales `string | integer` donde corresponde y revisiones opacas sin conversión a `Date`.

### Decimales, concurrencia y trazabilidad

- Cantidades y dinero se mantienen como texto decimal en los límites. Producción usa contexto local de 64 dígitos para consolidación y escalado; no pasa por `float`. Se cubren 32/16, coma española, acarreo, ratios, cero explícito, desconocido y redondeo monetario únicamente al presentar.
- La lista rápida y la lista nativa usan concurrencia optimista. Marcar y deshacer envían `If-Match`; el servidor bloquea la fila antes de comparar. Falta de precondición cuando se cambia `checked` devuelve 428, formato inválido 400 y revisión obsoleta 409 con estado vigente. La revisión es una cadena opaca que conserva microsegundos de PostgreSQL.
- El bulk nativo valida todas las revisiones antes de escribir. La cola offline mantiene FIFO, solo avanza la revisión tras su propio éxito y, ante 409, descarta contextos causalmente solapados, refresca y no reintenta una escritura a ciegas. Undo usa la revisión obtenida por la operación que revierte.
- Recepciones de compras inmovilizan los controles de contexto mientras hay POST. La respuesta solo limpia el borrador si pedido, existencia y cantidad siguen siendo los enviados; la clave de idempotencia permanece estable a través de retry y cambios A→B→A.
- Declaraciones de alérgenos guardan `created_by` y `created_at`. La migración no atribuye filas históricas: autor y fecha anteriores permanecen desconocidos. Lectura y UI conservan esos metadatos y normalizan la selección del último estado.

### Readiness, migración 0017 y operación

- Readiness deriva las migraciones pendientes del grafo real de Django, para todas las apps exigidas por el proyecto. Una migración actual o futura pendiente invalida la respuesta. `boot.sh` propaga fallos de migración y tareas de arranque; el proceso no continúa hacia Gunicorn después de un error.
- `0017_release_integrity_and_allergen_audit` añade constraints e índices de integridad: cantidades positivas, estados admitidos, ratio objetivo, reversión no reflexiva, precios actuales y movimientos. Su preflight informa conteos e IDs inválidos y detiene la migración sin corregir datos históricos de forma silenciosa.
- Los escritores secundarios, imports y bulk se alinearon con las invariantes de Space, cantidades, estados y relaciones. Las rutas de ledger conservan movimientos compensatorios, bloqueo transaccional, idempotencia y auditoría.
- El perfil productivo usa Python 3.13.16 y Node 24.21 fijados por digest verificado. El runtime baja a UID/GID 10001, expone healthcheck y explicita rutas escribibles. Compose incorpora reinicio, límites de recursos y logs acotados por tamaño/rotación; esta configuración necesita todavía inspección sobre la imagen candidata arrancada.
- La fuente queda ligada mediante identidad explícita `SOURCE_COMMIT` más manifiesto de worktree cuando procede. El build Vite y el service worker producen procedencia sobre los módulos reales y el Dockerfile empaca inventarios/SBOM. Esa unión de fuente, bytes, imagen y reportes deberá comprobarse otra vez sobre el candidato final.
- El tooling de backup/restore conserva guardas de destino, rechaza producción para los ensayos demo, verifica rutas/symlinks, DB y media, y compara fingerprints, tablas, secuencias y logins. Hay evidencia histórica útil, pero todavía falta crear y restaurar una copia nueva del candidato actual y ensayar rollback.

### Frontend, roles y TypeScript nativo

- La navegación de escritorio y móvil incluye Cuaderno según edición: precios en Esencial; producción en Profesional+; almacén/compras en Integral. Las capacidades se invalidan al cambiar de edición, reintentan después de un fetch fallido y fallan cerradas ante respuestas contradictorias o malformadas.
- Consulta ve datos y explicación de solo lectura. Crear, guardar precios, producir, mover stock, comprar, recibir, revertir, marcar y deshacer quedan deshabilitados y además protegidos en los handlers. Un 403 conserva el borrador. La carga de rol tardía no habilita escritura.
- Precios ofrece tabla de escritorio y tarjetas móviles con precio de envase, precio unitario, unidad, fecha efectiva, moneda ISO e historial. La lista presenta unidad, origen, receta/lista y estado de sincronización. Los envelopes inválidos preservan la última vista válida.
- Producción expone el desglose de comensales base, altas y cancelaciones, además del total. Moneda se obtiene del Space y falla cerrada si falta o es inválida; no se sustituye silenciosamente por EUR. Se añadieron claves i18n para los textos compartidos tocados, manteniendo español como entrega inicial.
- Importación desde fuente convierte keywords, pasos, ingredientes, unidades y orden a requests nativos sin inventar IDs de catálogo. Solo asigna a la UI una `Recipe` devuelta y validada por servidor. Duplicado de receta y editores usan tipos request para creación y response para lectura.
- La deuda estricta se cerró sin `skip`, supresiones ni relajación de `tsconfig`: primero los 3 errores Cuaderno y después los 626 nativos. Se corrigieron drafts parciales, nulabilidad, índices, rutas, timers, formularios, props Vuetify y separación request/response. El checker global termina con cero diagnósticos.
- El runner Node de 33 archivos se corrigió para terminar sin procesos colgados: el renderer de `purchasingPanel.test.mjs` ahora implementa movimiento por anchor, `nextSibling` y retirada de nodos keyed antes de `app.unmount()`.

## Correspondencia A01–A27

| Hallazgo | Implementación actual | Estado de aceptación |
|---|---|---|
| A01 readiness | Grafo real de migraciones y arranque fail-fast. | Implementado y cubierto; falta smoke del runtime candidato. |
| A02 ficha de producción | Serializer/límite estricto, caps de grafo y traducción uniforme de `DomainError`. | Implementado con regresión de entradas inválidas. |
| A03 precisión | Contexto Decimal local de 64 dígitos y oráculos de texto 32/16. | Implementado y probado. |
| A04 CI propia | Workflow Cuaderno con toolchains fijadas, PostgreSQL, suites, schema, SDK y build propio. | Configurado; falta ejecución remota/protección de rama. |
| A05 gate de release | Registry/agregador distingue configurado, ejecutado, fallo y aprobado; liga evidencia a fuente. | Tooling verde; gate del candidato completo aún abierto. |
| A06 rendimiento | Se eliminaron consultas repetidas de roles/precios y se añadieron tests de eficiencia. | **Abierto: el último P95 válido sigue RED.** |
| A07 scan | Auditor admite scanner Linux y artefacto de imagen con herramienta/DB verificadas. | Implementado; scan Linux de la imagen final pendiente. |
| A08 procedencia/SBOM | Wiring Vite/Workbox/Docker, SBOM Python y frontend, manifiesto de fuente. | Implementado; binding final de imagen pendiente. |
| A09 upgrade/regresión | Harness y matrices preparados, migración 0017 caracterizada. | Pendiente sobre el mismo candidato final. |
| A10 navegador/a11y/impresión | Matriz Playwright de ediciones, roles y 390/768/1440 preparada. | Pendiente de ejecución y revisión visual sobre preview final. |
| A11 OpenAPI | Schema completo, split request/response, anotaciones de errores/revisión y SDK regenerado. | Schema estricto y tests de contrato verdes. |
| A12 invariantes | Constraints/preflight 0017 y validación en escritores secundarios. | Implementado; validación durante upgrade final pendiente. |
| A13 alérgenos | Autor/fecha, legado desconocido y render de auditoría. | Implementado y probado. |
| A14 zona/módulos | Fecha civil usa configuración efectiva; APIs/servicios divididos por responsabilidad. | Código y DST cubiertos; recorrido navegador pendiente. |
| A15 operación/recuperación | Compose operativo, log bound, healthcheck y tooling de copia/restauración protegido. | Restore/rollback del candidato y operación externa pendientes. |
| A16 privilegios/dependencias | UID/GID 10001, bases fijadas y conjunto Python 153 construido. | Build de dependencias verde; inspección runtime final pendiente. |
| A17 tests del kit | Discovery limitado a artefactos propios; JSON/JSONC se valida según formato. | Tooling completo verde. |
| A18 frontend unit/runtime | Markdown ya es unitario sin Docker; runner completo termina solo. | 149/149 verde en host; build Node 24 también estricto verde. |
| A19 recovery/discovery | Layouts, imports, rutas, symlinks y limpieza consistente en tooling. | Tests verdes; restore final pendiente. |
| A20 jerarquía documental | Audit como backlog, evidencia como historia y STATUS/checklist como control operativo. | Reconciliación final después de todos los gates pendiente. |
| A21 recepción tardía | Contexto bloqueado y limpieza condicionada al draft exacto. | Test real de componente con promesa controlada verde. |
| A22 lista compartida | `If-Match`, lock, revisión opaca, 409 y semántica de undo/cola. | Tests UI, SDK, store y PostgreSQL verdes; dos navegadores pendientes. |
| A23 typecheck | Corrección de 629 diagnósticos sin supresión. | **Cerrado técnicamente: checker global 0.** |
| A24 información/responsive | Unidad/origen/sync en lista; unitario/fecha/moneda y layout móvil en precios. | Unit/component verdes; verificación visual pendiente. |
| A25 Consulta | Capacidad compartida, UI bloqueada, handlers sin POST y lectura servidor acotada. | Tests de rol verdes; E2E cruzado pendiente. |
| A26 límites frontend | Parsers de envelopes, IDs/decimales/revisiones y protección contra respuestas tardías. | Helpers y componentes cubiertos. |
| A27 reservas/i18n/moneda | Desglose de comensales, moneda ISO estricta y textos compartidos localizados. | Implementado en el alcance acordado; revisión UX pendiente. |

## Evidencia actual

Estas cifras describen ejecuciones distintas y no deben sumarse como una tasa de cobertura.

| Capa | Resultado actual | Alcance y límite |
|---|---:|---|
| Regresión nativa | **1279 PASS**, 1712,31 s | Suite nativa actual. Debe repetirse si cambia código funcional del candidato. |
| Frontend Node | **149/149 PASS**, 33 archivos, 137086 ms | 142 Cuaderno + 5 store/revisión de compras + 2 `sourceImport`; ejecución secuencial terminó sola, sin fail/cancel/skip. Log: `.cuaderno-runs/frontend-node-tests-exit-clean.log`. |
| TypeScript host | **0 diagnósticos** | `npx vue-tsc --build --force --pretty false`; log limpio `.cuaderno-runs/typecheck-frontend-final.log`. |
| TypeScript Node 24 Docker | **PASS, 0 diagnósticos** | Toolchain fijada del stage frontend, no solo Node 25 del host. |
| Tooling | **229 PASS**, 41,629 s | Incluye kit/release/recovery; además OpenAPI **3 PASS** y comprobaciones de typecheck en contenedor **3 PASS**. |
| OpenAPI/SDK | **0 errores, 0 avisos** | Schema estricto y SDK regenerado con generador fijado. |
| Dependencias de producción | **153 paquetes PASS** | Target Python 3.13.16 construido e inspeccionado; incluye la evidencia del backport OAuth. No certifica aún el runtime completo. |
| Migración/ACL/concurrencia | Suites focales verdes dentro de las matrices anteriores | PostgreSQL real aislado para locks, revisiones, privacidad, roles y 0017. |

La cifra frontend anterior de 138 pruebas quedó obsoleta al añadirse cuatro regresiones y al contabilizar de forma completa los archivos nativos/source import. La fuente actual contiene 149 `test(...)`: 142 Cuaderno, 5 de compras nativas y 2 de importación. La ejecución agregada actual confirma exactamente esas 149.

## Bloqueos y validaciones pendientes

1. **Rendimiento continúa rojo.** La última evidencia válida mantiene P95 por encima del presupuesto: coste secuencial 303,960 ms frente a 300; servicios 226,423 ms secuencial y 1026,090 ms concurrente; movimientos 213,380/1398,686 ms; formatos 530,232/2158,155 ms, con presupuesto de 500 ms salvo coste. Las optimizaciones incorporadas no autorizan declarar mejora hasta repetir el benchmark completo, sin compiladores/builds compitiendo y con el mismo dataset.
2. **Mismo candidato.** La imagen/runtime completo seguía construyéndose al redactar este checkpoint. Los PASS de dependencias, frontend y suites no se convierten todavía en certificación de una única imagen. Hay que congelar fuente, registrar manifiesto/digest y repetir los gates que dependan del artefacto.
3. **Navegador.** Falta la ejecución Playwright multiagente sobre el preview candidato: ediciones, roles, viewports, teclado/foco, accesibilidad, conflictos de dos sesiones, pérdida de red, consola, impresión y revisión visual. El harness preparado no equivale a sus resultados.
4. **Recuperación.** Falta upgrade desde el pin, nueva copia, restore a DB/media nuevas y rollback del candidato exacto. La evidencia histórica prueba el procedimiento anterior, no esta fuente.
5. **Seguridad/procedencia.** Falta auditoría Linux de la imagen final, informe Grype JSON completo, binding de SBOM/procedencia a digest y revisión explícita de avisos. Un inventario estructural o el backport OAuth por sí solos no cierran el scan.
6. **Operación externa.** VPS, TLS/proxy real, alertas, copias externas, RPO/RTO e iPad físico siguen fuera de la evidencia local y requieren entorno/autorización específicos.

Hasta que esas validaciones terminen en verde o exista una excepción revisada y documentada, este trabajo permanece como implementación avanzada y candidato en preparación, no como release aprobada.
