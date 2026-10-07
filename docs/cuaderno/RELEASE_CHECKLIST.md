# Aceptación final

## Candidato con recetas y planificación ampliadas — pendiente

- [x] Distribución de funciones entre Esencial, Profesional e Integral,
  preservando recetas, calendarios y listas nativos.
- [x] Implementación y revisión de fuente; diez pruebas puras de planes/entradas
  y once de privacidad/activación del worker pasan. No equivalen a aceptación UI.
- [x] CI 37691631344: migración aditiva y suite PostgreSQL con persistencia,
  permisos y concurrencia; 609 tests Cuaderno y 1.296 nativos + 21 subtests PASS.
- [ ] Contrato OpenAPI sin warnings, snapshot y SDK reproducibles del nuevo commit.
- [x] CI 37691631344: 324 tests frontend, TypeScript, build y un único SVG
  propio realmente emitido en el precache pasan. Revalidar en el candidato final.
- [ ] CI completa, G7 y artefactos de una misma fuente e imagen nueva.
- [ ] Playwright real de funciones nuevas por edición, rol y anchura.
- [ ] Despliegue y aceptación HTTPS completa del nuevo runtime, sin retries añadidos.
- [ ] Backup, restauración y rollback aislados con las migraciones nuevas.
- [ ] Limpieza de datos sintéticos, backup final y comprobación de otras apps.
- [ ] Admisión reciente de capacidad y estabilidad, con los seis procesos
  víctimas OOM históricos conservados. El gestor de usuario ya se observó activo
  con recuperación externa de disparador desconocido; no acredita estabilidad
  durante las pruebas ni borra los controles fallidos anteriores.

Runtime publicado anterior: `ff3b685`, CI 37651982834 con nueve jobs y G7 PASS.
Su aceptación pública más reciente conserva 25 READ PASS, 1 FAIL de worker y
un caso no ejecutado; WRITE no arrancó por el control del host. Los resultados
antiguos no certifican esta ampliación. Backups locales cifrados; sin offsite.

## Referencias históricas; estados en su fecha original

## Aceptación pendiente de la modernización

- [x] 20 bugs y 20 errores distintos revisados por Astra a nivel de fuente y
  pruebas unitarias; 47 FAIL anteriores y 47 PASS sobre la misma suite.
- [x] Calendario corregido sin creación automática de token: 55/55 pruebas
  combinadas. No se añade al mínimo de 40 correcciones primarias.
- [ ] Cierre de las 20 mejoras UX y 20 UI con implementación, compilación y
  pruebas DOM/navegador; los 80 resultados están en el registro enlazado.
- [ ] CI completo y G7 del nuevo commit, nueva imagen y sus nueve artefactos.
- [ ] Publicación del nuevo runtime y aceptación de ediciones/roles bajo prefijo.
- [ ] Backup coherente, restauración aislada y rollback con la imagen anterior.
- [ ] Limpieza exacta de los nuevos datos sintéticos y verificación final de las
  otras aplicaciones, correo y recursos.

La aplicación publicada conserva la versión inicial siguiente. Sus PASS no
certifican la modernización. Ver [registro de 80 resultados](evidence/2026-10-07-modernizacion.md).

## Cierre del despliegue inicial — 7 de octubre de 2026

Runtime `60aca2d0aa7776137f507699be7f111dcf758e18`; imagen local OCI
`sha256:93854211cee63e58ca2bd4b066f06af6a5aba17ae150a8acaf33a0a3d7b1d0ce`.
Los resultados siguientes pertenecen a ese runtime; el commit posterior de
documentación no representa una nueva imagen ni una nueva ejecución de CI.

- [x] CI 37532317372: nueve jobs PASS; raíz 193/193, prefijo 309/309,
  G7 17/17 y backup/restauración/limpieza adicionales PASS.
- [x] Identidad de 2.402 archivos, nueve artefactos y relación entre config
  digest CI y manifiesto OCI Docker 29 local verificadas.
- [x] Producción propia healthy, PostgreSQL privado, web 127.0.0.1:18081;
  migraciones reales, cookies/prefijo, healthcheck y HTTPS comprobados.
- [x] Caddy: bloque propio de 439 bytes; retirada real del primer intento y
  publicación final verificada; tres recargas, PID 916, cero reinicios.
