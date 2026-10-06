# Estado del producto

## Despliegue autorizado bajo prefijo — 6 de octubre de 2026

El propietario autoriza corregir, publicar en su fork y desplegar en `https://gex-dashboard.hopto.org/cuaderno-cocina/`. Se verificaron paquete, HEAD limpio inicial y los 2.350 archivos: `f2e3f3ca6da66848fd1234c6189a342184316d52+worktree.d793040fafe38d541b0a69356ce7ba2b91ba8fcbb6f7b3b8e88205fe98604725`. La autorización actual sustituye las restricciones históricas de publicación de este documento.

Correcciones implementadas: URLs y uploads derivados del base Django, cookies configuradas y limitadas al prefijo, media compartida de mismo origen, share target del manifiesto, healthcheck con excepción HTTPS exacta, worker/caches/cola/storage propios, Compose de bajo consumo y recuperación con configuración reproducida e identidad de imagen estricta. Revisión independiente de código recibida; el CI y las pruebas reales del nuevo candidato todavía deben terminar. Los resultados del CI base no se transfieren a esta revisión.

Pruebas focalizadas: 25 frontend/PWA PASS, 4 Django proxy PASS tras regresión roja, 21 backup/restore unitarias PASS y 3 autenticación E2E PASS. Se usan dependencias existentes, sin instalar Node ni navegadores en el VPS. La matriz CI añade HTTPS con prefijo y perfil productivo, conservando ediciones/roles/anchuras y Firefox/WebKit; G7 recoge 17 evidencias reales del mismo candidato y falla si falta alguna.

Inspección inicial: RAM disponible 2,3 GiB; swap usada 2,2/4 GiB; disco libre 23 GiB; ningún OOM en el journal consultado. 18081–18083 y los directorios productivos propuestos estaban libres. Correo en 8080 intacto; no se reinicia ningún servicio ajeno. El temporizador de reboot existente permanece habilitado. **Todavía no hay despliegue de Cuaderno ni modificación/recarga de Caddy.**

El propietario indica backups en una subcarpeta del proyecto. Será una copia local privada; no existe destino externo confirmado y no se acredita offsite. Procedimiento y límites en [runbook VPS](VPS_RUNBOOK_ES.md). Las pruebas reales de recuperación/rollback del nuevo candidato siguen pendientes hasta disponer de su imagen.

Primer candidato publicado: `00c3d87`, [CI 37463061834](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37463061834). Tooling, frontend, ambas suites PostgreSQL, build/identidad/SBOM/procedencia, Markdown runtime y Playwright raíz (193 pruebas, retries=0) PASS. El preview de prefijo falló: Gunicorn interpreta la variable reservada `SCRIPT_NAME` antes del adaptador WSGI y rechaza las rutas ya recortadas por el proxy. G7 no se ejecutó por esa dependencia fallida; este candidato no está aprobado para despliegue. Se corrige la separación entre prefijo lógico de Django y entorno de transporte de Gunicorn, con regresión HTTP real. Toda corrección exige otra imagen y nuevas evidencias; no se trasladan los PASS al candidato siguiente.

Segundo candidato: `11e8e116`, [CI 37468038137](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37468038137). La regresión Gunicorn real, los siete jobs iniciales y raíz 193/193 PASS. El preview HTTPS prefijado arranca correctamente; su matriz termina con 66 PASS y 243 FAIL de 309, retries=0. El diagnóstico confirma que ignorar errores HTTPS por contexto no permite a Chromium registrar el worker del certificado autofirmado. Se prepara confianza específica del certificado generado solo en el runner desechable, manteniendo la validación HTTPS y el collector. Un probe breve con Chromium ya instalado reprodujo rechazo con pin incorrecto y registro correcto con el SPKI exacto, sin cambiar el almacén de confianza del VPS.

Las comprobaciones anónimas también descubrieron que `browser.newContext` hereda la autenticación del proyecto Playwright: las sesiones omitidas explicaban los 200 en lugar de 404. Se añaden estado vacío y precondiciones de anonimato, espera de recarga de idioma y actualización real del worker con comprobación de cache ajeno. G7 del segundo candidato sí arrancó, pero falló al descargar la base fijada del scanner (HTTP 403 del cliente urllib); no acredita ninguno de los 17 controles pendientes. El cliente identificado recibe 200 y mantiene los mismos hashes obligatorios. La nueva revisión exige otro candidato y CI completo. **Producción, backup/restauración reales del VPS y recarga de Caddy siguen pendientes.**


