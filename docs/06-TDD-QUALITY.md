# 06 · TDD, calidad y formato

## TDD operativo

Cada regla comienza como test del comportamiento esperado. La prueba RED debe fallar por ausencia/error de esa regla, no solo por un import roto. Guardar comando y código de salida en evidencia del paquete. Implementación mínima → GREEN → refactor → volver a ejecutar. Un test escrito después del código se identifica honestamente como test de regresión, no evidencia retroactiva de TDD.

Los mocks sirven para límites externos, no sustituyen SQLite o el navegador en los flujos que se certifican. Tests de costes usan resultados fijos revisados, no llaman a la misma función de producción para calcular el esperado.

## Capas

**Unitarias:** parser decimal es-ES, unidades, precio cero/desconocido, escalado, redondeos, DAG, mermas, contribución, necesidades de compra, ledger y claves de idempotencia. Propiedades: escalado proporcional antes de redondeo; convertir y volver recupera cantidad; stock nunca negativo; export/import estable.

**Integración:** DB SQLite temporal REAL por test suite, migrations desde cero, upgrades, restricciones, permisos de servicio, versiones concurrentes, transacciones de stock, import rollback, recepción parcial y sesión expirada. No usar la BD del desarrollador.

**E2E:** cuenta local sintética, navegador real y servidor del build, no solo servidor dev. Login, alta ingrediente, receta, guardar, reabrir, modificar precio, comprobar costes, escalar, imprimir, buscar, export/import, roles y URLs prohibidas. Repetir las rutas principales por edición.

**Seguridad:** acceso sin sesión, CSRF/origin, endpoint protegido por edición y rol, recursos privados, subidas inválidas, CSV formula injection, zip traversal/bombas, rate limit, revocación de sesión y prohibición de registro público.

**Operación:** construir desde checkout limpio; iniciar con datos persistentes; backup consistente; restore en otra carpeta; verificar integridad y saldos; migración y rollback documentado.

## Comandos que debe crear T002

| Comando | Resultado |
|---|---|
| `pnpm format:check` | Prettier check, sin modificar en CI |
| `pnpm lint` | ESLint con TypeScript/Svelte, sin warnings ignorados a granel |
| `pnpm check` | svelte-check + TypeScript strict |
| `pnpm test:unit` | Vitest dominio |
| `pnpm test:integration` | DB real aislada |
| `pnpm test:coverage` | Cobertura real con umbrales |
| `pnpm build` | Build adapter-node |
| `pnpm verify` | Format, lint, check, unitarias, integración, cobertura y build |
| `pnpm test:e2e` | Smoke Chromium en build |
| `pnpm test:e2e:release` | Chromium/WebKit/Firefox y matriz responsive |
| `pnpm test:security` | Suite de permisos, datos/archivos y abuso |
| `pnpm test:restore` | Backup y restore aislados |
| `pnpm bench` | Dataset fijo y métricas reproducibles |
| `pnpm release:check` | Agrega comprobaciones de release y manifiesto |

Scripts multiplataforma Node/tsx; no `rm -rf`, `cp` o asignaciones de variables Bash como única implementación en package.json. No usar `--passWithNoTests`. Las suites vacías deben fallar antes de declarar un módulo terminado.

## Umbrales iniciales del proyecto

Dominio: mínimo 95 % de ramas y 98 % de líneas, excluyendo solo tipos/generados con justificación. Servicios críticos (auth, edición, import, stock): mínimo 90 % de ramas. Cobertura global no permite esconder un motor sin probar. No exigir 100 % a plantillas sin sentido; cada flujo visible tiene E2E.

Sin `any` silencioso, `@ts-ignore`, errores de hidratación, warnings Svelte de accesibilidad descartados por lote o `test.skip` para el alcance obligatorio. Una excepción estrecha requiere motivo y revisión.

## Formato

UTF-8, LF, dos espacios para TS/JSON/Svelte; ancho 100; Prettier para Svelte/Markdown; imports ordenados con un único mecanismo. Español en UI, documentación y mensajes orientados al usuario. Identificadores técnicos y nombres de librerías en inglés por consistencia de ecosistema. Comentarios explican el porqué de una regla, no narran cada línea.

Funciones pequeñas con contratos explícitos; no umbrales arbitrarios de líneas usados para multiplicar archivos. Errores de dominio discriminados, errores HTTP traducidos sin filtrar SQL/rutas internas.

## CI

Crear CI con permisos mínimos, Linux + Windows para unitarias/integración/build, E2E al menos en Linux con motores requeridos. Fijar acciones a revisiones verificadas, lockfile obligatorio, caché del gestor sin secretos, artefactos de fallos con retención limitada. No instalar navegadores en la imagen de producción.

Auditar dependencias y licencias; un fallo de red se reporta, no se convierte en auditoría aprobada. Vulnerabilidad crítica/alta aplicable sin mitigación bloquea release. Una alerta no aplicable necesita evaluación documentada, no `ignore all`.
