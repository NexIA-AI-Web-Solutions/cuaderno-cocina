# Estado del producto

Actualización: 30 de septiembre de 2026. G7 sigue abierto. El propietario autorizó trabajo local; no hubo push, publicación, acceso a datos reales ni despliegue VPS. Los agentes de esta ronda son GPT-6.1 Sol, conforme a la restricción Sol6.1/Luna6. No se atribuye un modelo efectivo a la sesión principal sin evidencia del cliente.

## Preview y código

Abre http://127.0.0.1:18081. La aplicación ejecuta Tandoor derivado, Django/DRF, Vue/Vuetify y PostgreSQL; las referencias donantes no participan en runtime.

- Imagen: `sha256:59172af037dad2c4cc5762ecd5df24396de23b6bb05b78e5ac3d11d9d0edad9f`.
- Código efectivo: `88be31ec5a689699277c7e9c55aa10552344fb47+worktree.e9babaf9a96dce8dffbb87680f19d695a1e11d2e5d9c618f4baf07e8b4f734cc`.
- Build/arranque: `063934Z-local-up-97392261` PASS256.5s. Inspecciones de web e imagen coinciden; readiness healthy, tests de cookbook/cuaderno excluidos.
- Esquema: cookbook0243 y cuaderno0016. Incluye inventario de build8231ee566, protección de reversión413abf14e, valoraciónd4e29a10b y causa53e2c0671/UI88be31ec5. Cambios posteriores de documentación/herramientas no alteran esa identidad compilada.

Cuentas DEMO de uso local: `demo-esencial`, `demo-profesional`, `demo-integral`. Contraseña e instrucciones en [MANUAL_ES](MANUAL_ES.md). El entorno separado G0/18080 sirve para tests y no es el artefacto de entrega.

## Resultado vigente

| Comprobación | Resultado y alcance |
|---|---|
| Integración PostgreSQL candidata | `062615Z-integration-32108451` PASS250/250 en317.377s; incluye causa13/permisos17/reversión4/valoración11. No atribuir al runtime c07 anterior. |
| Autorización entre Spaces | `043447Z-group-cache-isolation-0b9eea69` PASS17/17, incluidos cuatro casos de caracterización posteriores. No sumar17 a218 como suites disjuntas. |
| Valoración WASTE | `053556Z-waste-valuation-4d88d0fa` PASS11/11; reposición congelada, unknown=null, gratis explícito0, scope y metadata legacy. Review independiente, commitd4e29a10b compilado en591. |
| Reversión parcial candidata | RED3/4→`052148Z-production-reversal-integrity-71a44aa3` PASS4; compras documental `053141Z-purchase-documents-a246a118` PASS2. Commit413abf14e; reversión completa del servicio sigue pendiente. |
| API causa candidata | `061901Z-waste-api-4b2417f8` PASS13, review independiente y commit53e2c0671. Reintentos legacy preservados sin crear nuevos desperdicios sin motivo. |
| UI historial/formulario | Helpers7 `063255Z-stock-movement-ui-3015d95b` y SFCvirtual3 `063252Z-almacen-panel-a7b784e7` PASS; draft/key/error/carrera de POST, review independiente y commit88be31ec5 compilado. No DOM/browser. |
| HTTP desperdicio | `064607Z-release-waste-3096d45b` PASS591:0.125L→0.8EUR, replay/conflicto/CSRF/ediciones y movimiento4/reversal5; saldo5 restaurado sin borrar logs. |
| Preparación persistente | PostgreSQL17, helperUI10 y SFCvirtual3 pasan. El montaje virtual no prueba DOM, Vuetify real ni navegador. |
| HTTP preparación | `043636Z-release-preparation-cf59c1d3` PASS tres cuentas/c07; reutiliza dos servicios DEMO, cuatro cambios de checklist, saldos/snapshots intactos. Auditoría no verificada por ese HTTP. |
| HTTP precios | `043854Z-release-prices-0381a794` PASS tres cuentas/c07; coste2.56, anterior desconocido, vacíos400/extremos414, cero escrituras del dominio. |
| Migración desde pin | `070137Z-migrations-c39da16a` PASS513.173s: pin689 sin Cuaderno→imagen591 hasta0016; login/GET200/POST201/reopen200 mediante DjangoClient y PostgreSQL real, receta creada por API preservada; privada/Step/stock5.125/hash financiero y checklist check/stale/noop. No socketHTTP/browser. |
| Backup/restore | `065043Z-restore-84bdbe5b` PASS591:114tablas/931filas/110secuencias/3media;3usuarios/5costes/3saldos/4finanzas/4servicios/4preparaciones con2ítems; incluye par desperdicio/reversión en hash de tablas. |
| Suite nativa | `050917Z-native-regression-5d9c2d8b` exit124timeout1200, salida1279passed/1warning en1243.57s, ejecutada sola. Resultado no aceptado; diagnóstico de duración pendiente. |
| Typecheck efectivo | `063242Z-typecheck-3ac97691` RED626, cero Cuaderno/service-worker; baseline pin650. Los antiguos PASS sin `-p` eran vacuos. |
| Lint Cuaderno | `061907Z-format-83245b91` PASS0; no equivale a lint de todo upstream. |
| Rendimiento | `013745Z-performance-307f57cd` RED3: secuencial cumple, p95 concurrentes808.857/673.347/2237.400ms supera500. No se elevó umbral. |
| Inventario/SBOM | Stage Linux453 validado `064245Z-image-frontend-sbom-cc41423f`; JSON preservado en591, Node/generador ausentes. Host451/Python anterior153 también validados. No cierre JS ni escaneo OS. |
| Auditoría runtime | `070438Z-runtime-audit-84c067b1` exit1 sobre591:153Python/63Alpine, cero consultas irresueltas, advisory OAuthlib por versión conservado; backport exacto comprobado. SBOM153 válido `070555Z-runtime-sbom-validate-b158f91f`, no escaneoOS. |
| Navegador | Reintento B04: no browser disponible/list=[]; capturas, impresión y responsive sin verificar. |

