# Operación de Cuaderno en el VPS compartido

## Instalación real — 7 de octubre de 2026

URL: `https://gex-dashboard.hopto.org/cuaderno-cocina/`.
Proyecto exclusivo: `cuaderno-prod`; único puerto publicado
`127.0.0.1:18081`, sin puerto PostgreSQL. Caddy existente actúa como proxy.
La referencia de esta instalación es el commit
`60aca2d0aa7776137f507699be7f111dcf758e18`, source SHA256
`c8e1848750193af6a7377e521195b4295a10ab3da59c16fa40589fba4444f229`.
ImageID local OCI:
`sha256:93854211cee63e58ca2bd4b066f06af6a5aba17ae150a8acaf33a0a3d7b1d0ce`.
Config digest de CI:
`sha256:aa9fdc7aacfd5d03e3c5cd00071d4daae71f78aa258221023735d713a44f9732`.
El CI completo es [37532317372](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37532317372).

Rutas actuales, todas bajo el paquete
`/home/kripta/cuaderno-cocina-deploy-20261006-f2e3f3ca6` cuando son relativas:

| Recurso | Ruta o identidad |
| --- | --- |
| Fuente operativa congelada y Compose | `source-runtime-60aca2d/` |
| Desarrollo y documentación publicada | `source-checkout/` |
| Configuración privada | `/etc/cuaderno-cocina/production.env`, root 0600 |
| Administrador | `/etc/cuaderno-cocina/admin-credentials.json`, root 0600 |
| Herramientas operativas propias | `/opt/cuaderno-cocina/bin/` |
| Base de datos | volumen `cuaderno-prod_database`, `/var/lib/docker/volumes/cuaderno-prod_database/_data` |
| Media | volumen `cuaderno-prod_media`, `/var/lib/docker/volumes/cuaderno-prod_media/_data` |
| Copias locales | `backups/`, root 0700; bundles y `encrypted/` privados |
| Clave de cifrado | `/etc/cuaderno-cocina/backup-encryption.key`, root 0600 |
| Evidencias y harness privados | `agent-evidence/`, root 0700, informes 0600 |

El directorio reservado `/var/lib/cuaderno-cocina` no contiene la BD productiva.
No borrar el worktree operativo ni su repositorio Git común: el backup registra
su HEAD congelado, aunque `source-checkout` avance con documentación. Git sólo
confía en esa ruta exacta dentro de la unidad de backup; no hay wildcard global.
No imprimir el env, la clave, passwords, cookies o JSON de credenciales.

Web: usuario 10001:10001, 768 MiB, 0,5 CPU, PIDs 256, un worker y dos threads.
BD: 512 MiB, 0,5 CPU, PIDs 128, shared_buffers 64 MiB y max_connections 30.
Ambos eliminan capacidades, usan NoNewPrivileges y restart `unless-stopped`.
DEBUG, signup, conectores, plugins e IA desactivados; espacio principal sin
sharing. Los límites deben conservarse salvo nueva medición y justificación.

### Operaciones propias reproducibles

Comprobar estado sin mostrar secretos:

```bash
cd /home/kripta/cuaderno-cocina-deploy-20261006-f2e3f3ca6/source-runtime-60aca2d
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno-cocina/production.env -f deploy/cuaderno/compose.production.yml ps
curl --fail --silent --show-error https://gex-dashboard.hopto.org/cuaderno-cocina/health/ready/
systemctl status cuaderno-cocina-backup.timer --no-pager
```

Backup coherente y cifrado usando la unidad ya instalada:

```bash
systemctl start cuaderno-cocina-backup.service
systemctl show cuaderno-cocina-backup.service --property=Result --property=ExecMainStatus
journalctl -u cuaderno-cocina-backup.service -n 10 --no-pager
```

