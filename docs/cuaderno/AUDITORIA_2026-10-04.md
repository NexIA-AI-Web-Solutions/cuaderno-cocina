# Auditoría integral de Cuaderno Cocina — 4 de octubre de 2026

## Dictamen y alcance

Existe una aplicación sustancial, derivada de Tandoor, con persistencia, APIs, interfaz Vue y pruebas propias. La prioridad es corregir defectos concretos y completar la aceptación del producto ya construido. No hace falta reiniciar el proyecto ni incorporar los tres donantes al runtime. **La entrega todavía no está aprobada.** Hay carencias de aceptación en varios gates G0–G6, además del cierre G7.

Esta auditoría responde a la petición de analizar la carpeta y documentar qué falta implementar, corregir y mejorar. Los únicos cambios realizados por este encargo son documentación. No se implementan aquí las correcciones propuestas, no se cambian estados de tareas a DONE y no se inicia la aplicación detenida.

Base inspeccionada: rama `cuaderno/main`, commit `83d0d6d6a362b2d46001dbc9d0a749d011414cd4`, checkout limpio al comenzar. Los números de línea de este informe corresponden a esa base. Se revisaron estructura, especificaciones, cambios respecto al pin, módulos propios, integración nativa, pruebas, scripts operativos, workflows, registros y evidencia local. Tres revisores acotados examinaron backend, frontend y release; el integrador contrastó sus hallazgos con rutas y código.

El análisis de donantes cubre pins, estado Git, límites de reutilización y unidades relevantes ya identificadas; no pretende certificar cada línea de sus 3.958 archivos ni ejecutar sus suites. Tampoco se auditan línea por línea `node_modules`, todos los blobs Git, imágenes binarias o todo el código upstream intacto. Las búsquedas y pruebas son una revisión amplia, no una prueba de ausencia de cualquier vulnerabilidad.

### Cómo interpretar la evidencia

- **Reproducido ahora:** comando o ejemplo ejecutado el 4 de octubre, con resultado en el [anexo de comprobaciones](evidence/2026-10-04-auditoria.md).
- **Confirmado por código:** condición visible en la base inspeccionada; cuando requiere Django/PostgreSQL, el efecto HTTP todavía debe cubrirse con una regresión real.
- **Histórico comprobado:** se leyó el reporte local del ensayo anterior; no se volvió a ejecutar ni se atribuye a la imagen o fuente actual por analogía.
- **Pendiente de verificar:** criterio requerido sin evidencia suficiente; no equivale a un fallo funcional demostrado.
- **Mejora propuesta:** reducción de riesgo o mantenimiento; no implica un incidente ocurrido.

Prioridades: **P1** antes de aprobar la entrega local o, cuando se indica expresamente, antes de admitir datos reales en producción; **P2** siguiente tanda de calidad/mantenimiento; **P3** mejora posterior. No se ha demostrado un incidente P0 que exija una intervención de emergencia.

## 1. Qué contiene realmente la carpeta

| Área | Observado | Papel y trabajo pendiente |
|---|---|---|
| Raíz | README, plan, guía Windows, manifest, tools, tests, validation y ZIP | Kit original; sus textos necesitan distinguir instalación inicial de continuación del producto existente. La raíz no es un repositorio Git. |
| `app/` | Repositorio de producto; 363 archivos versionados distintos respecto al pin Tandoor | Fuente principal. Preservar historia, licencias, migraciones y patches documentados. |
| `app/cuaderno/` | 117 archivos sin caché Python, unas 1,08 MB | Dominio, servicios, APIs, 16 migraciones y pruebas propias. Hay implementación real de las tres ediciones. |
| `app/vue3/src/cuaderno/` | 55 archivos, unas 416 KB | Páginas/componentes/helpers y pruebas frontend; falta aceptación en navegador. |
| `app/scripts/cuaderno/` | 48 archivos, unas 510 KB | Build, pruebas, backup, restore, rollback, auditorías y procedencia; varios caminos aún no están unidos en un gate único. |
| `app/docs/cuaderno/` | 58 archivos antes de esta auditoría, unas 737 KB | Especificación y abundante evidencia; algunas filas conservan estados históricos que dificultan localizar el estado vigente. |
| `app/.cuaderno-runs/` | 641 JSON de ejecución y logs asociados | Evidencia local ignorada por Git. Útil para contraste, pero no garantiza que otra máquina pueda reproducirla. |
| `app/data/` | 63 archivos, unos 3,65 GB de archivos regulares | Artefactos locales, scanners y archivos de imagen. Medida de archivos, no uso de Docker/VHD ni tamaño del runtime. `data/cuaderno/backups/` está vacío. |
| `overlay/` | 66 archivos | Plantilla histórica del kit, no espejo de `app/`. No reaplicarla sobre el producto. |
| `references/` | Tres clones limpios y fijados | Solo referencia; sin necesidad de levantarlos, actualizarlos ni copiar carpetas. |
| ZIP raíz | 75 entradas, 89.093 bytes; sin `app/` | Es el kit, no un paquete de entrega de la aplicación. |

Los tres manifests de fuentes —raíz, overlay y app— tienen contenido idéntico. Pins verificados en los clones:

| Fuente | Pin |
|---|---|
| Tandoor base | `7e1c427a0e17858ddc41bd198c79ccad77d3bd69` / `2.6.15` |
| Mealie | `0552eaa4a80031b8572849cca0ed95d07f1be001` / `v3.28.0` |
| KitchenOwl | `09aaf5fbd2343fcc10b12e906c63c3764dd38919` / `v0.7.10` |
| Grocy | `7d15c46bbdc35d4958cae99209ba170667dc1d64` / `v4.7.1` |

La arquitectura sigue siendo coherente: Vue/Vuetify → Django/DRF → PostgreSQL, con `Food`, `Unit`, `Recipe`, `MealPlan`, listas e inventario nativos. Los módulos Cuaderno amplían esas entidades. Mealie aporta referencias de importación, KitchenOwl referencias de lista compartida y Grocy referencias de compras/stock; no se ha encontrado un segundo backend donante en el runtime revisado.

