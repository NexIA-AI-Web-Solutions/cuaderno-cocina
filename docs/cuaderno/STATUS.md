# Estado del producto

## Candidato de precisión y recuperación — 8 de octubre de 2026

Producción continúa en `c79b2ce54c20f778524e3dcadfac0bc7e8053aa0` y su
comprobación HTTPS de disponibilidad devuelve 200. Los candidatos `2d09831`
y `638f190` se retienen sin desplegar: el primero reveló un desbordamiento
nativo y la CI del segundo conserva un fallo WebKit de navegación del calendario.
El candidato `54f3ec5` también se retiene: su CI 37828014208 pasó 1.296 pruebas
nativas y 21 subpruebas, 616 de Cuaderno, 463 de tooling más 11 de Node y 370
unitarias frontend. TypeScript detectó ocho incompatibilidades de consumidores;
no se ejecutaron imagen, matrices de navegador ni G7. Esta revisión adapta los
consumidores y evita redondear cantidades al convertir una vista de importación.

Esta revisión conserva cantidades exactas en API, SDK y editor, y corrige la
carga del calendario y su recuperación tras un error de red. La
[decisión de contrato](adr/0012-native-ingredient-decimal-strings.md) describe
la representación decimal. Siete pruebas nativas pasan realmente en PostgreSQL
aislado y OpenAPI se genera sin avisos. La exportación posterior de ese esquema
falló en el harness; su SHA real coincide con los bytes reconstruidos del
snapshot. Ese fallo de transporte se conserva como evidencia fallida.

La nueva CI completa, las nueve cuentas en cuatro anchos, G7, copia cifrada,
restauración aislada y aceptación HTTPS del nuevo runtime siguen pendientes
hasta registrar sus resultados efectivos. Las secciones siguientes conservan
el historial de candidatos anteriores y no certifican este candidato.

## Precios legibles y lectura por rol — 8 de octubre de 2026

La inspección del clon en navegador detectó decimales de almacenamiento visibles
y acciones incómodas en tablet. Las etiquetas conservan todas las cifras
significativas con aritmética exacta y eliminan únicamente ceros de relleno;
los importes muestran al menos dos decimales. Las tarjetas cubren los anchos
anteriores al breakpoint de escritorio de Vuetify. Consulta accede directamente
al listado y al historial, con un aviso de su permiso y sin formulario de creación.
Las cuentas operativas conservan edición, validación y borradores tras errores.

Las regresiones RED→GREEN pasan, junto con 341 pruebas frontend en 58 archivos
y tres pruebas de arranque sin descargas. La nueva imagen, revisión final,
aceptación visual en cuatro viewports, CI completa, G7 y publicación permanecen
pendientes. La CI de `f58b000` fue sustituida antes de terminar sus matrices:
sus resultados parciales no certifican esta fuente. La web publicada sigue
en `ff3b685`; las pruebas de escritura usan exclusivamente un clon restaurado.

## Arranque sin descargas de IA — 8 de octubre de 2026

El arranque del clon de `f58b000` reveló que el import nativo de LiteLLM intenta
descargar un catálogo remoto incluso con IA y conectores desactivados. El perfil
de producción ahora fuerza el catálogo incluido antes de importar los ajustes
base. Tres regresiones de importación en frío pasan tras reproducir el fallo;
la revisión independiente confirma el orden de imports y la ausencia de una
nueva opción para habilitar IA. El nuevo arranque real y su CI siguen pendientes.

La fuente `f58b000` y sus artefactos se conservan congelados. Su CI 37701266074
ha superado ambos backends, tooling, frontend, imagen y Markdown; las matrices
de navegador y G7 continúan pendientes en esta actualización. La web publicada
permanece en `ff3b685`. La copia previa de DB/media/env está cifrada y su
restauración completa se verificó en un namespace aislado con la imagen anterior.
Las pruebas adicionales del clon y la aceptación HTTPS del candidato final
se registran por separado; ninguna de estas comprobaciones publica esta fuente.

## Correcciones de aceptación — 8 de octubre de 2026

El candidato `2162075` no se publicó: CI 37694418221 obtuvo 578/599 pruebas
Playwright en raíz y 694/715 bajo prefijo; ambas matrices conservaron sus fallos.
El runtime HTTPS continúa en `ff3b685`, imagen `sha256:89bf20d9bcfd280d6403c3894f68aab18e14a1e43d5c8798ab8e960f39855020`.

Esta revisión corrige peticiones MealType prohibidas de Consulta, actualización
innecesaria del calendario tras asignar un plato y campos persistentes del diálogo
de plantillas. La lectura de recetas espera la autenticación para registrar una
visita, descarta respuestas de una ruta anterior y maneja fallos de red. Las
pruebas de navegación esperan los cuerpos API reales antes de recargar; mantienen
collector, ocho segundos de presupuesto y cero retries. Se añade el metadato
móvil estándar conservando el de Apple.