El wrapper detiene sólo web propia, rechaza escritores/clients DB ajenos,
incluye dump + media + env privado + manifiesto schema 3 y reanuda web en
`finally`. Cifra AES256 con integridad, verifica el descifrado completo y sus
cuatro miembros/hashes antes de retener los siete puntos completos más recientes.
No cuenta el directorio incompleto del primer intento. Un backup hace una pausa
breve de Cuaderno; ejecutarlo sin pruebas browser simultáneas. Timer:
03:17 Europe/Madrid con retraso aleatorio de hasta 15 minutos, Persistent=true.
La alarma escribe en journal, sin enviar correo; el test manual pasó tras añadir
`--` al mensaje de logger. La ruta automática `OnFailure` está configurada y
no se ha provocado deliberadamente.

Para un ensayo de recuperación, verificar antes el bundle, imagen exacta,
capacidad y recursos propios libres. Detener **sólo** web/BD de `cuaderno-prod`
para evitar dos runtimes simultáneos en este host; reanudarlos aunque falle el
ensayo. Desde la fuente congelada, ejecutar con un nombre de informe nuevo:

```bash
python3 -B scripts/cuaderno/production_restore_verify.py ../backups/20261006T223348Z-3f404737d56a --runtime-image sha256:93854211cee63e58ca2bd4b066f06af6a5aba17ae150a8acaf33a0a3d7b1d0ce --report ../agent-evidence/restore-nuevo.json
```

El comando crea un namespace aleatorio `cuaderno-restore-*`, red interna y
volúmenes separados; verifica datos/media/configuración/imagen y páginas nativas
prefijadas. Detiene sus contenedores al finalizar y conserva sus recursos para
revisión. No promueve volúmenes ni cambia la imagen productiva. El ensayo real
`cuaderno-restore-90e837bbecd9` pasó, y los contenedores originales volvieron
healthy conservando IDs y volúmenes. No se ensayó login autenticado en el clon.

### Rollback y actualizaciones

En esta primera instalación, el rollback probado recupera el punto de datos en
un clon con la misma imagen y demuestra la reanudación de producción original.
También se retiró realmente el bloque propio de Caddy y se verificó la
configuración anterior antes de volver a publicar. No existe una release
productiva previa cuyo downgrade se haya probado. Para una actualización futura,
exigir nuevo CI/imagen, backup cerrado previo y ensayo del esquema restaurado.
Volver a un tag anterior no deshace migraciones; conservar la pareja imagen +
backup compatible y restaurarla aisladamente antes de cualquier promoción.

Caddyfile actual SHA256:
`f20a5788a5a98e2a80d8572b5e129c3f3e35c8efe077bdf376bec12a606a1420`.
Bloque propio: 439 bytes, SHA256
`15d9b7992d34950be0f82a41ac38c100d57f424a9fbca508ea2c72220c35f1c1`.
Sus bytes y la referencia inicial están en las copias/evidencias privadas.
Para retirar la ruta, leer el Caddyfile **actual**, exigir una única coincidencia
exacta del bloque, eliminar sólo esos bytes y conservar toda edición concurrente.
Validar los imports y el entorno efectivo del proceso Caddy antes de reemplazar
atómicamente el archivo propio, conservando root:root 0644, y recargar por CLI.
Comparar después el JSON activo, estado, PID y endpoints. Si la ruta no coincide
exactamente, detenerse y revisar; nunca restaurar sobre el archivo completo una
copia histórica. No cambiar rutas raíz `/api`, `/static`, `/media` ni workers.
La validación adaptada normaliza exclusivamente la ruta temporal generada en
`file_server.hide`; el JSON activo se compara sin normalizarlo.

Docker, Caddy y el timer propio tienen arranque habilitado; los contenedores usan
restart `unless-stopped`. El reboot preexistente de las 08:30 Europe/Madrid
permanece programado. Se comprueba configuración y readiness; no se ejecuta un
reboot real para ensayar esta aplicación. Tras un reboot, repetir `ps`, HTTPS
ready y comparación de servicios/endpoints, sin reiniciar globalmente Docker,
Caddy, correo u otras aplicaciones.

### Evidencias y límites de esta instalación