## Candidato local de cierre — 4 de octubre

La continuidad actual ejecuta los gates del candidato y la aceptación multiagente real. El resultado verificable se guarda fuera de las fuentes congeladas en `.cuaderno-runs/release-manifest.json` y `.cuaderno-runs/RELEASE_REPORT.md`; una implementación o un informe antiguo no sustituyen ese resultado. El preview local está autorizado en http://127.0.0.1:18081. No hay autorización nueva de despliegue externo.

Correcciones adicionales: build reproducible de APKs Alpine y enlace Node/zlib con hashes runtime; aceptación explícita de findings mediante pruebas de remediación, sin ocultar el scan bruto; cola de compras conserva cambios/undo ante 401/403/500; Consulta conserva acciones de lectura en compras y producción (historial, actualización, impresión y preparación); formularios y handlers restringen las escrituras y la reposición según el rol; GET de Spaces sin perfil no inserta datos; impresión del navegador elimina la navegación y su padding. El benchmark de trabajo más reciente anterior al cierre era RED2, no RED6. Los presupuestos y el dataset permanecen intactos.

Tooling completo con Python 3.13 y pins de CI: **286 PASS**. El host Python 3.14 con PyJWT anterior había producido dos errores; ese entorno no es el runtime certificado. El gate definitivo exige fuente limpia, una imagen inmutable y los 17 registros reales, incluidos regresión nativa, integración, recuperación, escaneo y navegador. Los resultados finales deben consultarse en el informe generado, que no modifica las fuentes mientras se miden.

## Implementación del 4 de octubre en curso

El propietario autorizó resolver la auditoría y completar la aceptación con varios agentes y Playwright. Se ha reanudado el entorno local aislado. Cambios y resultados actuales en [evidencia de implementación](evidence/2026-10-04-implementacion.md). El candidato final aún debe completar los gates. Los resultados del 30 de septiembre que siguen son históricos y no representan la nueva imagen.

Comprobaciones vigentes de trabajo: 1279 tests nativos PASS; 149 tests frontend PASS con cierre autónomo; TypeScript global sin diagnósticos, incluido Node 24.21.0 fijado por digest; 241 tests de tooling PASS en Python 3.13; OpenAPI sin errores/avisos y SDK reproducido. Tras dos tests SQL rojos, las optimizaciones de JSON y movimientos pasan 49 regresiones de payload/permisos. Estos resultados proceden de entornos de trabajo distintos: todavía no acreditan los 17 checks de una imagen final única. El último benchmark de trabajo fue RED6 y queda visible en la evidencia; el nuevo runtime y la aceptación multiagente están en curso.

## Auditoría documental previa a la implementación (histórico)

Nueva [auditoría integral](AUDITORIA_2026-10-04.md) con 27 hallazgos, criterios de aceptación y mapa de las 38 tareas; [comprobaciones de esta sesión](evidence/2026-10-04-auditoria.md). No se reanudó la aplicación ni se implementaron las correcciones. Los gates mantienen su estado. El typecheck local actual arroja 629 diagnósticos, tres en Cuaderno, con vue-tsc 3.3.5/TypeScript 5.9.3; no confundirlo con el resultado histórico de 626/cero Cuaderno citado debajo. Los resultados runtime que siguen conservan su fecha y alcance originales.

## Parada solicitada el 1 de octubre, 08:42 UTC

El propietario autorizó borrar toda la caché del builder compartido y detener Cuaderno. El integrador detuvo los 12 contenedores activos (2 web y 10 PostgreSQL), todos con salida 0 y política `restart=no`. Verificó cero contenedores Cuaderno activos, cero listeners en 18080/18081 y cero procesos o servicios Windows atribuibles a la app. Conservó Docker Desktop y los 8 contenedores activos de otros proyectos, sin detenerlos.