- [x] Backup local coherente, cifrado AES256 e integridad/descifrado comprobados;
  recuperación aislada real, misma imagen/punto de datos, sin puertos ni promoción.
- [x] Timer diario y retención de siete bundles completos verificados; alarma
  local probada manualmente. `OnFailure` no se provocó artificialmente.
- [x] Matriz pública VPS 54/54: READ V4 27, WRITE V5 9, WORKER V5 9 y
  LOGIN/LOGOUT V6 9; tres ediciones/roles, fases completas, cero retries.
- [x] Media físicamente vacía; nueve usuarios/tres Spaces sintéticos eliminados
  y 18 sesiones ausentes. Backup final `20261007T004418Z-7c827cdf7a24`,
  un administrador/un Space/cero recetas, cuatro miembros descifrados y verificados.
- [x] Comparación final: 16 contenedores/46 servicios sin cambios, ocho endpoints
  con el mismo status/error/redirección, ningún OOM nuevo; recursos documentados.
- [ ] Copia cifrada offsite: sin destino configurado. `backups/` está en este VPS.
- [ ] iPad físico; la emulación de 768 px no lo acredita. SMTP real no ensayado.

Las evidencias operativas privadas están en `agent-evidence/` del paquete;
ver [STATUS](STATUS.md) y [runbook](VPS_RUNBOOK_ES.md). Los FAIL previos, incidentes
del host y resultados históricos siguen conservados debajo y no sustituyen
ninguna casilla vigente.

## Historial de aceptación y candidatos anteriores

## Candidato para prefijo — 6 de octubre de 2026

- [x] Paquete y fuente inicial comprobados; autorización de fork/VPS vigente.
- [x] Correcciones de prefijo/cookies/media/manifest/worker/health y recursos implementadas con pruebas focalizadas y revisión independiente.
- [x] Inspección VPS: rutas/namespaces/puertos libres, correo 8080 conservado, reboot existente sin cambios.
- [ ] CI del nuevo commit, imagen inmutable, SBOM/provenance y auditoría Linux.
- [ ] 17 checks G7 del mismo candidato, restauración y rollback reales aislados.
- [ ] Playwright HTTPS con prefijo: tres ediciones, tres roles, tres anchuras y tres motores.
- [ ] Arranque productivo nuevo, migraciones, administrador y smokes por loopback.
- [ ] Backup local privado y restauración productiva aislada; copia externa no configurada.
- [ ] Caddy respaldado/validado/recargado y apps existentes comparadas.
- [ ] Playwright HTTPS real y medición de recursos/OOM/persistencia.

Estas casillas son pendientes reales; el CI base verde no las completa. La imagen recibida es referencia para rollback, no imagen con estas correcciones.

El primer intento nuevo, `00c3d87` / CI `37463061834`, pasó raíz (193 Playwright, retries=0) y los controles iniciales, pero falló en el transporte Gunicorn del prefijo. No está desplegado. La CI corregida obtiene también los diagnósticos independientes G7 si falla el prefijo; el workflow completo debe ser verde, incluida su matriz de prefijo, antes de desplegar.

Segundo intento `11e8e116` / CI `37468038137`: siete jobs PASS, raíz 193/193, preview prefijado saludable, pero prefijo 66 PASS/243 FAIL. Se corrigen confianza TLS del worker de CI, contextos anónimos que heredaban sesiones y sincronización del harness. G7 falla en la descarga HTTP 403 de su DB fijada antes de los controles; no es PASS de seguridad ni recuperación. Las casillas permanecen pendientes para el nuevo candidato. La corrección del cliente conserva URL y hashes del scanner/DB y las aserciones browser conservan collector, timeout y retries.

Tercer intento `5b366375` / CI `37477892105`: raíz 193/193 PASS (448,392 s), pero el preflight del prefijo falla por fuentes nativas que escapan a raíz y certificado servidor `CA:TRUE` rechazado por Firefox; la matriz prefijada no se ejecuta. Se corrigen 18 URLs de fuentes y se separan CA y servidor `CA:FALSE`. G7 terminó FAIL durante la provisión de Grype: la hidratación de SQLite cambia su huella; el pin anterior también supera 120 horas. El diagnóstico externo `37487584544` verifica dos importaciones válidas del archivo oficial nuevo pero termina FAIL por huellas instaladas no deterministas. La nueva verificación requiere un recibo privado unido a los pins oficiales, con SHA entregado por el proceso de provisión, metadata auténtico e inmutabilidad durante el scan. Ningún PASS anterior certifica la imagen siguiente.