CI: `eighth-ci-completed-verification.json`; identidad:
`candidate-60aca2d-local-attestation-actual-image.json`; backup inicial:
`eighth-production-initial-backup-verification.json`; recuperación:
`eighth-production-isolated-recovery-and-rollback-verification.json`; Caddy:
`eighth-caddy-second-cutover.json`. Todas dentro de `agent-evidence/`.
Aceptación pública final: **54/54 PASS** de tres ediciones y tres roles. READ V4
27 casos a 390/768/1440 px; WRITE V5, WORKER V5 y LOGIN/LOGOUT V6, nueve cada
una a 1440 px. Sin retries; fases completas con namespaces explícitos. El collector
conserva fallos por destinos externos, cabeceras con credenciales, consola, red y
5xx; V6 omite solamente el RPC de cabeceras dentro del ámbito cuyo predicado de
fuga siempre era falso. Los fallos anteriores permanecen documentados en STATUS.

Informes privados del cierre:

- `eighth-public-vps-final-54-verification.json`: hashes de los 54 casos.
- `eighth-production-physical-media-verification.json`: seis imágenes/recetas
  propias ausentes y cero archivos en el volumen, sin borrados por el verificador.
- `eighth-production-synthetic-cleanup.json`: nueve usuarios/tres Spaces retirados.
- `eighth-production-final-backend-verification.json`: administrador validado,
  un Space sin sharing, cero recetas/media, DEBUG desactivado.
- `eighth-production-final-session-verification.json`: nueve sesiones originales
  y nueve sustitutas ausentes.
- `eighth-production-final-backup-verification.json`: backup final
  `20261007T004418Z-7c827cdf7a24`, cifrado/descifrado independiente, cuatro miembros
  y hashes comprobados. Manifiesto SHA256
  `92ddc7b0ad916f644f2a4fbdbac0c41169f8345140934f00bed551da798c2953`;
  cifrado en `backups/encrypted/20261007T004418Z-7c827cdf7a24.tar.gpg`, SHA256
  `1a0e0f22afb526245b4a7a5b9b380b986ac0d09217e909307da6c2e93e75d4fe`.
- `eighth-production-final-runtime-verification.json`: identidad/health/puertos,
  privilegios/límites, Caddy y timers, listeners de correo y recursos.
- `eighth-production-final-shared-services-verification.json`: comparación real
  de 16 contenedores, 46 servicios y ocho endpoints; sin cambios ni OOM nuevos.

La restauración aislada anterior corresponde al punto inicial; el bundle final
posterior a la limpieza tiene verificación de backup/descifrado, sin otro ensayo
de restauración. No se transfiere el resultado de una imagen anterior.
La comprobación inmediata después del backup final falló; el snapshot posterior
mostró web `starting`. El predicado original no conservó el estado del contenedor.
Ese FAIL se conserva en `eighth-final-runtime-immediate-check-failure.json`.
El registro posterior muestra HTTPS 200 y luego healthcheck healthy, dentro del
start period nativo de 120 s. Se repitió la verificación final sin cambiarlo.

Muestra final del 7 de octubre, 00:46 UTC (sin browser activo):

| Recurso | Medición | Límite |
| --- | --- | --- |
| Web | 327,1 MiB; 0,14 % CPU | 768 MiB; 0,5 CPU |
| PostgreSQL | 29,99 MiB; 7,04 % CPU | 512 MiB; 0,5 CPU |
| Host | 3.048.004 KiB RAM disponible; 987.556 KiB swap libre | sin cambios globales |
| Disco | 12.568.444.928 bytes disponibles | sin limpieza global |
| HTTPS ready | 200, 77 ms | sin redirección |

Son muestras puntuales, no una prueba de carga ni una garantía de capacidad
futura. El pico del browser READ fue 760,2 MiB; LOGIN V6, 505,7M según systemd,
ambos dentro del límite y con swap del cgroup 0. La emulación no acredita hardware.