`docker buildx prune --builder desktop-linux --all --force` terminó con exit 0: Docker informó `Total: 35.36GB`; `docker buildx du --builder desktop-linux` confirmó `Total: 0B`. Esa cifra es la salida de Docker, no una medición de reducción del archivo de disco virtual de Windows. La caché se regenerará en próximos builds. No se eliminaron imágenes, contenedores, volúmenes, recetas ni destinos restaurados; la imagen a3c sigue disponible. El preview permanece detenido hasta que el propietario lo reanude siguiendo el manual. G7 continúa abierto.

## Limpieza solicitada el 1 de octubre de 2026

El propietario pidió retirar copias y caché. El integrador envió las 13 carpetas de `data/cuaderno/backups` a la Papelera (9 465 302 bytes, recuperables) y eliminó caché Docker identificada por IDs propios de Cuaderno: Docker informó 14,39 MB liberados. Conservó imágenes, contenedores, volúmenes, bases activas, destinos restaurados y caché sin atribución segura. Readiness del preview devolvió `ready=true` tras la limpieza. Las rutas de bundles citadas abajo son evidencia histórica: para repetir rollback hay que recuperar el bundle de la Papelera o generar y validar uno nuevo; no ejecutar los comandos fijados suponiendo que esos archivos aún existen.

Cierre de tanda local del 30 de septiembre de 2026. Rama `cuaderno/main`; **G7 sigue abierto**. El propietario autorizó ahora push a GitHub: primer push confirmado hasta `cfffdd338`, sin force ni PR. La documentación y el tooling posteriores se integran por separado. Solo hijos GPT‑6.1 Sol; no se atribuye un modelo efectivo a raíz. No VPS, datos reales ni migración del cliente.

## Usar la aplicación

Reanuda primero el preview detenido siguiendo el [manual español](MANUAL_ES.md); después abre http://127.0.0.1:18081. [Arranque y preparación de producción](PRODUCCION_ES.md), [checklist](RELEASE_CHECKLIST.md). Cuentas SOLO DEMO: `demo-esencial`, `demo-profesional`, `demo-integral`; contraseña `Demo-Cocina-2026!`. Cada Space es independiente.

Es Tandoor real: Django/DRF, Vue/Vuetify y PostgreSQL. Los donantes no participan en runtime. Esencial500€+17€/mes, Profesional1000€+20€/mes e Integral1500€+30€/mes son metadata comercial, no una pasarela; no se retiran funciones nativas útiles.

## Artefacto comprobado

- Imagen conservada: `sha256:a3c426362270c835ed795741ff92c205c62cf40d53ac6c6905dc69d728a8598c`, healthy en el ensayo previo; contenedor ahora detenido por petición del propietario.
- Fuente efectiva: `f191c6b29c5afb2e1b251b8ae446d4fa19205b64+worktree.e8999bc1868565229f2129adfa77543cdaa4b4b6262396bc04652f551d4a53fb`.
- `205924Z-local-up-4298bc82` PASS1321.767s. Checkout congelado hasta terminar. Pythonstage636s reconstruido con153constraints, pipcheck y exact-set. Frontend CACHE del builded4: no nueva compilaciónVue.
- Ya incluye guardFoodf8186, predicadoPackagecb474 y perfilDB_OPTIONSjitoffb1b7, además de las correcciones previas de privacidad, conversiones, densidad, precisión, alérgenos, merma teórica, roles y reversión.
- Runtime `211202Z-runtime-python-lock-fd5073e9` PASS153/conjunto `2009d15b8f39b8051a5afe772e90487f898f91a38fdb6de15f23e163799e01bb`; `211213Z-runtime-pip-check-0a14d216` PASS; `211224Z-runtime-db-profile-a0382f10` muestra jit=off y libpq_options=-c jit=off.
- Git, fuentesVue, node_modules y tests cookbook/cuaderno ausentes, reobservado. Node24.19.0 sí existe en la dependencia Python nativa nodejs-wheel-binaries; no afirmar ausencia absoluta.
- Scanner7106/cfff y toolingJSa447 son cambios posteriores de checkout. El collector JS **no está conectado a Vite/Docker ni empacado**. No confundir su commit con la fuente f191 del preview.

## Resultados de esta imagen