## 2. Qué está implementado y qué falta aceptar

| Capacidad | Base existente | Falta para considerarla entregada |
|---|---|---|
| Precios manuales sin existencias | `PackageFormat`, `PriceVersion`, APIs y `PreciosPage` | Recorrido navegador completo, conflictos/error de red, precios desconocidos/gratuitos y versión efectiva de referencia. |
| Coste por receta y ración | Motor Decimal, conversiones nativas/densidad, panel en receta | Regresión final con dependencias productivas, P95 y comprobación visual al cambiar raciones/precios. |
| Recetas nativas | Editor, búsqueda, categorías, duplicación y fotos Tandoor conservados | Probar los recorridos nativos después de los patches de permisos, serialización y media. |
| Importación/exportación | Importadores nativos más intercambio genérico portable con preview | E2E de ida/vuelta con fotos, subrecetas, precios, conversiones y permisos; extractor del programa antiguo requiere muestra autorizada. |
| Impresión | Infraestructura nativa y controles de impresión en módulos | PDF/capturas reales, contenido completo y estado incompleto visible; comprobar saltos de página y tamaños. |
| Subelaboraciones/mermas | `RecipeYield`, política por ingrediente, coste y snapshots | Aceptación de edición/conflictos, precisión extrema y ausencia de doble merma en UI/API. |
| Menús/servicios/reservas internas | `MealPlan` y `ServicePlan`, confirmación, snapshot, producción y reversión | Flujo completo en navegador, varias recetas/servicios, fechas, permisos y recuperación tras timeout. |
| Preparación/alérgenos | Checklist persistente y declaraciones con estado desconocido | Autor/fecha de declaraciones, aceptación visual y distinción clara entre desconocido y ausencia declarada. |
| Lista compartida | Reutiliza `ShoppingList` nativa | Adición rápida, marcar/deshacer, dos sesiones, fuente y feedback de fallo; T021 sigue abierto. |
| Finanzas orientativas | Venta/presupuesto y ratio coste/precio sobre propiedades nativas | Aceptar políticas neto/bruto y límites de presentación; no llamarlo beneficio neto. |
| Proveedores/pedidos/recepciones | Proveedor nativo y documentos Cuaderno con recepción/reversión | E2E de recepción parcial, replay, cantidades/lotes y permisos; pedido nunca aumenta saldo. |
| Inventario/consumo/desperdicio | Ledger idempotente sobre inventario nativo, trazabilidad y compensaciones | Matriz final concurrente, todos los escritores nativos, merma teórica frente a desperdicio real y navegación al documento. |
| Mínimos/reposición/impacto | Servicios y pantallas propios ligados al catálogo | Listas grandes, permisos, unidades y cambios de precios; validar cálculos y presentación conjuntamente. |
| Recuperación | Backup/restore/rollback local con fingerprints | Nueva copia disponible, ensayo del artefacto final y procedimiento productivo separado. |
| Entrega reproducible | Dockerfile propio, imágenes históricas y constraints Python | CI propia, upgrade final, scan válido, SBOM/procedencia empacados, aceptación de todos los gates. |

Fortalezas que conviene conservar: bloqueos transaccionales de Space/entrada, claves de idempotencia, movimientos compensatorios, cero explícitamente gratuito, aislamiento de grafos privados, snapshots y revisiones de preparación/merma. El problema no se resuelve sustituyendo estas garantías por escrituras directas más simples.

## 3. Defectos y carencias concretas

### A01 — P1: readiness puede aprobar un esquema incompleto

**Evidencia:** `cuaderno/health.py:10` solo busca `0013_offer_free_equivalence`; existen `0014_price_explicit_free`, `0015_stockminimum` y `0016_servicepreparationitem`. Los healthchecks local y productivo confían en esa respuesta. Además, `boot.sh:89` ejecuta `python manage.py migrate` sin `set -e` ni comprobación explícita de retorno y continúa hacia Gunicorn en la línea 110.

**Impacto:** si una migración posterior falla, el proceso puede seguir arrancando y una base en 0013 parecer preparada aunque falten tablas o constraints requeridas. Es un camino confirmado por código; no se simuló un fallo de migración en una BD durante esta auditoría.

**Corrección:** hacer fallar el arranque ante error de migración/collectstatic y derivar readiness del grafo de migraciones requerido por el código actual, evitando otro literal que vuelva a quedarse antiguo. Mantener la respuesta pública mínima y sin detalles internos.

**Aceptación:** bases en 0013 y 0015 devuelven 503; base totalmente migrada, 200; cualquier migración requerida pendiente —también futura o de otra app incluida en el grafo exigido— invalida readiness hasta aplicarse. Un fallo deliberado de migración o collectstatic termina el contenedor con código no cero y no sirve tráfico de aplicación.

### A02 — P1: la ficha de producción admite entradas que terminan en excepciones internas

**Evidencia:** ruta `/api/cuaderno/production/` → `ProductionSheetView`, `cuaderno/api/operations.py:359–375`. Se extraen `component` y `quantity` sin serializer y se llama a `consolidate` fuera del bloque que traduce `DomainError`. `edges` y `recipe_ids` tampoco reciben aquí un contrato estructural completo. Los ejemplos puros `usages=[{}]` y cantidad `invalid` reproducen `KeyError` y `DomainError` respectivamente.

**Impacto:** entradas de un usuario autenticado autorizado pueden producir errores 500 y mensajes poco útiles. Un grafo arbitrariamente profundo también necesita límite. No se ha ejecutado la petición HTTP en esta tanda.

**Corrección:** serializer estricto para objeto raíz, arrays, identificadores, componentes, cantidades y grafo; límites de longitud/profundidad; traducción uniforme de errores de dominio a JSON 400; evitar escrituras ante validación fallida.

**Aceptación:** matriz de null, tipos incorrectos, campos ausentes, cantidades inválidas, ciclos, grafos profundos y listas excesivas devuelve 400 legible, sin 500 ni cambios de saldo. Caso válido conserva resultado exacto.