Incidente OOM/reboot del host documentado en STATUS. La comparación posterior al reboot conserva 16 contenedores y 46 servicios sin nuevos cambios, pero no acredita continuidad ininterrumpida durante toda la sesión. Los temporales del diagnóstico local ya se retiraron; las importaciones restantes se ejecutan fuera del VPS. Revalidar capacidad antes de cualquier arranque de Cuaderno.


El cierre actual usa `scripts/cuaderno/candidate_check.py`, `release_manifest_collect.py` y `release_gate.py`. El resultado actual y los hashes de sus 17 pruebas se conservan en `.cuaderno-runs/release-manifest.json`; la explicación legible está en `.cuaderno-runs/RELEASE_REPORT.md`. Esta evidencia generada queda fuera de Git para no invalidar las fuentes congeladas ni publicar trazas/sesiones sintéticas. Las casillas históricas siguientes conservan su fecha: no son el dictamen del nuevo candidato.

Cuarto intento `2257385` / CI `37490988588`: los controles iniciales y raíz 193/193 PASS (445,078 s). Preflight prefijado PASS en los tres motores; matriz 291 PASS/18 FAIL de 309, retries=0. Solo fallan las recetas Chromium por denegaciones no gestionadas de Wake Lock. Se corrige el ciclo de esta función opcional en la aplicación con pruebas focalizadas; permisos, collector y aserciones browser permanecen estrictos. G7 terminó FAIL (12/17 PASS): cuatro controles fallan por el archivo de requisitos no legible y la evaluación Linux aún espera once hallazgos en lugar de los ocho del scan nuevo; el ensayo productivo adicional también falla. Este candidato no se despliega; toda corrección requiere otra imagen y CI completo del mismo candidato.

El diagnóstico externo `37500272630`, commit `9731456`, completa backup/restauración del perfil productivo de la imagen 225, sin puertos publicados y con contenedores propios detenidos. No acredita la siguiente imagen ni identifica la causa del RuntimeError anterior. Para el quinto candidato se preparan el permiso público de requisitos, gestión Wake Lock y remediación pareada real de tempfile/shutil; los ocho hallazgos originales permanecen en el scan con cero ignorados y pruebas exactas de backports/producto/componente. Tooling local 427/427 PASS con PyJWT 2.15.0 aislado; son pruebas de trabajo, no G7. Las casillas productivas siguen pendientes.

Quinto intento `14af268` / [CI 37503603756](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37503603756): raíz 193/193 y prefijo 309/309 PASS, retries/skips=0 y worker real en tres motores. Ocho jobs PASS, G7 FAIL (15/17): contratos JSON ausentes en el montaje de integración y lectura errónea de versiones APK. El ensayo adicional productivo de esa misma imagen pasa con manifest/assets/login, contenedores detenidos, cero puertos publicados y limpieza completa. El scan conserva ocho hallazgos y cero ignorados; no existe assessment runtime completo. Esta imagen no se despliega. Se corrigen los dos lectores/montajes con regresiones rojas/verdes y tooling local 434/434 PASS; una sexta imagen debe volver a pasar el CI completo y todos los controles. Las casillas anteriores siguen pendientes para ese nuevo candidato.

El OOM concurrente de las 17:54–17:55 UTC y las recreaciones ajenas quedan documentados en STATUS. El propietario confirma terminada la otra tarea; se toma una referencia posterior conservando las anteriores. A las 18:32 UTC los 16 contenedores y 46 servicios no presentan nuevos cambios; `user@1000.service` sigue failed desde el incidente y no se reinicia. No se afirma continuidad de todos los servicios.