Veinte pruebas focalizadas pasan tras regresiones rojas significativas. La
ejecución amplia local anterior conserva sus dos fallos de entorno: dependencia
vue-i18n ausente y contenedor aislado de Markdown inexistente. No se ejecutan
tests destructivos sobre producción. Una CI completa del nuevo commit, G7,
recuperación y aceptación HTTPS son requisitos pendientes para publicar.
La auditoría pública usa Chromium local con cuentas sintéticas, límites propios
de memoria/CPU y ejecución exclusiva; sus resultados se registran por separado.


## Estado actual — ampliación funcional del 7 de octubre de 2026

La URL HTTPS publicada es <https://gex-dashboard.hopto.org/cuaderno-cocina/>.
El runtime actual es `ff3b685fb85a546d6f8e5c4efa305c47c9e94e86`, imagen local
`sha256:89bf20d9bcfd280d6403c3894f68aab18e14a1e43d5c8798ab8e960f39855020`.
Su CI 37651982834 pasó nueve jobs y G7 17/17; esos resultados no certifican
la ampliación funcional de esta fuente, cuya CI y despliegue están pendientes.
La [distribución de funciones](09-FUNCTIONAL-PLANS.md) define Esencial,
Profesional e Integral sin eliminar funciones nativas básicas.

El CI 37691631344 de `d50b75a` comprobó 609 tests de Cuaderno,
1.296 tests nativos y 21 subtests PostgreSQL, y 324 tests frontend. TypeScript,
build y comprobación del worker compilado pasaron: un único SVG propio en
precache, 1,05 KiB. El job backend conserva su FAIL por diferencia del snapshot
OpenAPI; la generación sin warnings y el SDK quedaron en el artefacto oficial
11513179190 para revisión. La fuente incorpora ese contrato generado sin
cambiar el runtime CSRF ni los 25 enums anteriores; una nueva CI debe comprobar
su reproducción y los jobs de imagen, navegador y G7 todavía no ejecutados.

La aceptación pública más reciente del runtime anterior conserva un fallo:
READ obtuvo 25 PASS y 1 FAIL de alcance del service worker; el último caso no
se ejecutó. WRITE posterior no abrió el navegador porque el control del host
detectó dos OOM y `user@1000.service` fallido durante otro despliegue comunicado
por el propietario. No se declara completada la aceptación final de esa versión.
La lectura completa posterior del kernel conserva seis procesos víctimas y 18
mensajes OOM del mismo boot, con último incidente a las 20:32:53 UTC. La causa
no está establecida. A las 21:36 UTC se observó el gestor de usuario activo con
otra invocación; esta tarea no ejecutó su arranque y desconoce el disparador.
Se cerró con SIGTERM la terminal Codex 5128, identificada por el propietario
como terminada; la sesión 325136 se preservó. A las 22:02 UTC se midieron
3.203.664 KiB de RAM disponible y 940.880 KiB de swap libre. La admisión de
operaciones posteriores requiere medidas nuevas y control del historial;
la observación no convierte en PASS los controles fallidos anteriores.
Esta fuente incluye una corrección de vida de activación y precache acotado que
requiere su propia validación en navegador; no se han ampliado los plazos ni retries.

Webmail y J-Automation se comprobaron por autorización expresa: sus páginas
públicas de acceso y los recursos inspeccionados devolvieron HTTP 200. Stalwart
y Caddy siguen activos, sin reinicios realizados por esta tarea. No se inició
sesión ni se probó envío/recepción de correo. No se reinician servicios ajenos.
Los backups cifrados son locales en una subcarpeta del proyecto elegida por el
propietario; no existe copia externa configurada. La restauración y rollback
aislados del runtime `ff3b685` se comprobaron, pero deben repetirse para el nuevo.

## Referencias históricas de versiones anteriores

Los apartados siguientes conservan sus hechos y estados en la fecha original;
no sustituyen el estado actual indicado arriba.

## Modernización en curso — 7 de octubre, posterior al reboot programado

La URL publicada sigue funcionando con el runtime `60aca2d`; las fuentes nuevas
no están desplegadas todavía. Hay 20 correcciones funcionales y 20 de gestión
de errores con revisión de GPT-6 Astra y pruebas rojas/verdes de los scripts
reales. La suite original pasa 47/47; el calendario añade ocho pruebas y el
conjunto pasa 55/55. La compilación, CI y aceptación del nuevo artefacto siguen
pendientes. Las 20 mejoras de UX y 20 de UI se implementan y revisan por separado;
ninguna se declara verificada en navegador aún. Registro de los 80 resultados:
[evidencia de modernización](evidence/2026-10-07-modernizacion.md).

El [CI 37608974757](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37608974757)
del candidato `808724b` terminó rechazado: raíz 290 PASS/77 FAIL y prefijo
406 PASS/77 FAIL, sin retries ni skips; G7 falló. La imagen no se cargó ni
desplegó. Las capturas y trazas reales mostraron peticiones de supermercados
prohibidas para Consulta y dos problemas de Ayuda en escritorio. Se corrigen
la aplicación y las interacciones de teclado del harness, conservando collector,
permisos y plazos. Una nueva CI debe verificar el resultado antes de desplegar.
GPT-6 Astra abrió personalmente la web HTTPS anterior con Playwright y revisó
trece capturas; el recorrido conservó su fallo del calendario. Esa visita y
los informes fallidos no certifican el nuevo runtime.