**Precisión del alcance:** `operations.ReplenishmentView` contiene validación similarmente débil, pero **no está conectada** en `cuaderno/urls.py`; la ruta activa usa `api.purchasing.ReplenishmentView`. Tratar la primera como código heredado a retirar/caracterizar, no como una vulnerabilidad demostrada de la ruta activa.

### A03 — P1: consolidación manual pierde precisión decimal admitida por el producto

**Reproducido ahora:** `cuaderno/domain/production.py:39–45` suma con el contexto Decimal ambiental, de precisión 28. Una única cantidad `1234567890123456.1234567890123456` se convierte en `1234567890123456.123456789012`. No hay que sumar dos líneas para perder dígitos. La función se usa en la ruta activa de ficha manual.

**Corrección:** aplicar la misma política explícita de precisión/intermedios que el resto del motor, validar límites de entrada y revisar la suma posterior de necesidades en `operations.py:375`. Caracterizar también `scale_covers`, `packs_to_buy` y `waste_value`, que conservan operaciones con contexto ambiental. No atribuir este defecto al ledger o a la reposición canónica: usan otros caminos y contextos propios.

**Aceptación:** una cantidad individual permanece idéntica; agrupación y orden de líneas no alteran el resultado dentro del contrato; entradas máximas 32/16, sumas con acarreo y divisiones recurrentes tienen oráculos independientes. Mantener redondeo monetario solo al presentar.

### A04 — P1: los workflows heredados no validan el repositorio propio

**Evidencia:** `.github/workflows/ci.yml:7`, `build-docker.yml:9`, `codeql-analysis.yml:11` y `docs.yml:12` condicionan los jobs al propietario `TandoorRecipes`. El origin del producto pertenece a `NexIA-AI-Web-Solutions`. El build heredado referencia el Dockerfile e imágenes upstream, no `deploy/cuaderno/Dockerfile`.

**Corrección:** workflow propio para la rama del producto, sin publicación automática, con toolchains de release, constraints, PostgreSQL aislado, suite Cuaderno y regresión nativa. No basta con quitar el `if`: CI usa Python 3.12/Node 22, instalación diferente del runtime y cachés frontend deficientes (`vue3/src/*` frente al `vue/src/*` de guardado).

**Aceptación:** checks realmente ejecutados sobre un checkout limpio; una rotura de Cuaderno falla el pipeline; un cambio en componente anidado o lock invalida caché; build de la imagen correcta. Configuración de protección de rama pendiente de comprobar por separado; este informe no afirma haberla inspeccionado.

### A05 — P1: no existe un gate de release ejecutable completo

**Evidencia:** hay 155 checks registrados, pero `e2e`, `security` y `release` tienen `argv: null` y `verified: false`. `pytest.ini:3` limita el descubrimiento predeterminado a `cookbook/tests`; ejecutar `pytest` sin más no cubre Cuaderno. El registry integra módulos explícitos que han crecido con el tiempo y aún no constituye una regresión completa del candidato final.

**Corrección:** agregador con matriz explícita, dependencias y propagación de fallos; distinguir comando conocido de resultado aprobado. Registrar HEAD, manifiesto de fuente, imagen, conjunto de dependencias y entorno en cada resultado. Mantener estados separados para no ejecutado, error ambiental, fallo funcional y aprobado.

**Aceptación:** una ejecución limpia puede acreditar todos los criterios obligatorios del candidato exacto; ausencia de comando/evidencia no produce verde; añadir un módulo de tests crítico no lo deja fuera silenciosamente.

### A06 — P1: rendimiento todavía incumple cinco aserciones

**Evidencia histórica contrastada:** `.cuaderno-runs/20260930T203010Z-performance-profile-35cb6393.json` tiene exit 1 y su log conserva cinco fallos. Dataset: 3.000 recetas, 45.000 ingredientes, 1.500 alimentos/formatos, 100.000 movimientos y 10 usuarios de prueba.

| Operación | P95 secuencial ms | P95 concurrente ms | Presupuesto ms |
|---|---:|---:|---:|
| Coste, 15 líneas | 303,960 | — | 300 |
| Servicios | 226,423 | 1.026,090 | 500 |
| Movimientos | 213,380 | 1.398,686 | 500 |
| Formatos | 530,232 | 2.158,155 | 500 |

**Corrección:** perfilar espera de locks, consultas/planes, middleware de permisos, serialización y saturación de workers por separado. Los bloqueos amplios de Space merecen medición, pero no se ha demostrado que sean la única causa. Comparar misma fuente, hardware, datos, configuración y carga antes/después. Una mejora de EXPLAIN aislada no acredita el endpoint completo.

**Aceptación:** presupuestos existentes cumplidos con dataset íntegro y concurrencia declarada, sin eliminar outliers, reducir datos ni relajar ACL. Medir también LCP/INP y aumento del bundle Esencial según `11-PERFORMANCE-AND-STORAGE.md`; hoy no hay aceptación navegador equivalente.

### A07 — P1: scan de imagen aún sin resultado válido y sin runner Linux integrado

**Evidencia:** último `image-audit` histórico termina con exit 1; el fichero `grype.json` vacío no es una lista vacía de vulnerabilidades. `scripts/cuaderno/image_audit.py:19–23,60–69` fija ejecutable/archivo Windows, mientras la continuación requiere ejecutar el binario Linux preparado. El script también depende de inspeccionar el preview, actualmente detenido.

**Corrección:** adaptar el límite de ejecución para scanner Linux aislado sobre el archivo de imagen exacto, con DB y binarios verificados; conservar hashes y fecha de la base de avisos. Evitar red/socket Docker dentro del scanner cuando se use el archivo retenido. Definir una forma verificable de asociar ese archivo con la imagen sin exigir arrancar la aplicación.

**Aceptación:** archivo JSON válido, completo y no truncado, identidad de imagen/archivo/DB/herramienta registrada, todos los avisos evaluados y resultado propagado al gate. Cero hallazgos es un resultado admisible si lo acredita un informe completo; un archivo vacío no lo acredita. El audit Python histórico detectó OAuthlib por versión pese al backport; registrar evidencia del parche y tratamiento explícito, sin borrar el aviso ni sustituir un scan OS por un inventario.

