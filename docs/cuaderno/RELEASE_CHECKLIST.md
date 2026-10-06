# Aceptación final

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