La referencia de las 09:02 UTC conserva 16 contenedores y 46 servicios ajenos,
sin cambios ni OOM nuevos. El reboot diario existente ocurrió a las 08:30 CEST,
sin acción de esta tarea; Caddy tiene PID 913 y su configuración se conserva.
El timer de backup propio se ejecutó a las 03:21 CEST con éxito, antes del reboot.
Hay nueve cuentas sintéticas en tres espacios propios para la aceptación, con
sus IDs y credenciales protegidos fuera de Git; no se han inyectado sesiones aún.
Las cuentas y datos primarios siguen conservados. Las copias continúan locales
en este VPS; no existe destino externo configurado.

## Referencia del despliegue inicial — 7 de octubre de 2026

Cuaderno responde por HTTPS en `https://gex-dashboard.hopto.org/cuaderno-cocina/`.
El runtime corresponde a `60aca2d0aa7776137f507699be7f111dcf758e18`, fuente
`c8e1848750193af6a7377e521195b4295a10ab3da59c16fa40589fba4444f229` (2.402 archivos).
El [CI 37532317372](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37532317372)
terminó con nueve jobs PASS: Playwright raíz 193/193 y prefijo 309/309,
sin retries, skips ni flaky; G7 17/17 y ensayo productivo adicional de
backup/restauración/limpieza PASS. Chromium, Firefox y WebKit se ejecutaron en CI.
La imagen local Docker 29 es
`sha256:93854211cee63e58ca2bd4b066f06af6a5aba17ae150a8acaf33a0a3d7b1d0ce`;
su configuración CI es
`sha256:aa9fdc7aacfd5d03e3c5cd00071d4daae71f78aa258221023735d713a44f9732`.
La relación entre ambos identificadores y los nueve artefactos se verificó antes del arranque.

El proyecto exclusivo `cuaderno-prod` publica solamente `127.0.0.1:18081`.
Web y PostgreSQL están healthy; se aplicaron 328 migraciones y se comprobaron
114 tablas. Caddy conserva PID 916 y cero reinicios: se realizaron tres recargas,
incluida una retirada efectiva del bloque propio después del primer intento.
El cambio final añade exclusivamente 439 bytes al Caddyfile, con la redirección
308 y el handler del prefijo. Los cuatro imports permanecen idénticos.
Los fallos de comprobación inicial del `<base>` en login nativo y de URLs
relativas del manifiesto se conservaron; se corrigieron las expectativas de las
pruebas, sin alterar la aplicación. La comparación de configuración Caddy
normaliza únicamente los nombres temporales de `file_server.hide`, comprobados
contra el comportamiento real de Caddy 2.11.4.

Aceptación pública VPS: **54/54 PASS**, tres ediciones y tres roles. Fases
completas: READ V4 27/27 a 390/768/1440 px; WRITE V5, WORKER V5 y LOGIN/LOGOUT
V6 9/9 cada una a 1440 px. Se usaron Chromium 151 y Playwright 1.63 existentes,
con casos seriales y límites de 768 MiB/0,5 CPU; sin instalación ni retries.
El cierre verifica hashes de los 54 informes y la misma identidad del runtime.
Los intentos previos conservan sus FAIL: título móvil oculto a 1440 px,
activación de worker no observada en un caso y cierre prematuro de las auditorías
de cabeceras. El harness privado ahora selecciona el título visible, espera el
`load` nativo inicial y drena auditorías dentro del mismo plazo de 55 segundos.
El collector sigue estricto. El diagnóstico pasivo del worker pasó, pero no
demuestra la causa del fallo previo. No hubo modificaciones adicionales del runtime.

READ V4 completó 27/27 PASS. WRITE V4 se detuvo con 1 PASS y 1 FAIL por exigir
404 para una receta privada de otro usuario del mismo Space. El contrato nativo
documentado exige 403; un diagnóstico real mediante el router confirmó 403 y
JSON con sólo `detail`, sin identidad de receta, para Consulta y Responsable.
Su fila sintética se revirtió mediante transacción; la secuencia PostgreSQL
puede avanzar. El primer adaptador diagnóstico falló sin retener su status:
se encontró la omisión de `detail=True` y se sustituyó por el callback real del
router. No se atribuye un status observado a ese primer intento. WRITE V5 exige
403 exacto y ausencia de datos de receta; la media sigue exigiendo 404.
En V5, READ y collector permanecen byte a byte iguales. WRITE V5 completó
9/9 PASS y WORKER V5 9/9 PASS. LOGIN V5 se detuvo en la primera cuenta: sus
cuatro checks funcionales pasaron, pero el collector agotó los 55 segundos y
cuatro llamadas `allHeaders` acabaron con contexto cerrado. Las otras ocho
cuentas no se ejecutaron; el FAIL se conserva. No se atribuye una causa concreta
de cancelación que no fue observada.