No se hizo una consulta actual de avisos externos: los IDs/versiones citados describen el resultado local guardado, no un certificado de seguridad vigente al día de la auditoría.

### A08 — P1: procedencia frontend y SBOM final incompletos

**Evidencia:** `scripts/cuaderno/frontend_build_provenance.mjs` existe y sus pruebas pasan, pero no está integrado en Vite/Workbox/Docker. `deploy/cuaderno/Dockerfile:7–10,37–40` genera/copia inventario frontend instalado y constraints Python; no empaca un SBOM Python ni una relación final de módulos/chunks. `SOURCE_COMMIT` admite por defecto `worktree`.

**Corrección:** conectar recolección de módulos a los builds principal y service worker; calcular hashes después de las transformaciones finales; empacar reportes, SBOM Python y manifiesto de fuente. Exigir identidad explícita de release. Resolver y documentar cuál lock/frontend es autoritativo: Docker usa `yarn.lock`; también existe `package-lock.json`.

**Aceptación:** build limpio real produce reportes que corresponden a los bytes finales y al conjunto instalado; todos los componentes relevantes tienen procedencia o una excepción explícita. Las 153 versiones Python y los 453 componentes frontend de la evidencia anterior son inventarios, no una prueba de reproducibilidad byte a byte ni del cierre JS.

### A09 — P1: falta repetir upgrade y regresión sobre el artefacto final

**Evidencia:** integración histórica 341/341 y particiones nativas aprobadas corresponden a distintas fuentes/dependencias; el upgrade citado es de una imagen anterior. El propio STATUS excluye una aprobación global bajo las mismas 153 dependencias de la imagen a3c.

**Corrección:** congelar candidato después de las correcciones; migrar una BD sintética del pin al candidato en destino nuevo; ejecutar suite Cuaderno completa, API nativa, vistas, importación/auth y carreras relevantes con el mismo runtime. Medir el tiempo de la regresión antes de modificar timeouts: hubo una ejecución con salida de tests pero timeout del runner, que no cuenta como PASS.

**Aceptación:** migraciones, datos, secuencias, login, permisos, media, coste, saldo, idempotencia y reversión verificados en la misma identidad de release; cero nuevos skips para ocultar fallos. No repetir suites completas sobre cada cambio de documentación.

### A10 — P1: aceptación navegador, impresión y accesibilidad sin cerrar

**Evidencia:** B04 y `e2e` sin comando; tests de SFC/helpers no sustituyen DOM real, CSS, navegación ni servidor. El frontend actual tiene pruebas útiles, pero no evidencia completa de las tres ediciones en Chromium/Firefox/WebKit.

**Corrección:** instalar/configurar el recorrido E2E autorizado sobre build y PostgreSQL sintético cuando se reanude la validación; cubrir 390×844, 768×1024, 1024×768 y 1440×900. Teclado/foco, targets táctiles, scroll, formularios con coma, pérdida de red, conflictos, login/logout y caché privada; impresión real de recetas/fichas.

**Aceptación:** capturas, trazas, consola/red y PDFs identificados por commit/imagen, recorridos completos de Esencial→Profesional→Integral, revisión visual independiente. Mantener iPad físico como comprobación separada; no afirmar que la emulación lo certifica.

### A11 — P2: contratos OpenAPI incompletos y cliente manual

**Evidencia:** las anotaciones `extend_schema` de Cuaderno están concentradas en `api/finance.py:48,55`; muchas vistas heredan directamente de APIView y validan manualmente. Las páginas Vue construyen rutas/payloads a mano. No se ejecutó generación del schema durante esta revisión, por lo que no se afirma que sus paths desaparezcan todos; sí falta descripción explícita de gran parte de requests/responses/errores.

**Corrección:** inventario ruta/método/permiso/serializer/respuesta, contratos de decimales como strings y errores 400/403/404/409/428, revisión/idempotencia; generar cliente o comprobar sus tipos contra schema. Priorizar endpoints de escritura.

**Aceptación:** validación OpenAPI sin contratos vacíos de Cuaderno; tests de compatibilidad del cliente; cambios incompatibles detectados por CI.

### A12 — P2: reforzar invariantes en almacenamiento y escritores secundarios

**Evidencia:** `cuaderno/models.py` no incluye checks escalares equivalentes en todos los modelos: cantidad de formato (42), movimientos (91–108), comensales/estado (206–219), rendimiento (287–292). Varias relaciones guardan `space` además de la FK, sin constraint relacional automática. Ya hay protecciones útiles en servicios y tests de corrupción; no se ha demostrado una vía pública que eluda todas ellas.

**Corrección:** definir tabla de invariantes y quién las garantiza; CheckConstraints para condiciones locales compatibles con el dominio, auditoría/migración de filas existentes, validación central para FKs/Space y rutas de bulk/import/admin. Un `clean()` de modelo por sí solo no se ejecuta en todas las escrituras ORM; una condición entre tablas no se resuelve con un simple CHECK SQL.

**Aceptación:** escrituras directas/bulk inválidas se rechazan o se detectan de forma explícita; lecturas fallan de forma segura; migración maneja datos históricos sin inventar autores/cantidades. No imponer restricciones que rompan compensaciones válidas del ledger.

### A13 — P2: declaraciones de alérgenos sin autor ni fecha

**Evidencia:** `AllergenDeclaration`, `models.py:251–262`, guarda alimento/nombre/estado, pero no `created_by`/`created_at`; POST en `operations.py:446–474` y lectura por último PK en `services/allergens.py:14–23`.

**Corrección:** autor/fecha y política explícita de sustitución/normalización; registrar cambios y conservar el desconocido. Los datos históricos deben marcar procedencia desconocida, no atribuirse a quien ejecuta la migración.

**Aceptación:** se identifica quién y cuándo cambió cada declaración; los snapshots confirmados conservan su estado; cambiar declarado→desconocido no elimina trazabilidad.

### A14 — P2: zona horaria fija y concentración de responsabilidades