No hay destino offsite: las copias autorizadas están en el mismo VPS, incluso
cuando están cifradas. No se acredita iPad físico ni envío/recepción SMTP.
Las pruebas seriales de Chromium instalado emulan anchuras 390/768/1440; las
pruebas Firefox/WebKit pertenecen a CI. Los incidentes históricos del host están
en STATUS; los 404 y el error preexistente de `webmail-new` no se presentan como
endpoints sanos. Comparar con el baseline, sin hacer CRUD/carga en otras apps.

## Procedimiento general y antecedentes

Destino autorizado: `https://gex-dashboard.hopto.org/cuaderno-cocina/`. Esta guía
describe a continuación el procedimiento general. La instalación y los ensayos
realmente ejecutados están en el apartado vigente anterior, STATUS y
RELEASE_CHECKLIST; un comando preparatorio no constituye por sí solo un PASS.

## Identidad y aislamiento

La fuente es el checkout Git del paquete entregado. El proyecto exclusivo será
`cuaderno-prod`, con PostgreSQL sin puerto publicado y web en `127.0.0.1:18081`.
Revalidar puertos, directorios, proyectos, redes y volúmenes antes de cada primera
instalación. Nunca reutilizar recursos que no se hayan identificado como propios.
El correo ocupa 8080. Caddy es el existente; no crear otro proxy en este servidor.

El entorno privado será `/etc/cuaderno-cocina/production.env` (0600), separado de
Git. Secretos nuevos, DEBUG=0, dominio explícito, plugins/conectores/IA/signup
desactivados. Compose usa un worker, dos threads, web 768 MiB y BD 512 MiB con
0,5 CPU por servicio; medir antes de aumentar. Caddy sobrescribe forwarded proto,
host, IP y script name; nginx añade su salto, por lo que el contador inicial es 2.
Verificar la IP resultante con una petición propia antes de aceptar ese contador.

El arranque conserva el prefijo lógico en `CUADERNO_APP_SCRIPT_NAME` y retira
`SCRIPT_NAME` solo del proceso Gunicorn: esa variable reservada hace que Gunicorn
rechace las rutas que Caddy ya recorta. Los comandos de gestión y el metadata del
contenedor conservan la configuración original para backups. No añadir de nuevo
el prefijo en nginx ni cambiar el handler previsto de Caddy.

El ImageID de Docker no es un tag ni necesariamente el digest de configuración:
Docker 29 con containerd puede identificar el manifiesto OCI. Antes de cargar,
verificar SHA256 del archivo, config digest del archivo, identidad de fuentes,
SBOM y procedencia. Después de cargar, verificar que el manifiesto local enlaza a
esa misma configuración. Registrar ambos identificadores cuando difieran; no
atribuir a otra imagen las pruebas de CI.

La fixture TLS prefijada de CI usa una CA efímera y un certificado servidor firmado
separado, `CA:FALSE`, con SAN `127.0.0.1` y propósito `serverAuth`. La CA se instala
solo en el runner desechable; Firefox recibe su política de instalación y Chromium
el SPKI exacto del servidor. Nunca instalar esa CA en este VPS ni usar un certificado
CA como servidor. El preflight exige activación real del worker en los tres motores.
Los temas nativos deben resolver también sus fuentes dentro del prefijo.

