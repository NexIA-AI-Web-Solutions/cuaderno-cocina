# Checkpoint local — 30 de septiembre de 2026

Proyecto sin terminar; G7 sigue abierto. Sin publicación, datos reales ni VPS.

HEAD al redactar: `b4db700cf`, rama `cuaderno/main`. Aplicación compilada de88be31ec5+worktree; b4db añade baseline nativo al arnés de upgrade, no cambia el runtime. Preservar cambios de git status; no reset ni limpieza. Solo agentes GPT‑6.1 Sol y GPT‑6 Luna. Tres hilos Sol6.1 reutilizados, sin subdelegación. La configuración no verifica el modelo efectivo de la sesión principal.

## Preview y entorno

`http://127.0.0.1:18081`, imagen efectiva `sha256:59172af037dad2c4cc5762ecd5df24396de23b6bb05b78e5ac3d11d9d0edad9f`.
Build `063934Z-local-up-97392261` PASS256.5s. Source ref `88be31ec5a689699277c7e9c55aa10552344fb47+worktree.e9babaf9a96dce8dffbb87680f19d695a1e11d2e5d9c618f4baf07e8b4f734cc`. Incluye8231/413/d4/369/53e/88: SBOM de stage, protección de producción, valoración/causa y UI segura de desperdicio. Readiness healthy; cookbook0243/cuaderno0016 aplicadas. Tests cookbook/cuaderno/Node/node_modules/generador ausentes del runtime, comprobado por inspección efectiva.

Cuentas SOLO locales: `demo-esencial`, `demo-profesional`, `demo-integral`; contraseña DEMO `Demo-Cocina-2026!`. Datos sintéticos. Cinco recetas, tres saldos y tres archivos media; cuatro servicios confirmados, dos de ellos con checklist nuevo. El HTTP de preparación conserva la auditoría de sus cuatro cambios aunque devuelve las casillas al estado inicial.

El contenedor de tests `cuaderno-g0-t002-web` usa18080 y PostgreSQL aislado, usuario `cuaderno_demo`. Copiar código/tests actuales allí antes de nuevos checks. Nunca ejecutar tests contra la BD preview.

## Resultados vigentes

- Integración PostgreSQL vigente `062615Z-integration-32108451`:250/250 PASS en317.377s, incluye causa13/permisos17/reversión4/valoración11. No sumar suites solapadas ni atribuir navegador.
- Permisos: RED11/13 en `040946Z-group-cache-isolation-d1ef94ec`; helper request-local `955cad4d7`. Integración posterior RED1 (15 consultas >14) en `041854Z-integration-27245941`; middleware select_related Space `f6d2b474d` restituye presupuesto sin elevarlo, preparación17 PASS `042324Z-service-preparation-88fc3bfa`.
- Preparación backend17, helpersUI10 y SFC virtual3 PASS. SFC unitario con API/widgets sustituidos: no DOM, Vuetify real ni navegador.
- HTTP preparación `043636Z-release-preparation-cf59c1d3`:PASS c07, sin nuevos servicios, cuatro cambios de casillas, snapshot y stock intactos. HTTP precios `043854Z-release-prices-0381a794`:PASS tres cuentas, coste2.56/impacto, entradas inválidas y sin escrituras de dominio.
- HTTP desperdicio `064607Z-release-waste-3096d45b`:PASS591;0.125L→0.8EUR, causa/retry/conflicto/ediciones/CSRF, movement4/reversal5, saldo5. Repetible sin borrar logs.
- Migración desde pin `070137Z-migrations-c39da16a`:PASS513.173s hasta0016 sobre591; pin689 sin Cuaderno, login/GET200/POST201/reopen200 DjangoClient con PostgreSQL real, recetaAPI preservada trasupgrade. Conserva privada/pasos/stock5.125/finanzas/checklist stale409/no-op. Imagen retenida como `cuaderno-cocina:upgrade-85ecca0e44d5`. No prueba socketHTTP/Vue/browser, T002 sigue parcial.
- Restore `065043Z-restore-84bdbe5b`:PASS591,114 tablas/931 filas/110 secuencias/3 media, dos ítems de preparación y par desperdicio/reversión. Bundle `data/cuaderno/backups/20260930T064711Z-99941210`; BD nueva `cuaderno_restore_d4106c41d8a9467ca9696d0efd4dad21`. No reemplaza preview ni demuestra rollback completo.
- Lint Cuaderno `061907Z-format-83245b91`:exit0, alcance cuaderno. Typecheck `063242Z-typecheck-3ac97691`:RED626, cero diagnósticos Cuaderno/service-worker; pin650, sin supresiones.
- Regresión nativa: `050917Z-native-regression-5d9c2d8b` exit124timeout1200; salida1279passed/1warning en1243.57s, corrió sola. Terminal58633 terminada. No convertir esa salida en PASS del runner; diagnóstico pendiente.
- Benchmark `013745Z-performance-307f57cd`:RED3 concurrentes; servicios808.857/movimientos673.347/formatos2237.4ms superan500. Secuencial coste242.964ms cumple300. Dataset real verificado; no hardware2CPU/2GiB ni benchmark navegador/red.
- Inventario frontend hostWindows451 validado044208Z; stageLinux453 preservado dentro de591 y validado064245Z. Incluye build/dev, no cierre exacto de JS empacado.
- Runtime audit `070438Z-runtime-audit-84c067b1`:exit1 sobre591,153 Python/63 Alpine, cero consultas PyPI irresueltas; aviso OAuthlib3.3.1 conservado por versión, backport exacto53f308e8 comprobado. Validación del SBOM153 `070555Z-runtime-sbom-validate-b158f91f`:PASS. No escaneo OS/imagen.
- Browser B04: el Browser autorizado no devuelve ningún navegador disponible. Sin capturas ni comprobación física iPad. No usar Playwright/CDP alternativo para eludir esta limitación.