**Evidencia:** `operations.py:284,313` fija `Europe/Madrid`. Es correcto para la instalación inicial prevista, pero difiere de una futura configuración nativa distinta. El mismo archivo reúne 950 líneas de movimientos, servicios, producción, alérgenos y catálogos de intercambio; conserva clases heredadas y políticas de edición repartidas.

**Corrección:** usar la zona de configuración efectiva con política explícita de fecha civil; dividir APIs por responsabilidad después de caracterizar comportamiento, compartir campos/errores/permisos y retirar únicamente rutas/clases sin consumidores comprobados.

**Aceptación:** fechas DST y zona no Madrid conservan la fecha de servicio; sin cambios de rutas o ACL inadvertidos; cada módulo tiene contratos y pruebas propios. Refactor gradual, no reescritura estética.

### A15 — P1 antes de producción: operación y recuperación todavía locales

**Evidencia:** el ejemplo productivo de `PRODUCCION_ES.md:58–120` carece de política de reinicio y rotación de logs; monitorización/retención externa no están configuradas. Las líneas 134–140 explican que los scripts de recuperación son locales y rechazan producción. La carpeta de backups está vacía por limpieza autorizada anterior.

**Corrección:** preparar perfil productivo validable con reinicio, logs acotados, alertas y límites medidos; procedimiento separado de backup consistente/cifrado, retención, restauración y activación. Mantener las guardas del tooling demo. Crear una nueva copia verificable antes de depender de rollback local; no asumir que los bundles citados aún existen.

**Aceptación:** reinicio de host/daemon recupera servicios; fallo dispara alerta; copia nueva se restaura en DB/media nuevas con RPO/RTO medidos; TLS/cookies/proxy/media/recuperación de acceso probados. VPS, dominio y datos reales siguen requiriendo su autorización y destino concretos, sin bloquear las pruebas locales independientes.

### A16 — P2 antes de producción: privilegios y reproducibilidad de dependencias

**Evidencia:** Dockerfile propio sin `USER`; entrypoint no baja explícitamente privilegios de Gunicorn. El Compose propuesto no fija usuario ni `no-new-privileges`/capabilities. Las constraints Python fijan versiones, no hashes de archivos, y `apk add` sigue resolviendo paquetes.

**Corrección:** ensayar usuario no privilegiado y puerto interno compatible, directorios escribibles explícitos, capacidades mínimas y filesystem restringido donde sea viable. Conservar pines base y avanzar hacia hashes/procedencia de artefactos Python/OS. Medir, no prometer rootless por editar una línea.

**Aceptación:** inspección y smoke acreditan usuario efectivo, rutas de escritura permitidas, media/static/migraciones operativas y dependencias verificadas. No se ha demostrado un escape de contenedor; es hardening pendiente.

### A17 — P2: los tests del kit dejan de funcionar después del bootstrap

**Reproducido ahora:** 42 tests, 41 correctos y 1 error. `tests/test_kit.py:243–245` hace `ROOT.rglob('*.json')`: alcanza app, referencias, dependencias y artefactos. El primer fallo se encuentra en un JSONC de devcontainer de Mealie. La búsqueda diagnóstica encontró 1.778 archivos y 80 rechazos del parser JSON estricto; no son 80 archivos corruptos.

**Corrección:** delimitar archivos propios del kit mediante allowlist de manifest/overlay/fixtures; validar JSONC con su formato cuando corresponda, fuera de este check. No editar configuraciones de donantes para que un test mal acotado pase.

**Aceptación:** suite verde tanto en kit recién extraído como en workspace poblado; un JSON propio inválido sigue fallando y el mensaje incluye su ruta. Mantener protección contra colisiones del bootstrap.

### A18 — P2: tests frontend mezclan dependencias unitarias y runtime

**Reproducido ahora:** `node --test src/cuaderno/*.test.mjs` ejecuta 126 tests: 125 PASS y 1 fallo en `markdownSecurity.test.mjs:113`, cuyo helper intenta Docker y no encuentra el engine Linux. Esto no demuestra un fallo de seguridad Markdown; demuestra que el comando no es una suite puramente local.

**Corrección:** separar comandos unitarios/SFC e integración Markdown con backend real; declarar requisitos y preflight. Añadir scripts npm/yarn verificables de test/typecheck para que el desarrollador no dependa de conocer nombres del registry.

**Aceptación:** tests unitarios se ejecutan sin Docker; integración falla claramente como requisito ausente cuando falta runtime y permanece obligatoria en CI completa. No convertir el fallo en un skip silencioso del gate.

### A19 — P2: tooling de recuperación y discovery necesitan consistencia

**Evidencia:** `delivery_backup.py:156–162` conserva cada BD de prueba creada; `delivery_restore.py:15–25,47` acepta una ruta resuelta de bundle y escribe resultado allí, con menos confinamiento que rollback. `test_delivery.py` usa un import que falla al invocarlo como `python -m unittest scripts.cuaderno.test_delivery`, aunque las 10 pruebas pasan desde su layout admitido.

**Corrección:** inventariar destinos y añadir política explícita de retención/limpieza de recursos propios con dry-run y guardas; homogeneizar confianza y confinamiento de bundles/resultados, sin borrar copias ajenas. Hacer los imports de tests compatibles con discovery y ejecución registrada.

**Aceptación:** éxito y fallo dejan recursos conforme a la política; symlinks/rutas no autorizadas se rechazan si la política los prohíbe; ambas invocaciones de tests pasan. La posibilidad de usar un bundle externo puede ser una opción explícita, no necesariamente algo que eliminar.

### A20 — P2: estado, documentación y kit necesitan una jerarquía clara

**Evidencia:** README raíz y plan aún dicen que no hay producto/clones; ZIP solo contiene kit. README de app y STATUS describen una aplicación avanzada. `tasks.json` tiene 3 DONE, 11 REVIEW, 19 IN_PROGRESS, 3 BLOCKED y 2 TODO. `check.py --list` muestra VERIFICADO también para comandos cuyo último resultado es rojo: significa que el comando está configurado, no que el producto lo haya pasado.