Grype conserva la validación de antigüedad de DB (120 horas). Antes de certificar
otro candidato, verificar que sus pins siguen vigentes; si caducan, renovar desde
la publicación oficial de Anchore, comprobar SHA256 del archivo y SQLite distribuido,
y verificar por separado el SQLite instalado después de la hidratación real y su
`import.json` auténtico. No reescribir ese metadata ni confundir la versión del
cliente (`v6.1.9`) con el esquema de DB (`v6.1.10`). Obtener las huellas instaladas
con importaciones independientes en CI externo; el diagnóstico comprobó que su
hidratación no produce bytes deterministas. Por eso el gate enlaza los pins oficiales
del archivo/SQLite distribuido/binario con un recibo privado de la importación real:
su SHA se entrega desde el proceso de provisión, nunca desde el propio recibo.
Auditoría y evaluación revalidan DB, metadata y recibo durante todas sus etapas.
Sus índices y temporales hacen inadecuada esta operación para el VPS compartido.
Repetir CI/scan completo.
La composición del scan cambia con su DB fijada: la publicación del 6 de octubre
devuelve ocho hallazgos, conservados sin ignoredMatches. La evaluación exige
pruebas exactas del runtime para todos: cuatro backports Alpine, poplib, el par
tempfile/shutil y dos coincidencias de producto/componente comprobadas contra
fuentes primarias y bytes de bibliotecas. El backport tempfile de CPython 3.13
está fijado a `56caf8e0b89463e2e8465ce06f7aaa31847c1768`; su PR 158429 sigue abierto.
La imagen debe contener sus dos módulos verificados, licencia PSF y el noveno
artefacto `SECURITY.tempfile-backport.json`; comprobar Linux con borrado por
descriptores, sin file flags y limpieza funcional normal. No sustituir estas
pruebas por aceptación genérica de CVEs ni atribuirle estado de fix publicado.
El lector runtime obtiene las versiones `P:`/`V:` y los hashes de los bloques del
mismo registro `/lib/apk/db/installed`, leído una sola vez. Rechaza identidades,
versiones o paquetes requeridos ausentes/duplicados y conserva paquetes virtuales
como `.python-rundeps`. `apk info -e` comprueba existencia y por defecto devuelve
el nombre, no una versión; no usarlo como procedencia. Los controles de integración
montan además los dos contratos JSON canónicos de tests, solo lectura, con sus
ancestros y archivos verificados y legibles por UID 10001. Estos fixtures no se
empaquetan dentro del runtime productivo.
Un informe histórico o desactivar la validación
de edad no acredita el candidato nuevo.

## Publicación y primer arranque

Publicar cambios revisados en `NexIA-AI-Web-Solutions/cuaderno-cocina`, rama
`cuaderno/main`, sin force ni upstream. El CI construye una imagen ligada a la
fuente limpia, ejecuta raíz y prefijo HTTPS y reúne los 17 controles del candidato.
La migración nativa, las regresiones, el rendimiento, la auditoría Linux y la
recuperación deben pasar; no sustituir un resultado fallido por el CI base.

Con la imagen nueva verificada y `CUADERNO_IMAGE=sha256:ID_LOCAL` en el env file:

```bash
python3 -B scripts/cuaderno/production_config_check.py
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno-cocina/production.env -f deploy/cuaderno/compose.production.yml config --quiet
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno-cocina/production.env -f deploy/cuaderno/compose.production.yml up -d --no-build --pull never --wait --wait-timeout 600
```

Este arranque aplica migraciones solamente en la BD nueva de Cuaderno. Crear el
administrador con contraseña fuerte, por entrada privada, sin publicarla en logs
ni documentación. Nunca usar semillas ni contraseñas DEMO en producción.
Probar por loopback nginx→Django→PostgreSQL, forwarding HTTPS, prefijo, assets,
redirecciones, media autorizada y JSON `ready=true` sin 301.

Respaldar Caddyfile e imports en un directorio privado. Comparar su hash con el
leído antes de escribir. Añadir exclusivamente la redirección 308 del prefijo
sin barra y su `handle_path /cuaderno-cocina/*`, con límite 54525952 bytes y proxy
a 18081. Conservar rutas/imports/dominos existentes. Validar con el entorno real
del servicio y recargar Caddy. Comparar endpoints seguros previamente medidos;
no ejecutar CRUD ni carga en ninguna aplicación ajena.

Playwright debe usar cuentas sintéticas propias y destino explícito,
verificando login/logout, cookies/path, CSRF, assets/API/media, manifesto, worker,
roles, responsive, impresión y recargas. No instalar navegadores/build tools en
este VPS. Si se usa el Chromium ya instalado en el host, registrar esa ejecución
como local y serializar sus contextos; no atribuirle ejecución remota ni los tres
motores que se verifican por separado en CI. No cambiar las guardas loopback del harness CI para apuntarlo a datos
reales: el smoke público requiere su namespace/cuentas sintéticas explícitos.