El restore recuperó el snapshot del bundle `data/cuaderno/backups/20260930T064711Z-99941210` en `cuaderno_restore_d4106c41d8a9467ca9696d0efd4dad21`. Conserva hashes de tablas/secuencias/media y fingerprint funcional, incluido el par desperdicio/reversión. Dump SHA256 `154af8ea8c89db65439fa383eca481e0c7c8c905580f1689176f5ab7e17a0a4f`; fingerprint `b8fca9bf6bb85039ad65d2ba2f4788271f3d01d6dbeb12a90c1dde902dfd7430`. No se compara una BD viva posterior con el punto del dump. Restore93.097s, pausa11.907s; no SLA ni rollback completo.

## Correcciones revisadas de esta ronda

Se conserva la interfaz y el dominio nativos. Los precios comerciales siguen como metadata: Esencial500€+17€/mes, Profesional1000€+20€/mes e Integral1500€+30€/mes. No se quitaron funciones nativas para justificar ediciones.

- Preparación: pasos canónicos Step congelados al confirmar ServicePlan, estados independientes y revisión/auditoría nativa. Los servicios anteriores a0016 no reciben instrucciones históricas inventadas. Commits9274ea4bb/0665234c3.
- Permisos: el caché global por usuario permitía usar el rol de otro Space o sobrevivir a una revocación. RED11/13→GREEN; snapshot fresco vinculado al request y1SQL, sin señales incompletas. Commit955cad4d7 y [ADR0006](adr/0006-request-local-group-permissions.md).
- Consultas: la autorización fresca añadió una consulta a preparación; integración204/205 detectó15>14. Middleware carga Space con membresía, conserva el presupuesto. Commitf6d2b474d.
- Entrega: arnés stock compara JSON numérico nativo sin afirmar precisión Decimal; upgrade retiene imagen exacta antes del ensayo largo. Fallos por pausa de backup y retag de imagen conservados en evidencia; se repitieron de forma secuencial.
- Procedencia: inventario instalado y validación real CycloneDX, límites de lectura/red y rechazo de JSONNaN/Infinity. Commit5908ae590. Revisiones independientes por bloque; no firma global.

Mermas versionadas, precios/historial/impacto, propiedades financieras, reservas/mínimos, compras, servicios y stock idempotente ya tienen código, persistencia y pruebas. Sus resultados históricos y límites están en [evidencia](evidence/2026-09-30-continuacion.md); no certifican cada writer nativo futuro.

## Gates y trabajo pendiente

| Gate | Estado | Falta para aceptación |
|---|---|---|
| G0 | PARCIAL | Capturas del baseline; resto de auditorías y pin documentados. |
| G1 | EN REVERIFICACIÓN | Cierre final de contratos y revisión de dependencias de tareas. |
| G2 | PREVIEW LOCAL UTILIZABLE / PARCIAL | Comprobar interacción visual, responsive e impresión; no certificación iPad. |
| G3 | PARCIAL | Completar scope profesional y validación visual de servicios/preparación. |
| G4 | PARCIAL | Valoración de stock/desperdicio vinculado y alcance de producción resultante. |
| G5 | PARCIAL | Matriz de roles operativos, rendimiento concurrente, escaneo OS/imagen y cierre de writers/permisos. |
| G6 | PARCIAL | Rollback completo, cierre exacto de JS empacado y handoff final. El inventario453 del stage sí está preservado en591. Build/migración/restore local actuales pasan. |
| G7 | NO FIRMADO | Scope completo, checks pendientes y revisión final de la entrega. |

Quedan batching del grafo, rendimiento concurrente y comprobación completa del intercambio de densidad/alérgenos/media/finanzas. El importador genérico no depende del export del programa antiguo. B01 bloquea solo su extractor; B02 iPad físico, B03 VPS sin autorización/destino y B04 navegador afectan sus comprobaciones concretas.

Desperdicio independiente con causa y valoración tiene código y tests reales, compilado en591 y verificado por HTTP `064607Z-release-waste-3096d45b`. No desperdicio adicional vinculado al servicio porque la producción ya descuenta la cantidad bruta. Clasificación atómica y reversión documental completa faltan. Smoke local revisado commit620015607 y unitarias7 `062524Z-release-waste-unit-0b8bd7a7`.

T003/T004: mapas revisados independientemente por integrity_review_sol (Sol6.1) y aceptados como auditorías documentales, sin atribuir ejecución a suites donantes. T002 sigue parcial: el baseline PostgreSQL/DjangoClient es trazable, falta baseline servido/visual. Perfil nativo18606 en curso, namespace nuevo y timeout1200 intacto; todavía no PASS.

`tasks.json` conserva dependencias y estados: REVIEW no es DONE. Consulta [RELEASE_CHECKLIST](RELEASE_CHECKLIST.md), [BLOCKERS](BLOCKERS.md) y el [checkpoint](RESUME.md) antes de continuar. No publicar ni probar contra una base real.