**Corrección:** entrada clara de producto frente a kit; usar STATUS como estado actual, evidencias como historia y audit como backlog evaluado. Separar en el registry «comando comprobado» de «último resultado». Añadir un resumen legible de fuente/imagen/checks, sin concatenar IDs y palabras. Actualizar routing/prompts históricos cuando contradigan la configuración efectiva; no atribuir un modelo efectivo por un TOML.

**Aceptación:** un nuevo colaborador sabe dónde trabajar, qué arrancar, qué está parado y qué pruebas faltan; ningún README sugiere rebootstrap sobre `app/`; cada DONE tiene evidencia y revisión vigente. No cerrar tareas solo para subir un porcentaje.

### A21 — P1: una recepción tardía puede borrar el borrador de otro pedido

**Evidencia:** `vue3/src/cuaderno/components/PurchasingPanel.vue:108–139,386–403`. Durante un POST, abrir/cerrar otra recepción sigue disponible; esas acciones reutilizan el mismo objeto `receipt`. Al volver la respuesta del pedido A, `receive` limpia incondicionalmente `receipt.quantity` y actualiza el mensaje compartido, aunque el usuario ya esté escribiendo el pedido B.

**Corrección:** asociar respuesta a pedido y versión de borrador, o impedir explícitamente el cambio de contexto durante la operación. La clave idempotente del backend evita duplicación de stock, pero no protege el estado del formulario.

**Aceptación:** test de componente con promesas controladas: enviar A, abrir B/escribir, resolver A. B conserva cantidad/destino/mensaje; A queda correctamente actualizado y el retry no duplica la recepción. Repetir error de A, cierre y navegación.

### A22 — P1: marcar/deshacer en lista compartida no protege de cambios ajenos

**Evidencia:** `ListaPage.vue:150–182` lee `updated_at` pero envía solo `{checked}`; no manda revisión ni `If-Match`. La comparación posterior comprueba la respuesta cuando la escritura ya sucedió y normalmente refleja el valor solicitado. Undo tampoco incluye una precondición.

**Impacto:** una sesión con una copia antigua puede sobrescribir una actualización posterior de otra sesión sin que el aviso actual la proteja. El alcance observado es la lista compartida, no un saldo de inventario.

**Corrección:** precondición atómica servidor/cliente, versión o revisión compatible con la ruta nativa; conflicto explícito y actualización de estado antes de un nuevo intento. Definir la semántica de undo cuando otra persona haya intervenido.

**Aceptación:** dos clientes leen la misma revisión; el segundo cambio obsoleto y un undo obsoleto no sobrescriben la revisión nueva y muestran conflicto recuperable. Cubrir UI y PostgreSQL, no solo el helper que forma `{checked}`.

### A23 — P1: typecheck actual incluye tres errores propios de Cuaderno

**Reproducido ahora:** `npx vue-tsc --noEmit -p tsconfig.app.json`, desde `app/vue3`, con Node 25.8.1, vue-tsc 3.3.5 y TypeScript 5.9.3, termina con error y 629 diagnósticos: 626 fuera de Cuaderno y tres dentro. Ubicaciones:

- `allergenUi.ts:89`: acceso a `foods[0].id`, posiblemente undefined para el checker.
- `productionWasteUi.ts:60`: `integer.replace`, elemento de destructuring posiblemente undefined.
- `productionWasteUi.ts:70`: mismo problema en validación de ratio.

**Corrección:** estrechamiento/defaults que mantengan la validación real; no usar supresiones globales ni desactivar comprobaciones. Separar corrección del código propio de la estrategia para los 626 diagnósticos heredados; comparar baseline con el mismo TypeScript/vue-tsc/tsconfig instalados.

**Aceptación:** cero diagnósticos en código nuevo/modificado, baseline restante explícito y reproducible; decidir y registrar cómo se cierra el gate global. El resultado histórico «626, cero Cuaderno» no describe esta ejecución y debe actualizarse cuando se rehaga la validación operativa. Sin reproducir aquel entorno no se puede atribuir la diferencia a tres regresiones nuevas de código: aquí se demuestra el fallo actual, no cuándo apareció.

### A24 — P2: las pantallas de precios y lista aún omiten información prevista

**Evidencia:** `ListaPage.vue:31–45,69–72` presenta pendientes/hechos y cantidad/nombre, pero no unidad, agrupación, receta de origen ni estado por línea. `PreciosPage.vue:54–76` usa un listado para todos los anchos y no expone directamente precio por unidad base/fecha efectiva; parte del historial solo aparece al seleccionar formato.

**Corrección:** completar la información útil y adaptar presentación a ancho disponible: tabla de precios en escritorio y tarjetas compactas móvil; lista con unidad, origen, agrupación y feedback de sincronización. Reutilizar componentes Vuetify/nativos. Si se prefiere otro diseño igualmente usable, actualizar y revisar explícitamente el contrato UX.

**Aceptación:** misma información crítica a 390 px y escritorio, sin overflow que esconda acciones; estado incompleto visible; carga/error/retry/undo verificables. No declarar un fallo CSS concreto hasta observar navegador.

### A25 — P2: el rol Consulta ve controles de escritura que acabarán rechazados

**Evidencia:** `PreciosPage.vue:6,34,65–74,87–105` muestra aviso de rol, pero las acciones dependen de busy, no de `can_operate_cuaderno`. `save`/`savePrice` no impiden la solicitud según el rol cargado.

**Corrección:** usar el contrato de rol para deshabilitar u ocultar acciones no disponibles con explicación accesible; conservar lectura/historial y autorización del backend. Mientras el rol no esté cargado o sea inválido, no ofrecer escritura.

**Aceptación:** Consulta no dispara POST desde esos controles; Cocina puede operar; un cambio de rol o 403 de servidor conserva borrador y explica qué ocurrió. No es una elevación de privilegios demostrada: el servidor sigue rechazando.

### A26 — P2: contratos frontend demasiado permisivos en algunos límites API