V6 calcula el mismo predicado exacto de origen/prefijo y consulta cabeceras sólo
fuera de ese ámbito: dentro, la condición original de fuga siempre era falsa.
Toda URL externa sigue fallando inmediatamente; sus auditorías de credenciales,
rechazos y bloqueos siguen fallando. Consola, red, 5xx, drain, plazo de 55 segundos
y recursos se conservan. Doce tests focales y revisión independiente PASS; las
cuatro funciones de fases siguen idénticas. Los resultados se vinculan por fase
a namespaces explícitos, sin escoger casos PASS de intentos fallidos.

La comprobación física acredita cero archivos de media y ausencia de las seis
imágenes/recetas subidas. Se retiraron nueve usuarios y tres Spaces sintéticos;
las nueve sesiones originales y nueve sustitutas están ausentes. Quedan un
administrador validado, un Space sin sharing, cero recetas y cero media.
El backup final coherente `20261007T004418Z-7c827cdf7a24` pasa cifrado AES256,
descifrado independiente y hashes de sus cuatro miembros; conserva schema 3,
114 tablas, 328 migraciones y el commit/imagen del runtime.

El ensayo inicial usó el backup coherente local cifrado y descifrado comprobado
`20261006T223348Z-3f404737d56a`. La restauración real se ejecutó en
`cuaderno-restore-90e837bbecd9`, con red interna y cero puertos publicados;
datos, media, configuración, imagen y assets/login nativo coinciden. Los
contenedores restaurados están detenidos. Durante el ensayo se detuvieron
solamente web/BD propios y se reanudaron los mismos contenedores y volúmenes.
Es una recuperación del punto de datos con la misma imagen de esta primera
instalación; no acredita un downgrade a una release productiva anterior ni un
login autenticado en el clon. El timer diario y la alarma local están instalados;
la prueba manual de alarma PASS no equivale a haber provocado `OnFailure`.

Los backups usan la fuente operativa congelada `source-runtime-60aca2d` para
conservar el commit del runtime cuando este checkout avance con documentación.
Las credenciales y evidencias operativas permanecen privadas, fuera de Git.
La copia offsite sigue pendiente: el propietario eligió `backups/` dentro del
proyecto, en este mismo VPS. Tampoco se acredita un iPad físico ni envío SMTP.

La comparación final de las 00:46 UTC con el baseline de las 22:20 UTC no
muestra cambios en los 16 contenedores y 46 servicios ajenos ni nuevos OOM.
Los ocho endpoints conservan sus status/error/redirección anteriores. Web:
327,1 MiB y 0,14 % CPU; BD: 29,99 MiB y 7,04 % CPU en la muestra, dentro de
sus límites. RAM disponible: 3.048.004 KiB; swap libre: 987.556 KiB; disco libre:
12.568.444.928 bytes. Readiness HTTPS 200 en 77 ms; ambos contenedores healthy.
La comprobación inmediata tras el backup falló; el snapshot posterior mostró
web `starting`. El predicado original no conservó el estado del contenedor.
Se conservan el FAIL y el registro de probes. La siguiente verificación completa
pasó, sin cambiar healthcheck ni runtime (start period nativo 120 s).
Se conservan los incidentes históricos: OOM/reboot de las 14:57–15:02 UTC,
temporales del diagnóstico local que agotaron disco, OOM durante mantenimiento
ajeno a las 17:54–17:55 y reinicios automáticos de cuatro bots a las 21:02.
No se afirma continuidad ininterrumpida de todos los servicios. Los 404 y el
error del portal `webmail-new` ya existían antes de este despliegue.
Procedimiento, recursos y pruebas finales en [runbook VPS](VPS_RUNBOOK_ES.md).

## Historial de preparación y candidatos anteriores

## Despliegue autorizado bajo prefijo — 6 de octubre de 2026

El propietario autoriza corregir, publicar en su fork y desplegar en `https://gex-dashboard.hopto.org/cuaderno-cocina/`. Se verificaron paquete, HEAD limpio inicial y los 2.350 archivos: `f2e3f3ca6da66848fd1234c6189a342184316d52+worktree.d793040fafe38d541b0a69356ce7ba2b91ba8fcbb6f7b3b8e88205fe98604725`. La autorización actual sustituye las restricciones históricas de publicación de este documento.

Correcciones implementadas: URLs y uploads derivados del base Django, cookies configuradas y limitadas al prefijo, media compartida de mismo origen, share target del manifiesto, healthcheck con excepción HTTPS exacta, worker/caches/cola/storage propios, Compose de bajo consumo y recuperación con configuración reproducida e identidad de imagen estricta. Revisión independiente de código recibida; el CI y las pruebas reales del nuevo candidato todavía deben terminar. Los resultados del CI base no se transfieren a esta revisión.

Pruebas focalizadas: 25 frontend/PWA PASS, 4 Django proxy PASS tras regresión roja, 21 backup/restore unitarias PASS y 3 autenticación E2E PASS. Se usan dependencias existentes, sin instalar Node ni navegadores en el VPS. La matriz CI añade HTTPS con prefijo y perfil productivo, conservando ediciones/roles/anchuras y Firefox/WebKit; G7 recoge 17 evidencias reales del mismo candidato y falla si falta alguna.