Sexto intento `ff5d1ab` / [CI 37513108397](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37513108397): raíz 193/193 PASS, G7 17/17 PASS y ensayo adicional productivo PASS de la misma imagen, verificados independientemente. El prefijo falla 308/309 por navegación desde StartPage con cuerpos nativos todavía pendientes en WebKit; el collector mantiene la cancelación como error. Ocho jobs PASS y uno FAIL: no se despliega. Para el séptimo candidato se corrige únicamente la sincronización del harness con señal DOM y finalización de cuerpos, manteniendo presupuesto de ocho segundos, collector y retries. 35/35 regresiones ligeras PASS y revisión focal; quedan obligatorios nueva imagen, nueve jobs completos y todos sus registros ligados al mismo candidato.

La recuperación observada de `user@1000.service` a las 18:54 UTC se registra sin intervención propia. Se conservarán las referencias históricas y se capturará una referencia actual antes del arranque propio; los smokes VPS, backup real, restauración y recarga Caddy siguen pendientes.

Séptimo intento `bda944d` / [CI 37521898680](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37521898680): raíz 193/193 y prefijo 309/309 PASS, retries/skips/flaky=0, worker real en tres motores y 17/17 registros G7 PASS revisados independientemente. El job G7 falla en su ensayo productivo adicional: fase restore, operación `docker.exec.pg_restore`, RuntimeError, limpieza PASS. Su stderr no se retuvo y la causa no está demostrada. Ocho jobs PASS y uno FAIL; no se descarga ni despliega la imagen. Para el octavo candidato se corrige la comprobación de PostgreSQL temporal por socket, exigiendo TCP y SQL en la base exacta con los mismos presupuestos, y se añade diagnóstico solo mediante enums permitidos. 38 pruebas focales y 454 pruebas completas de tooling PASS; Compose validado sin servicios. El ensayo externo `37531553112` reproduce socket temporal aceptado antes del servidor TCP, confirma SQL/timeout/socket y limpia sus cuatro recursos propios. No identifica la causa del FAIL anterior; nueva CI completa del octavo candidato obligatoria. Las casillas productivas siguen pendientes.

Medición del VPS a las 21:06 UTC: 16 contenedores y cinco archivos Caddy sin cambios, sin nuevos OOM; cuatro bots ajenos reiniciados automáticamente y activos, sin acciones de Cuaderno sobre ellos. Revalidar capacidad y capturar referencia actual antes de arrancar Cuaderno.

La matriz browser incluye Esencial/Profesional/Integral, Consulta/Cocina/Responsable, 390/768/1440 px y controles adicionales Firefox/WebKit. El informe distingue ejecuciones exploratorias de la imagen anterior y aceptación final. La certificación de iPad físico, datos del programa antiguo y VPS/TLS reales sigue requiriendo sus respectivos entornos.

Estado actual, 4 de octubre: implementación autorizada en curso; [evidencia vigente](evidence/2026-10-04-implementacion.md). Los 17 checks finales deben corresponder al mismo commit limpio, Image ID y contexto. Regresión nativa, frontend, TypeScript, schema y tooling de trabajo pasan; rendimiento y aceptación completa del nuevo artefacto siguen abiertos. G7 no está cerrado.

Estado histórico, 1 de octubre 08:42 UTC: todos los contenedores de Cuaderno se detuvieron por solicitud del propietario. El builder compartido quedó con caché 0 B; imágenes, volúmenes y datos se conservaron. Los resultados healthy/HTTP/restore siguientes son evidencias anteriores. Esta parada no cerró G7.

Nota del 1 de octubre: las copias locales citadas en este checklist se enviaron a la Papelera por petición del propietario. Los PASS conservan su evidencia histórica, pero repetir rollback requiere recuperar el bundle o generar y validar uno nuevo. La aplicación y sus volúmenes se conservaron; readiness siguió verde. La limpieza no cierra ningún gate.

Previewa3c saludable, fuente f191+worktreee8999 exacta en [STATUS](STATUS.md). Build205924Z PASS1321.767s,153versiones verificadas/pipcheck/JIToff/PyJWT2.15. HTTP seis smokes PASS sobre esta imagen; backup/restore213552Z y rollback directo PASS sobre destinos nuevos. G7 sigue abierto. El propietario autorizó pushGitHub al cerrar esta tanda, **no VPS**.