**Evidencia:** `any`/respuestas manuales en `ListaPage.vue:55–70,121,150`, `PurchasingPanel.vue:260–290`, `AlmacenPage.vue:107–120,189` y varias secciones de `ExchangePanel.vue`. Hay helpers nuevos con validación estricta que pueden servir de patrón, pero no se aplican uniformemente.

**Corrección:** tipos generados/validados en el límite, identificadores/decimales/envelopes comprobados y tokens de carga por selección. Evitar reemplazar estado útil por un 2xx con forma inesperada.

**Aceptación:** respuestas malformadas, IDs incongruentes, selecciones rápidas y respuestas invertidas preservan el estado válido y muestran error; tests de componentes reales para compras/lista, además de helpers.

### A27 — P3: mejoras de reservas, localización y moneda

**Reservas:** la UI de `ProduccionPage.vue:44–47,432–440` ofrece total de comensales; backend y `forms.ts:26–31` admiten base + altas − cancelaciones. Exponer ese desglose haría más claro el trabajo diario. El alcance mínimo pide reservas internas por número, que el total ya cubre; no considerar automáticamente obligatorio un historial detallado sin decisión de producto. Si se adopta, aceptar 20 + 3 − 2 = 21 y decidir si el desglose debe persistir.

**Localización:** las nuevas cadenas y navegación están directamente en español (`apps/tandoor/main.ts:45–48`, `useNavigation.ts:17–20` y SFCs). El español cumple la entrega inicial, pero usar las claves i18n existentes evitaría mezcla de idiomas para otros usuarios y duplicación de textos. No convertir multilingüismo completo en un bloqueo comercial nuevo.

**Moneda:** `forms.ts:44–45` muestra `€` fijo en coste congelado, mientras el panel de receta respeta `cost.currency`. Si se habilita una moneda distinta de EUR, el snapshot debe transportar y representar su ISO; alternativamente, explicitar/restringir EUR de forma coherente. Test con moneda no EUR antes de prometer ese soporte.

## 4. Estado de validación observado

| Comprobación | Resultado | Alcance |
|---|---|---|
| Git/source locks/referencias | Limpios al inicio; manifests coinciden | Fuente local; no certificación del runtime. |
| Tests kit | 41 PASS, 1 ERROR de 42 | Fallo de alcance del parser JSON, A17. |
| Dominio puro Cuaderno | 27/27 PASS | Python host 3.14.2; no PostgreSQL ni Python productivo 3.13. |
| Ejemplo precisión consolidación | Pérdida reproducida | A03, función pura usada por ficha manual. |
| Frontend Node | 125 PASS, 1 FAIL de 126 | Fallo ambiental Docker Markdown, A18; Node host 25.8.1, no Node de build. |
| Tooling Python operativo | 53/53 PASS con layouts admitidos | Unitarias con límites simulados; discovery alternativo presenta A19. |
| Inventario/procedencia frontend | 11/11 PASS | Pruebas de tooling, no wiring/build final. |
| DAG tareas y listado registry | Exit 0 | Consistencia estructural; no completa tareas. |
| Chequeo migraciones Django host | No ejecutable: Django no instalado | No se instalaron requirements sobre Python del sistema. |
| Typecheck | Nuevo RED, 629 diagnósticos: 3 Cuaderno y 626 restantes | Difiere del resumen histórico; ver A23 y versiones de E05. Baseline histórico 650 no vuelto a ejecutar. |
| Integración PostgreSQL | Histórico 341/341, con ampliaciones posteriores focales | No suite final con identidad uniforme. |
| Build/HTTP/restore/rollback a3c | PASS históricos documentados | No disponibilidad actual; bundles retirados y preview parado. |
| Performance | Histórico RED5 | A06. |
| Scan OS/imagen | Sin scan válido | A07. |
| Navegador/iPad/VPS | Sin aceptación nueva | Límites expresos; no se iniciaron servicios. |

No sumar estas cifras como una tasa única de cobertura: mezclan capas, entornos y fuentes. Tampoco hay una medida nueva de cobertura de ramas que permita afirmar los objetivos 95% del dominio crítico/85% del código nuevo.

## 5. Plan de ejecución ordenado

El tamaño indicado es relativo —S acotado, M varios módulos, L una tanda de integración—, no una estimación contractual de horas. Ejecutar primero Esencial aceptable y ampliar luego los flujos profesionales; conservar las funciones nativas útiles en todas las ediciones.

| Paso | Resultado concreto | Hallazgos/tareas | Dependencias | Tamaño |
|---|---|---|---|---|
| 1 | Arranque/readiness, ficha manual y correcciones frontend críticas | A01–A03/A21–A23; T006/T022/T026/T034 | Pruebas rojas focales, PostgreSQL aislado para aceptación API/migración | M |
| 2 | CI propia y matriz completa de tests | A04/A05/A18; T005/T031/T038 | Toolchains y servicios de test aislados | L |
| 3, independiente | Tooling local con comandos claros y kit validable tras bootstrap | A17–A20; T001/T036 | No bloquea pasos 1–2; ninguna operación sobre runtime | S–M |
| 4 | Cierre de Esencial en navegador | A10/A24–A26; T007–T017 | Build/backend preparados, browser operativo | L |
| 5 | Cierre de Profesional e Integral | A10–A14/A21/A22/A24–A27; T018–T030 | Esencial sin regresiones; workflows persistentes | L |
| 6 | Rendimiento y hardening funcional | A06/A12; T031/T032/T033 | Dataset estable, perfiles reproducibles | L |
| 7 | Procedencia y scanner Linux reales | A07/A08; T034/T036 | Pipeline final; archivo/imagen e identidades congeladas | M–L |
| 8 | Candidato único: upgrade, suites, backup/restore/rollback | A05/A09/A15; T034/T035 | Código/pipeline estables, nueva copia disponible | L |
| 9 | Revisión independiente y paquete local | T037/T038 | Todos los gates obligatorios con evidencia válida | M |
| 10 | Preparación y ensayo productivo autorizado | A15/A16 | Destino/dominio/secrets/autorización; decisión posterior | L |