| Comprobación | Resultado real |
|---|---|
| PyJWT | `211029Z-pyjwt-security-5f56a50f` PASS4/4, PyJWT2.15.0. |
| Audit Python | `211047Z-runtime-audit-5f274d52` exit1:153Python/63Alpine/unresolved0. Único aviso OAuthlib3.3.1 GHSA-xpv3-w29h-x7cv por versión; backport exacto53f308e8 reobservado. No se oculta ni equivale a scanOS. |
| SBOM | Python153 PASS211058Z/canónicoac5f19c7; frontend453 PASS211115Z/canónico359a23f4. Árbol instalado, no cierreJS. |
| HTTP tres ediciones | Genérico212029Z, precios212155Z, lecturas212324Z, preparación212448Z, reversión212611Z y waste212733Z PASS. Sin DOM; logins serializados. |
| Alcance de escrituras | Genérico guarda dos finanzas y reutiliza dos servicios confirmados; preparación marca/desmarca cuatro veces y conserva auditoría. Reversión revalida servicioscancelled5/6/movimientos6/7 existentes, writes0; waste revalida4/5, no nueva producción o desperdicio. Saldo Integral5L. |
| Backup/restore | `213552Z-restore-2172450d` PASS:114tablas/949filas/110secuencias/3media, BD/media nuevas;117.785s/pausa13.792s. Bundle `data/cuaderno/backups/20260930T212850Z-32d8a6a3`. |
| Rollback aislado | `214236Z-rollback-current-6c30d463` PASS107.430s, DB `cuaderno_restore_rollback_db56b593d8b7`, imagen/fingerprint idénticos. Ensayo directo previo PASS115.782s también retenido; nunca activación del preview ni downgrade vivo. |
| Documentación productiva | Ejemplo Compose validado con `214015Z-production-doc-config-43a4ed15` PASS solo sintaxis/config. No VPS/TLS/settings override ejecutados. |

Fingerprint funcional del backup y rollback: `07c232c3544bf4d91b86fef9ab182feebbcb332867d6e58d7518112ed6eb1315`. Dump `dcf40880166589e9948fe7b15aa3bf423d8e4c64bec98815ed8b6a517ef57b7a`. El manifiesto distingue ImageIDa3c de source_commit del checkouta447: este último **no sustituye TANDOOR_REFf191**.

## Gates todavía abiertos

Rendimiento último `203010Z-performance-profile-35cb6393` **RED5**, dataset/umbrales/muestras intactos: coste303.960ms/15SQL falla300; servicios226.423seq y movimientos213.380seq cumplen500, concurrentes1026.090/1398.686 fallan; formatos530.232seq/2158.155conc fallan500. EXPLAIN formatos bajó712.464→53.789ms, no P95global. Regresión Food/Package/JIT89PGPASS202249Z/reviewfresh, sin cambiar ACL.

Native API674PASS180222Z/other571PASS174727Z corresponden a backend2e/PyJWT2.14; views34PASS181023Z/OAuth50PASS180814Z a2.15. No1279 bajo153dependencias idénticas ni integración ampliada final. Integración341PASS115316Z histórica. Typecheck efectivo626RED frente baseline650, ceroCuaderno; no PASS vacuo. UI SFC virtual noDOM.

Scanner unit11PASS211252Z/reviewfresh y fixes7106/cfff. Scans reales210844Z (DBshape, corregido) y211543Z fallaron: GrypeWindows no puede crear nombres de caché de layers con `sha256:`. Reporte vacío no es scan válido. Archivo retenido; binario Linux0.119 descargado y checksum verificado, escaneoLinux aún pendiente. ToolingJSa44711unitPASS212643Z/reviewfresh, sin wiring/build ni cierre exacto.

Upgrade desde pin al a3c pendiente; upgrade591070137Z histórico no lo acredita. B04 Browser autorizado no disponible: faltan capturas, responsividad, impresión y E2E. B01 export antiguo bloquea SOLOextractor; B02 iPad físico/B03VPS externos no ejecutados.

Los scripts operativos son locales y abortan en producción: no retirar guardas para el servidor. La guía productiva es preparatoria, con secretos externos, media autorizada, cookies Secure y validación de proxy/dominio pendientes de ensayo real. [RESUME](RESUME.md) contiene lo pendiente; [evidencia cronológica](evidence/2026-09-30-continuacion.md) conserva todos los RED y resultados históricos. REVIEW no significa DONE.