## Ejecución y cuidados

Cada PowerShell nuevo requiere volver a definir variables. Serializar build, backups, restore y HTTP sobre el preview: el backup pausa escrituras y un smoke simultáneo ya falló por timeout. No retaggear la imagen durante upgrade. No compartir un namespace de tests entre procesos. La suite nativa corre sola, timeout1200 sin elevar.

```powershell
git status --short
$env:CUADERNO_ENV='local'
$env:CUADERNO_DEMO_PASSWORD='Demo-Cocina-2026!'
python scripts/cuaderno/check.py group-cache-isolation --allow-isolated-mutations
python scripts/cuaderno/check.py integration --allow-isolated-mutations
python scripts/cuaderno/check.py release-preparation --allow-isolated-mutations
python scripts/cuaderno/check.py release-prices --allow-isolated-mutations
$env:CUADERNO_BACKUP_TARGET='release'
python scripts/cuaderno/check.py restore --allow-isolated-mutations
python scripts/cuaderno/check.py frontend-sbom-validate
python scripts/cuaderno/check.py runtime-sbom-validate
```

No repetir estos checks a la vez. Usar `tooling/cuaderno/commands.json` y `check.py`; un comando verificado puede seguir siendo RED.

## Trabajo inmediato y carencias

Root integra docs/core/modelos/migraciones/config/locks. API53e/UI88/smoke620/upgradeb4db revisados independientemente e integrados. T003/T004 auditorías documentales aprobadas, DONE con evidenciaT003-T004-review; T002/T005 parciales no DONE.

Perfil nativo terminal18606 en curso: nuevo namespace `cuaderno_native_profile_20260930`, `check.py native-profile`, misma suite1279 y timeout1200, durations100/min0.25. No otro testDB/build/restore/HTTP pesado hasta acabar; no atribuir PASS antes del resultado. Antes: cpu.max/memory.max/pids.max sin límites, throttling/OOM0, no otro pytest activo. Resultado previo050917exit124 sigue vigente hasta un PASS real.

Dos escritores acotados Sol6.1: service_workflow_sol solo `cuaderno/tests/test_list_query_efficiency.py` (RED pendiente, sin tocar implementación); purchase_workflow_sol solo `cuaderno/tests/test_exchange_conversions.py` (RED pendiente, reutiliza UnitConversion). Root aún NO implementa esos huecos hasta RED funcional. Revisor integrity_review_sol disponible para docs y futuros bloques. No ejecuciónDB por workers mientras perfil activo.

Continuar implementación con prueba roja y revisión independiente: valoración/desperdicio vinculado, matriz operativa de roles, batching del grafo/rendimiento, intercambio completo, rollback ensayado. Inventario empacado/escaneo OS y revisión visual siguen abiertos. B01 bloquea únicamente extractor del programa antiguo; no el importador genérico. B02 iPad físico/B03 VPS no se afirman hechos.

Los archivos de documentación/registry listados por git status aún necesitan revisión y commit focalizado. No marcar todas las tareas DONE: dependencias y gates abiertos. Historia exacta de resultados/fallos: `evidence/2026-09-30-continuacion.md`. G7 no firmado.