No acoplar pasos independientes al extractor del programa antiguo. No reactivar el preview o reconstruir imágenes solo para leer este informe. Al volver a ejecutar la aplicación, seguir el manual vigente y preservar la separación entre demo, pruebas y producción.

### Cierre de las 38 tareas

La tabla resume qué debe demostrarse para cerrar cada fila del registry; no reemplaza sus dependencias ni su criterio de aceptación detallado.

| Tarea | Estado registrado | Evidencia/acción que falta |
|---|---|---|
| T001 | DONE | Mantener pins/historia y routing efectivo coherente. |
| T002 | REVIEW | Revisar baseline y separar imagen pin del producto actual. |
| T003 | DONE | Mantener mapa nativo ante cada patch nuevo. |
| T004 | DONE | Conservar ledger y pins; no ejecutar donantes por rutina. |
| T005 | BLOCKED | Baseline íntegro y capturas; automatizar en CI propia. |
| T006 | IN_PROGRESS | Contratos/API y decisiones restantes con pruebas; A01–A03/A11. |
| T007 | REVIEW | Space español/Esencial y navegación aceptados en navegador. |
| T008 | REVIEW | Unidades/precios y casos de precisión con revisión final. |
| T009 | REVIEW | Persistencia/versiones/precio gratuito y ausencia de stock obligatorio. |
| T010 | REVIEW | Costes/recalculo/privacidad y presupuesto P95 cumplidos. |
| T011 | IN_PROGRESS | Pantalla precios completa y usable en móvil/tablet/escritorio. |
| T012 | IN_PROGRESS | Panel coste nativo, raciones, errores e impresión verificados. |
| T013 | IN_PROGRESS | E2E Esencial de principio a fin sobre candidato identificable. |
| T014 | IN_PROGRESS | Roundtrip portable, fotos, preview, conflictos y errores en UI. |
| T015 | BLOCKED | Impresión real y accesibilidad en viewports definidos. |
| T016 | REVIEW | Revisar restore existente y producir copia actual utilizable. |
| T017 | IN_PROGRESS | Revisión de Esencial y preview evaluable al reanudarlo. |
| T018 | REVIEW | Subrecetas/rendimientos/ciclos y consistencia visual final. |
| T019 | IN_PROGRESS | Mermas/presupuesto/precio orientativo sin doble cálculo. |
| T020 | REVIEW | Menús/servicios/reservas y fechas con aceptación final. |
| T021 | IN_PROGRESS | Lista compartida, dos sesiones, marcar/deshacer y fallo de red. |
| T022 | IN_PROGRESS | Ficha/manual/preparación/alérgenos; A02/A03/A13. |
| T023 | IN_PROGRESS | E2E Profesional, impresión y regresión Esencial. |
| T024 | REVIEW | Revisar ledger único y matriz de escritores/concurrencia. |
| T025 | REVIEW | Proveedor/ofertas/pedido y edición/conflictos en UI. |
| T026 | REVIEW | Recepción parcial/retry/reversión en API y navegador. |
| T027 | IN_PROGRESS | Producción/desperdicio/auditoría completos sin doble saldo. |
| T028 | IN_PROGRESS | Reposición/impacto y listas grandes aceptadas. |
| T029 | IN_PROGRESS | UI Integral con roles, ayudas y estados/error probados. |
| T030 | IN_PROGRESS | E2E Integral y regresión cruzada de ediciones. |
| T031 | IN_PROGRESS | Matriz security real agregada y final con fuente exacta. |
| T032 | IN_PROGRESS | Resolver RED5 y medir UI/bundle/almacenamiento. |
| T033 | BLOCKED | Diseño final, navegadores y accesibilidad; iPad aparte. |
| T034 | IN_PROGRESS | Imagen/procedencia/scan/upgrade final, A01/A07–A09. |
| T035 | IN_PROGRESS | Nueva copia, restore y rollback del candidato final. |
| T036 | IN_PROGRESS | Manuales actuales, SBOM/procedencia y entrada kit/producto clara. |
| T037 | TODO | Revisión independiente final de código, pruebas y artefacto. |
| T038 | TODO | Rerun limpio y paquete de entrega reproducible. |

## 6. Límites y decisiones pendientes reales

1. **Programa antiguo:** falta nombre/versión/export autorizado. Solo bloquea el extractor específico y el ensayo de migración real. Preparar fixtures sintéticas y mapping genérico mientras tanto.
2. **iPad físico:** falta comprobación en dispositivo real. Registrar modelo, iPadOS, navegador, teclado, impresión y uso táctil cuando esté disponible.
3. **Producción:** falta un ensayo autorizado de VPS/TLS/proxy, copias externas, alertas, recuperación y políticas operativas. La guía actual es preparatoria.
4. **Navegador de pruebas:** el B04 histórico requiere revalidar disponibilidad al retomar E2E; no se declara que la indisponibilidad del 30 de septiembre sea permanente.
5. **Decisiones de explotación:** retención, RPO/RTO, volumen esperado y soporte de cada edición deben basarse en mediciones. Los precios comerciales no prueban capacidad ni coste operativo.

No se añaden al alcance TPV, contabilidad fiscal, ecommerce, OCR universal, IA obligatoria ni escrituras offline. No se retiran exportación, seguridad o recuperación de ninguna edición para justificar precios.

## 7. Condición de salida

La entrega local puede aprobarse cuando A01–A10 y A21–A23 estén resueltos y los gates/tareas reflejen exactamente su evidencia. Cualquier excepción a un criterio de aceptación debe identificar el hallazgo, responsable, motivo y alcance de la decisión revisada; documentar un fallo no equivale a resolverlo. El candidato debe tener una fuente/imagen inequívocas, tests finales, E2E y rendimiento aceptados, scan/procedencia válidos y recuperación repetible.

La aprobación local no equivale a desplegar en producción. Antes de datos reales también deben cerrarse operación, secretos/TLS, backups externos y ensayo de recuperación productiva. Conservar [STATUS](STATUS.md), [RELEASE_CHECKLIST](RELEASE_CHECKLIST.md) y [RESUME](RESUME.md) como controles operativos, enlazando este documento para el detalle del trabajo pendiente.