- [x] Base Tandoor/pins/historia/avisos preservados; sin runtime de donantes.
- [x] Build local a3c y comprobación de153versiones instaladas, no bytes/OS congelados.
- [x] HTTP real en las tres ediciones: costes/finanzas/CSRF/lecturas/precios/preparación/replays.
- [x] Backup/restore local del preview:114tablas/949filas/110secuencias/3media, login/permisos/costes/saldos y fingerprint07c232c3.
- [x] Rollback aislado del preview registrado por runner214236Z PASS107.430s, imagen/fingerprint idénticos; no activación/downgrade vivo.
- [ ] Migración desde pin al a3c. Upgrade591070137Z histórico no acredita este artefacto.
- [ ] UI Tandoor y módulos verificados en navegador; impresión/responsive pendientes.
- [ ] Esencial500/17, Profesional1000/20 e Integral1500/30 completos con aceptación visual.
- [ ] Integración ampliada y regresión nativa final bajo idénticas153dependencias.
- [ ] Matriz final privacidad/Spaces/export/media/roles/concurrentes/retries; focal89PGPASS202249Z no sustituye aceptación global.
- [ ] Ninguna respuesta/prototipo/mock sustituye API o persistencia; SFCvirtual no es E2E.
- [ ] SBOM empacado y procedencia frontend efectivamente observada.153Python211058/453frontend211115 PASS son inventarios; toolingJSa44711PASS212643 no está conectado al build, no cierreexactoJS.
- [ ] EscaneoOS/imagen válido y tratamiento de findings. GrypeWindows211543 FAILlayerscolon, no resultados válidos. Linux preparado, no scan aún. OAuthlibversión continúa en audit211047 exit1, backport exacto separado.
- [ ] Rendimiento:203010Z RED5. Coste303.960/15SQL falla300; servicios226.423seq y movimientos213.380seq cumplen500; concurrentes1026.090/1398.686 y formatos530.232seq/2158.155conc fallan500. Dataset/umbrales/outliers intactos.
- [ ] Typecheck efectivo:626RED/baseline650/ceroCuaderno; no PASS previo sin-p.
- [x] Manual español e instrucciones locales comprobadas, guía productiva explícitamente preparatoria. Composeejemplo214015Zconfig--quiet PASS, **no VPS/TLS/settings override probados**.
- [ ] Configuración/backup/restore/monitorización productivos ensayados en destino autorizado, antes de datos reales.
- [ ] Revisión independiente final global aprobada. Revisiones focales no equivalen a G7.
- [x] Externos separados: no iPad físico, migracióncliente, SMTP real ni despliegueVPS ejecutados.

Native API674PASS180222/other571PASS174727 fueron backend2e/PyJWT2.14; views34PASS181023/OAuth50PASS180814 con2.15. No1279 bajo153versiones idénticas. Integración341PASS115316 histórica, ampliación pendiente. UI merma/roles fueron SFCvirtual, sin DOM.

HTTPa3c212029/212155/212324/212448/212611/212733 PASS. Reversión212611 revalida servicioscancelled5/6 y movimientos6/7 existentes, writes0; waste212733 revalida4/5, no creación nueva. Preparación conserva auditoría al restaurar cuatro cambios. Todo sintético local.

B04 Browser autorizado no disponible, sin capturas ni bypass. B01 exportantiguo bloquea solo extractor; importador genérico disponible. Nodefrontend no copiado, pero dependenciaPython nativa incluye Node24.19. No declarar finalización por documentación, inventarios o pruebas de tooling.

[Estado](STATUS.md), [continuidad](RESUME.md), [uso](MANUAL_ES.md), [producción](PRODUCCION_ES.md), [evidencia](evidence/2026-09-30-continuacion.md).
# Candidato del 8 de octubre de 2026

La ampliación `2162075` queda rechazada para despliegue por fallos Playwright:
raíz 578/599 y prefijo 694/715. Las correcciones de esta fuente requieren una
nueva imagen; los checks del runtime publicado `ff3b685` no las certifican.

- [x] Regresiones rojas y veinte pruebas focalizadas verdes de recetas y planificación.
- [x] Revisión independiente del diff para enviar a CI.
- [ ] CI completa del nuevo commit: backend, frontend, navegador raíz/prefijo e imagen.
- [ ] G7 del mismo candidato con sus diecisiete evidencias.
- [ ] Backup coherente previo y restauración aislada; actualización propia de Cuaderno.
- [ ] Aceptación HTTPS por edición y rol, backup posterior y recuperación de esa versión.