## Backup y recuperación

El propietario indicó una subcarpeta del proyecto para las copias. Usar
`../backups` respecto al checkout, privada 0700 y fuera de la fuente canónica:

```bash
python3 -B scripts/cuaderno/production_backup.py --env-file /etc/cuaderno-cocina/production.env --destination-parent ../backups --include-env
python3 -B scripts/cuaderno/production_restore_verify.py ../backups/BUNDLE --runtime-image sha256:ID_LOCAL
```

La copia detiene solo el escritor Cuaderno, rechaza clientes externos y obtiene
dump+media coherentes, hashes, configuración, imagen y entorno privado 0600.
Siempre reanuda el escritor en finally. La restauración usa red interna, BD y
media nuevos, misma imagen y configuración de prefijo, sin puertos publicados;
verifica contenido y readiness, detiene sus contenedores y conserva sus volúmenes.
Registrar duración, fingerprint, informe y recursos exactos del ensayo.

En este VPS, ejecutar el ensayo de recuperación después de cerrar y verificar el
backup, deteniendo primero solo los servicios `web` y `db` de `cuaderno-prod`.
El verificador no necesita los contenedores originales en marcha; así se evita
sumar dos PostgreSQL y dos webs al pico de memoria. Exigir en su informe
`passed=true`, `containers_stopped=true`, `published_ports=false` y
`runtime_candidate.prefixed_manifest_assets_login_verified=true`. Resolver cualquier
limpieza fallida de sus contenedores propios antes de reanudar producción con
`up -d --no-build --pull never --wait --wait-timeout 600 web db`, conservando env,
imagen y volúmenes originales. Repetir readiness y login por loopback; no volver
a ejecutar el bootstrap de cuentas. No detener servicios de otros proyectos.

El smoke HTTPS crea únicamente nueve cuentas temporales en tres Spaces sintéticos,
con sesiones limitadas a dos horas y cookies propias del prefijo. Ejecutar los
contextos serialmente, verificar las rutas físicas de cualquier upload de prueba
y eliminar después solo sus recetas, Spaces, usuarios y sesiones identificados.
El administrador productivo se conserva separado de esas cuentas y de las trazas.
No publicar valores de contraseñas, cookies ni tokens en los informes browser.

Activar un timer propio solo después del primer backup/restauración. El servicio
debe usar estas rutas efectivas, `--include-env`, UMask=0077 y OnFailure para una
alarma local visible en journal. Retención máxima propuesta: siete bundles
cerrados; borrar únicamente bundles propios verificados, nunca datos activos.
No enviar correo ni activar servicios externos automáticamente.

Wrapper operativo preparado en `/opt/cuaderno-cocina/bin/backup.py`, fuera de la
fuente congelada: ejecuta el backup coherente y cifra una copia en `../backups/encrypted`
con GnuPG AES256 y protección de integridad. La clave propia es
`/etc/cuaderno-cocina/backup-encryption.key` (0600); no mostrarla ni ponerla en Git,
en argumentos o dentro de la copia cifrada. Usa un home GnuPG privado propio y
`--no-symkey-cache`. Comprueba descifrado completo y hashes; antes de la retención
vuelve a descifrar cada copia y coteja los cuatro archivos regulares exactos contra
el bundle. Solo siete pares completos verificados cuentan para borrar los anteriores.
El servicio puede escribir únicamente backups y su home GnuPG. El cifrado y la
retención pasan pruebas sintéticas y revisión independiente; aún no están activados
ni acreditan una copia/restauración real de producción.

La ubicación indicada está en este mismo VPS. **No hay copia externa configurada**.
No afirmar protección frente a pérdida del servidor. Una futura transferencia
requiere destino autorizado, cifrado antes de salir y comprobación de recepción.

## Sincronización de aceptación bajo prefijo