Inspección inicial: RAM disponible 2,3 GiB; swap usada 2,2/4 GiB; disco libre 23 GiB; ningún OOM en el journal consultado. 18081–18083 y los directorios productivos propuestos estaban libres. Correo en 8080 intacto; no se reinicia ningún servicio ajeno. El temporizador de reboot existente permanece habilitado. **Todavía no hay despliegue de Cuaderno ni modificación/recarga de Caddy.**

El propietario indica backups en una subcarpeta del proyecto. Será una copia local privada; no existe destino externo confirmado y no se acredita offsite. Procedimiento y límites en [runbook VPS](VPS_RUNBOOK_ES.md). Las pruebas reales de recuperación/rollback del nuevo candidato siguen pendientes hasta disponer de su imagen.

Primer candidato publicado: `00c3d87`, [CI 37463061834](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37463061834). Tooling, frontend, ambas suites PostgreSQL, build/identidad/SBOM/procedencia, Markdown runtime y Playwright raíz (193 pruebas, retries=0) PASS. El preview de prefijo falló: Gunicorn interpreta la variable reservada `SCRIPT_NAME` antes del adaptador WSGI y rechaza las rutas ya recortadas por el proxy. G7 no se ejecutó por esa dependencia fallida; este candidato no está aprobado para despliegue. Se corrige la separación entre prefijo lógico de Django y entorno de transporte de Gunicorn, con regresión HTTP real. Toda corrección exige otra imagen y nuevas evidencias; no se trasladan los PASS al candidato siguiente.

Segundo candidato: `11e8e116`, [CI 37468038137](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37468038137). La regresión Gunicorn real, los siete jobs iniciales y raíz 193/193 PASS. El preview HTTPS prefijado arranca correctamente; su matriz termina con 66 PASS y 243 FAIL de 309, retries=0. El diagnóstico confirma que ignorar errores HTTPS por contexto no permite a Chromium registrar el worker del certificado autofirmado. Se prepara confianza específica del certificado generado solo en el runner desechable, manteniendo la validación HTTPS y el collector. Un probe breve con Chromium ya instalado reprodujo rechazo con pin incorrecto y registro correcto con el SPKI exacto, sin cambiar el almacén de confianza del VPS.

Las comprobaciones anónimas también descubrieron que `browser.newContext` hereda la autenticación del proyecto Playwright: las sesiones omitidas explicaban los 200 en lugar de 404. Se añaden estado vacío y precondiciones de anonimato, espera de recarga de idioma y actualización real del worker con comprobación de cache ajeno. G7 del segundo candidato sí arrancó, pero falló al descargar la base fijada del scanner (HTTP 403 del cliente urllib); no acredita ninguno de los 17 controles pendientes. El cliente identificado recibe 200 y mantiene los mismos hashes obligatorios. La nueva revisión exige otro candidato y CI completo. **Producción, backup/restauración reales del VPS y recarga de Caddy siguen pendientes.**

Tercer candidato: `5b366375`, [CI 37477892105](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37477892105). Siete jobs iniciales y raíz 193/193 PASS, retries=0 (448,392 s). El preflight del prefijo falla antes de su matriz: Chromium/WebKit activan el worker, pero los temas nativos intentan cargar fuentes Poppins desde `/static/webfonts/`; Firefox rechaza el certificado CA servido como certificado de servidor. Se corrigen las 18 URLs de fuentes a rutas relativas (2 tests, 54 resoluciones reales de assets PASS) y se genera un certificado servidor separado `CA:FALSE`, firmado por una CA efímera exclusiva del runner. Contratos TLS y generación exacta de certificados revisados; la nueva ejecución de los tres motores sigue pendiente.

G7 del tercer candidato terminó FAIL antes de sus controles: Grype hidrata la DB durante `db import`, añadiendo índices y cambiando los bytes de SQLite. Comparar ese resultado con el archivo distribuido es incorrecto; tampoco debe reescribirse el `import.json` auténtico. La DB anterior, construida el 30 de septiembre, supera además su límite de antigüedad de 120 horas. Se verifica la publicación oficial del 6 de octubre (`v6.1.10`, construida `2026-10-06T06:32:14Z`): archivo comprimido SHA256 `1535cef8f13c12f3b7cdfc652722bb59d99fab934d0ac80d810a0462466d97cb` y SQLite distribuido SHA256 `977ceff7828db1b57fa5c0ada35e26f7c0dc783e5485f6b950c13c094761fbd8`. El [diagnóstico aislado 37487584544](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37487584544), commit `927dbaf026c9e2116d04550ec87298f471ee1cae`, verifica dos importaciones reales: ambas válidas, mismo archivo/binario/versiones/tamaño, pero SQLite instalado SHA256 `52ca6e40fd79b5c3680384241754d7a946ffc0a066c7def64d1962a8e30b7a4f` y `6d8cbe7cb8a7e2a31f0409378aa50c2f9c511a93ba6febae5dbdd2478a6dd2a4`, con digests nativos diferentes. El diagnóstico termina FAIL porque exigía determinismo; no se declara PASS. Se prepara una cadena verificable de pins oficiales hasta un recibo privado de la importación, cuyo SHA se entrega desde el proceso de provisión y no se toma del propio archivo. Auditoría y evaluación deben cotejar ese recibo, DB y metadata auténtico antes/después de status y scan. No se desactiva la validación de antigüedad ni se atribuyen estos resultados al siguiente candidato.

