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


El cierre actual usa `scripts/cuaderno/candidate_check.py`, `release_manifest_collect.py` y `release_gate.py`. El resultado actual y los hashes de sus 17 pruebas se conservan en `.cuaderno-runs/release-manifest.json`; la explicación legible está en `.cuaderno-runs/RELEASE_REPORT.md`. Esta evidencia generada queda fuera de Git para no invalidar las fuentes congeladas ni publicar trazas/sesiones sintéticas. Las casillas históricas siguientes conservan su fecha: no son el dictamen del nuevo candidato.

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