La CI del sexto candidato `ff5d1ab` pasó raíz 193/193, G7 17/17 y el ensayo productivo adicional, pero falló prefijo 308/309. No autoriza su despliegue. La traza WebKit muestra cancelaciones nativas de StartPage durante una navegación completa a ajustes, anteriores al cambio de idioma. El séptimo candidato espera la señal visible de StartPage y los cuerpos completos de las respuestas nativas de recetas/planificación observadas en su origen y prefijo. Las peticiones opcionales ausentes no se esperan; cualquier error de finalización sigue fallando. Se conserva el presupuesto compartido de ocho segundos, sin alterar collector ni retries. Las 35 pruebas ligeras y la revisión focal no sustituyen nueva CI, imagen ni aceptación HTTPS real.

El OOM concurrente y las recreaciones ajenas quedan en STATUS. El gestor `user@1000.service` se observó de nuevo activo a las 18:54 UTC sin actuación de Cuaderno. Capturar una nueva referencia antes de arrancar, conservar las anteriores y comparar servicios, contenedores, archivos Caddy, memoria, swap, disco y eventos OOM tras cada fase propia. No reiniciar servicios ajenos.

## Readiness de PostgreSQL y diagnóstico de restauración

El séptimo candidato `bda944d` pasó raíz 193/193, prefijo 309/309 y los 17 registros G7, pero su ensayo productivo adicional falló en pg_restore. No autoriza despliegue; su stderr no se retuvo y no se afirma una causa demostrada. La inicialización de la imagen oficial PostgreSQL ejecuta un servidor temporal que solo acepta sockets Unix; `pg_isready` sin host puede aceptarlo antes del servidor definitivo. Además, pg_isready no acredita por sí solo que exista la base solicitada.

El octavo candidato exige TCP `127.0.0.1` con timeout de un segundo, seguido de `SELECT 1` en la base exacta por `/var/run/postgresql`, sin contraseña en argumentos, con `psql -X -w`, `ON_ERROR_STOP`, `PGCONNECT_TIMEOUT=2`, statement_timeout de un segundo y `timeout 2`. Deben coincidir salida exacta `1` y código cero. Se conservan las 120 iteraciones y sleep de un segundo, y healthcheck 10 segundos/timeout 3 segundos/20 reintentos. El presupuesto máximo previo de la espera era 480 segundos, no 120 segundos totales. pg_restore se ejecuta una vez después de readiness.

El ensayo aislado externo `37531553112` pasa con la imagen PostgreSQL fijada: copia su entrypoint real (SHA256 `9c440299ae04a0a79d55b8bf03307036d890a40979d2fb698073c9050d4b20a5`), reproduce socket temporal/TCP definitivo/consulta SQL, confirma soporte de timeout y limpia sus cuatro recursos propios. Guarda solo booleanos, enums y hashes; no constituye certificación de Cuaderno. En la CI siguiente, solo el primer RuntimeError de la operación pg_restore puede añadir `restore_error_category` de una lista fija al diagnóstico. No retiene stderr, SQL, argumentos, entorno ni secretos; fallos desconocidos siguen siendo `other`. No cambia transporte, retries ni resultado del gate.

## Actualización, rollback y reboot

Antes de actualizar: copia verificada, ensayo de migración aislado y registro del
ImageID anterior. Si el esquema es compatible puede restaurarse la imagen previa
después del ensayo. Si no lo es, rollback exige restaurar conjuntamente BD+media
y configuración del backup anterior, en recursos nuevos, antes de promoverlos.
Cambiar únicamente un tag no revierte la BD. No ejecutar downgrade sobre el esquema
vivo, `down -v`, prune ni limpieza global.

La persistencia depende de volúmenes propios y `restart: unless-stopped`, Docker
habilitado y Caddy existente. Verificar configuración y estado enabled, sin
reiniciar el VPS para probar. El reboot diario de las 08:30 Europe/Madrid ya existe
y debe conservarse. Ante presión de memoria/OOM/latencias ajenas, detener solo
Cuaderno y conservar datos/config/evidencias para diagnóstico.