Incidente del host: el journal del boot anterior registra OOM global a las 14:57–15:00 UTC, incluyendo procesos Chromium y `thetadata_feed`; el VPS arrancó de nuevo a las 15:02 UTC (17:02 CEST). El agente no emitió reboot ni reinició Docker, Caddy o servicios ajenos. No se afirma que todos los servicios permanecieran ininterrumpidos. La importación diagnóstica local también resultó inadecuada: sus temporales consumieron mucho más disco del previsto; se detuvo únicamente su unidad propia y se retiraron sus archivos incompletos. No se repetirá en el VPS. Tras el reboot, los 16 contenedores y 46 servicios medidos están activos; la comparación de las 15:27 UTC con el baseline posterior al reboot no muestra nuevos cambios, ni OOM en el boot actual. RAM disponible 2,63 GiB, swap libre 1,99 GiB, disco libre 9,75 GiB; los cinco archivos de Caddy originales siguen idénticos y 18081–18083 libres. La producción de Cuaderno y la recarga de Caddy siguen pendientes.

Corrección del scanner implementada: recibo privado con token de confianza entregado desde memoria, pins de entrada separados de la huella instalada variable, metadata nativo conservado, rutas fijas y validación de bytes/propietario/permisos/enlaces antes y después de status, scan y evaluación. El contenedor Linux usa el UID:GID del runner para leer sus directorios 0700 sin capacidades; HOME/cache temporales dentro de su tmpfs. Regresiones focalizadas conjuntas: 86 Python PASS y 16 contratos Node TLS/auth PASS, incluidas mutaciones posteriores y falsificación del recibo. Estas pruebas no sustituyen la nueva imagen, sus 17 controles ni los browsers reales pendientes.


Cuarto candidato: `2257385ca4a486ad6bd726b644a960a800588177`, [CI 37490988588](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37490988588). Ambas suites PostgreSQL, frontend, tooling, imagen/procedencia y Markdown PASS. Raíz: 193/193 PASS, retries=0, 445,078 s. El preflight prefijado activa el worker en Chromium, Firefox y WebKit; las fuentes permanecen dentro del prefijo. Matriz de prefijo: 291 PASS y 18 FAIL de 309, retries=0. Los 18 fallos corresponden a Chromium al abrir recetas con imagen privada y muestran exclusivamente dos rechazos no gestionados `Wake Lock permission request denied`; los casos Firefox/WebKit pasan. La vista de receta debe gestionar la denegación permitida de esta función opcional y sus promesas de liberación/recuperación, conservando los errores inesperados visibles. Se prepara una corrección focalizada con pruebas rojas/verdes; no se cambian permisos del navegador ni collector, retries o aserciones. G7 terminó FAIL: 12/17 controles PASS; regresión nativa, integración, seguridad y rendimiento no pueden leer el archivo público de requisitos montado, y la evaluación Linux rechaza la composición nueva de ocho hallazgos. El ensayo adicional productivo de recuperación falla con RuntimeError capturado cuya operación aún debe diagnosticarse. Este candidato no está aprobado ni desplegado. La imagen descargada y verificada se conserva como evidencia, sin activar producción.

Corrección Wake Lock implementada y revisada independientemente: controlador nativo acotado a la vista de receta, con denegaciones esperables gestionadas, liberación al salir, recuperación al volver visible y liberación de adquisiciones que llegan tarde. La revocación estando visible no inicia un bucle de nuevas peticiones; los errores inesperados se reportan. Pruebas significativas rojas/verdes: 9/9 PASS, reproducidas por el revisor con el Node 24 ya existente, sin instalaciones, build local ni navegador. La compilación, typecheck y matriz browser completa de la nueva imagen siguen pendientes.

Verificación del host a las 16:29 UTC: los 16 contenedores y 46 servicios siguen idénticos al baseline posterior al reboot, sin OOM del boot actual ni cambios en los cinco archivos de Caddy. RAM disponible 2,63 GiB, swap libre 1,48 GiB, disco libre 10,09 GiB; 18081–18083 libres. Esto acredita el estado de esa medición, no continuidad ininterrumpida durante toda la sesión.

Correcciones G7 en preparación para un quinto candidato: los requisitos públicos de tests pasan a 0444 mientras staging/env conservan 0700/0600; la lectura real con UID 10001 pasa y sus 17 tests focales fueron revisados. Se conserva el scan Linux completo de ocho hallazgos y cero ignorados. Cuatro corresponden a los backports Alpine existentes y uno a poplib. Ada (`CVE-2024-9410`) afecta al servicio Ada.cx, mientras la imagen contiene la biblioteca ada-url; nghttp2 (`CVE-2026-58055`) afecta al proxy nghttpx, ausente, mientras se conserva la biblioteca libnghttp2. Sus fuentes oficiales, versiones, subpaquetes, bytes de bibliotecas y ausencia del proxy deben demostrarse en cada candidato; no basta una lista de CVEs aceptadas.

El hallazgo Python `CVE-2026-12345` sí requiere remediación: los archivos tempfile/shutil de 3.13.16 son los originales. Se integra el par del [backport oficial 3.13](https://github.com/python/cpython/pull/158429), commit `56caf8e0b89463e2e8465ce06f7aaa31847c1768`, con hashes originales/nuevos, licencia PSF, procedencia e instalación offline estricta. Ese PR permanece abierto: no se afirma que sea un fix publicado. Patcher y comportamiento benigno: 16/16 PASS y revisión independiente en el host Python 3.12.3. La nueva imagen debe verificar el par real, el runtime 3.13.16, capacidades Linux de borrado mediante descriptores, ausencia de file flags y compatibilidad funcional; fallará si falta cualquiera. El manifiesto de release incorpora un noveno artefacto para esta procedencia. Integración focalizada: 60 tests PASS; el build y G7 reales siguen pendientes.

La [ejecución diagnóstica de recuperación 37500272630](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37500272630), rama aislada `cuaderno-production-probe-20261006`, commit `9731456bc669a6a7c4774a8b1c2b83c63cdb4863`, usa exclusivamente la imagen 225 ya verificada en un runner externo. Verifica archivo/identidad y sus ocho artefactos reales antes del ensayo; guarda únicamente fase, operación permitida, clase de error y estado de limpieza, sin secretos. Terminó PASS: backup/restauración completos, misma imagen, assets/login/manifiesto bajo prefijo comprobados, contenedores de restauración detenidos y cero puertos publicados; la limpieza del proyecto propio también pasa. El ZIP de tres informes se verifica con SHA256 `46a1d922e936ade1fc65fc4e3ad10c1f8dfa7a039627f3864bb43426367099b4`. La instrumentación conserva los métodos de transporte originales; el RuntimeError del G7 previo sigue sin una causa localizada y no se presenta como corregido por este resultado. No es una certificación del siguiente runtime. Cuaderno productivo, backup/restauración reales del VPS y recarga de Caddy permanecen pendientes.

Cierre local de las correcciones del quinto candidato: se reincluye el patcher en el contexto Docker específico y se añaden regresiones para tipos booleanos de schema, fuentes enlazadas/alteradas y lectura acotada de sus mismos bytes. El patcher empaquetado queda además ligado al manifiesto de aplicación; su ausencia o alteración se rechaza. La suite completa de tooling pasa 427/427 con el host Python 3.12.3 y PyJWT 2.15.0 leído de la imagen retenida en una ruta privada, sin instalación ni modificación de entornos ajenos. Con el PyJWT 2.7.0 original del host fueron 424 PASS/2 errores; ese resultado también se conserva. Esto no acredita el runtime 3.13.16 ni el CI del quinto candidato, que deberán ejecutarse sobre sus fuentes limpias y nueva imagen.

Quinto candidato `14af268fd40847338473587f08af289da095aff7`, [CI 37503603756](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37503603756): ocho jobs PASS, raíz 193/193 y prefijo 309/309, sin retries ni skips; preflight del worker PASS en Chromium, Firefox y WebKit. G7 falla con 15/17 PASS: integración no monta dos contratos JSON canónicos y la auditoría interpreta el nombre que devuelve `apk info -e` como versión. Scan original: ocho hallazgos, cero ignorados; la evaluación runtime termina antes de comprobar completamente tempfile y alcance, por lo que no se certifica. El ensayo productivo adicional de esa misma imagen sí pasa: backup/restauración, assets/manifiesto/login prefijados, sin puertos publicados, contenedores detenidos y limpieza completa. Ningún resultado acredita la siguiente imagen; el quinto candidato no está desplegado.

Correcciones para el sexto candidato: contratos de pruebas montados desde sus rutas canónicas, solo lectura, validación de enlaces/identidad y lectura real UID 10001; requisitos públicos 0444, staging 0700 y env 0600 conservados. El lector APK obtiene P/V y hashes de bloques de una sola lectura de `/lib/apk/db/installed`, rechaza campos ausentes/duplicados, registros duplicados y paquetes requeridos ausentes. Sus pruebas ejecutan el lector realmente empaquetado contra seis bloques extraídos de la imagen anterior; la reproducción roja falla con el lector anterior. La lectura benigna del registro completo, incluido el paquete virtual `.python-rundeps`, también pasa. Tooling ligero completo: 434/434 PASS en Python 3.12.3 con PyJWT 2.15.0 aislado. Falta revisión final, imagen nueva y CI completo; no se transfieren los PASS del quinto.

Segundo incidente del host: OOM global a las 17:54–17:55 UTC, durante actividad de mantenimiento concurrente que el propietario confirma terminada. `thetadata_feed` se recuperó automáticamente; `user@1000.service` queda en estado failed. Se observaron recreaciones ajenas de tres contenedores. No se atribuye causa exclusiva ni continuidad ininterrumpida, y no se reinician servicios ajenos. Se conserva la referencia anterior y una nueva medición posterior a esa tarea. A las 18:32 UTC no hay cambios nuevos respecto de esa referencia en los 16 contenedores y 46 servicios; los cinco archivos de Caddy siguen idénticos, sin nuevos eventos OOM. RAM disponible 2,62 GiB, swap libre 0,83 GiB, disco libre 11,54 GiB; puertos 18081–18083 libres. Cuaderno productivo y recarga de Caddy siguen pendientes.

Sexto candidato `ff5d1abc9626fca1eca65247a55a71a586624500`, [CI 37513108397](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37513108397): ocho jobs PASS y uno FAIL. Raíz 193/193 PASS; prefijo 308/309, con una cancelación de petición nativa detectada por el collector estricto en WebKit Integral/Responsable/768. La traza muestra peticiones de recuento y planificación pendientes al navegar a ajustes; la cancelación precede al cambio de idioma. G7 termina 17/17 PASS: ocho hallazgos brutos, cero ignorados y comprobaciones runtime completas del par tempfile/shutil, versiones APK y alcance de componentes. El ensayo productivo adicional de la misma imagen también pasa. Evidencias y hashes revisados independientemente; el FAIL del prefijo impide desplegar este candidato.

Preparación del séptimo candidato: el harness espera la señal visible de StartPage y el cierre de los cuerpos de las peticiones nativas observadas antes de permitir la siguiente navegación. Una única espera comparte el presupuesto existente de ocho segundos; las peticiones opcionales ausentes no se exigen y los errores reales se propagan. Collector, configuración, retries y límites permanecen intactos. Regresión roja significativa y 35/35 pruebas ligeras PASS, incluidas 17 nuevas; cuatro archivos revisados independientemente. Falta CI completo e imagen nueva; ningún PASS anterior certifica este candidato.

A las 18:54 UTC `user@1000.service` vuelve a estar activo sin intervención de este despliegue. Los otros 45 servicios y 16 contenedores siguen idénticos a la referencia posterior a la otra tarea; cinco archivos Caddy sin cambios y sin nuevos OOM. Se conserva el historial del incidente y se medirá de nuevo antes de arrancar Cuaderno. No se atribuye causa exclusiva ni continuidad ininterrumpida.

Séptimo candidato `bda944d35bd0039d96454d53a883fdbc5e702077`, [CI 37521898680](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37521898680): ocho jobs PASS y uno FAIL. Raíz 193/193 y prefijo 309/309 PASS, retries/skips/flaky=0; worker activo en Chromium, Firefox y WebKit. Los 17 registros G7 pasan y sus hashes, bindings y comprobaciones runtime se revisaron independientemente. Falla únicamente el ensayo productivo adicional durante `docker.exec.pg_restore`; el diagnóstico conserva RuntimeError y limpieza PASS, pero no stderr, por lo que la causa concreta permanece sin demostrar. No se descargó ni desplegó esa imagen.

Preparación del octavo candidato: la espera anterior por socket Unix podía aceptar el servidor temporal de inicialización de PostgreSQL. Se exige primero TCP y después `SELECT 1` en la base exacta, con timeout de uno y dos segundos respectivamente; se conservan 120 iteraciones, sleep de un segundo y los intervalos/reintentos del healthcheck productivo. La instrumentación adicional retiene solo una categoría permitida del primer fallo de pg_restore, sin stderr, SQL ni secretos. Regresiones focalizadas: 38/38 PASS tras controles rojos significativos. El [ensayo externo 37531553112](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37531553112), commit aislado `2d24d5fa6ce6d18886b0112aa0c66d130c768b1a`, termina PASS con la imagen PostgreSQL fijada: el socket temporal acepta conexiones mientras TCP y finalización siguen falsos; el servidor definitivo supera TCP y SQL exacto en la base propia. Confirma timeout, socket explícito y limpieza de cuatro recursos propios, sin puertos publicados. ZIP oficial SHA256 `84a4e2ba41fb0d346abad7791a88417ecf3076b443c0909ac9c42bdb3a39d66c`. Reproduce el defecto controlado; no certifica el nuevo candidato ni identifica la causa del fallo anterior. Tooling completo 454/454 PASS con Python 3.12.3 y PyJWT 2.15.0 privado; validación Compose PASS sin arrancar servicios.

A las 21:06 UTC los 16 contenedores y los cinco archivos Caddy siguen sin cambios y no hay nuevos OOM. Cuatro bots ajenos muestran un reinicio automático reciente y están activos; no fueron modificados por este despliegue. RAM disponible 2,80 GiB, swap libre 1,25 GiB y disco libre 10,97 GiB; 18081–18083 libres. Cuaderno, backup/restauración productivos del VPS y recarga Caddy siguen pendientes. Conservar las referencias anteriores y medir de nuevo antes del arranque propio.

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
