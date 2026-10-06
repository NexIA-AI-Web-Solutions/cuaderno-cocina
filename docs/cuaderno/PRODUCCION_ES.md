# Cuaderno Cocina: preparación de producción

El código se mantiene en la rama `cuaderno/main` de `NexIA-AI-Web-Solutions/cuaderno-cocina`. Es un único producto Tandoor/Django/DRF/Vue/Vuetify/PostgreSQL; no hay que instalar los donantes.

**Estado de esta entrega:** el resultado local vigente se determina mediante los 17 registros del candidato en `.cuaderno-runs/release-manifest.json` y `.cuaderno-runs/RELEASE_REPORT.md`, según [RELEASE_CHECKLIST](RELEASE_CHECKLIST.md). Los resultados históricos no sustituyen ese manifiesto. No se ha desplegado este procedimiento en un VPS; las instrucciones productivas son una preparación para el operador y requieren validación en su destino antes de admitir datos reales.

## Uso local comprobado

La parada del 1 de octubre se conserva como evidencia histórica. El propietario autorizó el 4 de octubre continuar la implementación y los ensayos locales. El procedimiento siguiente construye un preview propio; no apunta a producción.

Desde la raíz del checkout, con Docker Desktop disponible:

```powershell
$env:CUADERNO_ENV='local'
python scripts/cuaderno/local_up.py
$env:CUADERNO_DEMO_PASSWORD='Demo-Cocina-2026!'
docker exec -e CUADERNO_ENV=local -e CUADERNO_DEMO_PASSWORD cuaderno-release-web /opt/recipes/venv/bin/python manage.py seed_cuaderno_demo
python scripts/cuaderno/check.py release-http --allow-isolated-mutations
```

Abre http://127.0.0.1:18081. Cuentas **solo DEMO**: `demo-esencial`, `demo-profesional`, `demo-integral`; contraseña `Demo-Cocina-2026!`. Cada cuenta usa un Space independiente. El seed está restringido al entorno local; no ejecutarlo en producción. Uso de costes, menús, compras, preparación y reversión en [MANUAL_ES](MANUAL_ES.md).

El build puede reutilizar stages cacheados y tarda varios minutos. No editar el checkout ni crear commits durante el build: su identidad incluye HEAD y el hash de los archivos locales. Los precios 500+17, 1000+20 y 1500+30 son metadata comercial, no una pasarela de cobro.

## Herramientas de aceptación local

El gate E2E utiliza Node **24.21.0** y la instalación local de Playwright fijada en `tests/cuaderno/e2e/package-lock.json`; no descarga un runner alternativo mediante npx. Instala esa versión de Node en PATH o define `CUADERNO_E2E_NODE` como ruta absoluta a su ejecutable. En Windows también se verifica el SHA256 oficial de `win-x64/node.exe` (`ba4e6d110e8c1592a1ecd390f6b05f3da124b13871a5be62b341a07a853c6c32`), publicado en [checksums de Node 24.21.0](https://nodejs.org/dist/v24.21.0/SHASUMS256.txt). Un Node distinto detiene la aceptación.

`candidate_check.py e2e-final --context <contexto>` proporciona la imagen esperada. El wrapper comprueba imagen, salud y binding exclusivo `127.0.0.1:18081` antes y después del navegador, fuerza cero retries y crea artefactos en un directorio nuevo de `.cuaderno-runs`. La aceptación requiere las cuentas y fixtures sintéticos; ningún dato real participa.

El typecheck utiliza la fuente y todas las dependencias de la etapa Linux `frontend` construida desde el checkout con `yarn.lock` congelado. Se ejecuta contra su Image ID inmutable, sin red y con filesystem de solo lectura; las dependencias mutables del host no sirven para acreditar el resultado.

## Preparación del servidor, solo cuando se autorice el despliegue

Necesita Linux con Docker/Compose, espacio para PostgreSQL/media/copias y un dominio con HTTPS. Usar el Caddy que ya sirve el VPS: [fragmento Caddy](../install/caddy/Caddyfile). No arrancar un segundo proxy. El servicio web debe publicar **solo `127.0.0.1:18081:80`**; PostgreSQL no publica puertos. No reutilizar nombres, redes ni volúmenes `cuaderno-release` de la demo.

1. Obtener la rama y fijar un commit revisado, sin modificaciones locales. Construir con `deploy/cuaderno/Dockerfile`, no con el Dockerfile upstream ni una imagen Tandoor sin nuestros módulos. En un checkout limpio de Linux:

```bash
commit=$(git rev-parse HEAD)
source_hash=$(python3 -c 'from scripts.cuaderno.delivery_backup import source_manifest; print(source_manifest()["sha256"])')
python scripts/cuaderno/build_runtime_security_apks.py --output .cuaderno-runs/runtime-security-production
docker build -f deploy/cuaderno/Dockerfile --build-context runtime_security=.cuaderno-runs/runtime-security-production --build-arg "SOURCE_COMMIT=$commit+worktree.$source_hash" -t "cuaderno-cocina:release-$commit" .
docker image inspect "cuaderno-cocina:release-$commit" --format '{{.Id}}'
```

2. Conservar el Image ID resultante y el commit; configurar `CUADERNO_IMAGE=sha256:<ID>` en el fichero de entorno del servidor. Un Image ID local no es un digest de registro: no escribirlo como `repositorio@sha256:...`. No se ha publicado una imagen Docker. Si se construye en otro equipo, transferir un `docker image save` y verificar su SHA-256 antes de `docker image load`.

3. Guardar secretos fuera de Git, por ejemplo `/etc/cuaderno/production.env`, con permisos `0600`. Generar valores nuevos y largos para `CUADERNO_SECRET_KEY` y `CUADERNO_DB_PASSWORD`; no usar contraseñas DEMO ni copiar `data/cuaderno/local/compose.env`. Definir también `CUADERNO_DOMAIN=recetas.ejemplo.es`, sin esquema ni ruta.

4. Utilizar el perfil **incluido en la imagen**, [recipes/cuaderno_production_settings.py](../../recipes/cuaderno_production_settings.py). Exige secreto propio de al menos 50 caracteres, hosts explícitos y orígenes CSRF HTTPS; activa cookies Secure/HttpOnly, redirección HTTPS y nosniff, cierra el registro y la IA, y prohíbe reconstruir plugins al arrancar. No montar un módulo alternativo sobre este archivo: sus bytes forman parte del manifiesto verificado de la release.

5. Utilizar directamente [deploy/cuaderno/compose.production.yml](../../deploy/cuaderno/compose.production.yml), con proyecto `cuaderno-prod`. Esta configuración fija PostgreSQL, almacena datos y media en volúmenes propios, inicializa media para UID/GID 10001, publica la web solo en loopback y mantiene la BD sin puertos. Incluye reinicio, rotación de logs, límites de memoria/PIDs y tiempo de parada. El proceso supervisor detiene el contenedor si sale nginx o Gunicorn, permitiendo que la política de reinicio actúe. El healthcheck comprueba nginx → Django → PostgreSQL y migraciones pendientes.

El proxy HTTPS del host debe sobrescribir `X-Forwarded-Proto`; nginx lo transmite a Django y el perfil confía en ese encabezado dentro de esta topología con puerto privado. No publicar directamente el listener interno. Caddy y Compose deben usar el mismo dominio y el contador de proxies debe corresponder a los saltos reales.

6. Validar sin imprimir secretos. El primer arranque aplica migraciones; hacerlo inicialmente con una BD nueva, nunca como ensayo contra la base real de un cliente:

```bash
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno/production.env -f deploy/cuaderno/compose.production.yml config --quiet
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno/production.env -f deploy/cuaderno/compose.production.yml up -d --wait --wait-timeout 600
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno/production.env -f deploy/cuaderno/compose.production.yml exec web /opt/recipes/venv/bin/python manage.py createsuperuser
```

Crear el administrador interactivamente, sin credenciales por defecto. Importar el fragmento Caddy en su configuración existente y validar/recargar con el procedimiento del operador. Su variable `CUADERNO_DOMAIN` debe configurarse en el servicio de Caddy, o reemplazarse por el dominio concreto: el `.env` de Compose no se aplica automáticamente a Caddy. Comprobar HTTPS, login/logout, CSRF, cookies Secure, dirección real del cliente, media privada, dos Spaces, exportación y readiness. El contador de proxies debe ajustarse a los saltos realmente comprobados; no asumir que el ejemplo sirve para cualquier topología.

El fragmento limita el cuerpo a 54 525 952 bytes, exactamente 52 MiB como el nginx embebido; se dejan los 2 MiB adicionales al límite nativo agregado de 50 MiB para el multipart. Así no se confunden MB decimales y MiB ni se reduce el límite útil nativo. No subir un solo límite suponiendo que cambian los demás. La [directiva oficial Caddy](https://caddyserver.com/docs/caddyfile/directives/request_body) admite tamaños en bytes. Los 300 s del transporte Caddy no garantizan operaciones de esa duración: el timeout de worker Gunicorn se mantiene explícitamente en 30 s y su comportamiento depende de la clase de worker. Medir importaciones/exportaciones y ajustar la cadena completa antes de cambiarlo. `2 workers × 2 threads` es un punto inicial, **no dimensionamiento certificado**: el gate concurrente sigue rojo. Activar HSTS solo después de comprobar HTTPS y dominio reales, valorando previamente subdominios y recuperación.

## Copias, actualización y recuperación

La copia debe incluir dump PostgreSQL consistente, media, hashes, Image ID, commit, versión de migraciones y configuración no secreta. Pausar **todos** los escritores durante el snapshot conjunto, con ventana comunicada, y reanudarlos incluso si falla la copia. No copiar media activa suponiendo coherencia. Guardar secretos por separado y cifrar copias externas; retención y destino externo aún no están configurados.

Para el proyecto productivo versionado existen dos herramientas separadas:

```bash
python3 scripts/cuaderno/production_backup.py --env-file /etc/cuaderno/production.env --destination-parent /var/backups/cuaderno
python3 scripts/cuaderno/production_restore_verify.py /var/backups/cuaderno/BUNDLE --runtime-image sha256:IMAGE_ID
```

`production_backup.py` valida el archivo privado y destino, identifica únicamente `cuaderno-prod`, detiene su escritor web, rechaza clientes externos de BD, obtiene dump/media y hashes/conteos/secuencias, y reanuda la web en `finally`. No imprime secretos. Con `--include-env` guarda además una copia privada 0600 de la configuración, cuya transferencia exige cifrado. Cada ejecución crea un bundle nuevo. `production_restore_verify.py` verifica el bundle antes de actuar y restaura en red, BD y media nuevos, sin puertos publicados; con `--runtime-image` exige readiness de esa imagen exacta. Detiene únicamente los contenedores aislados verificados y conserva volúmenes e informe para revisión y nunca promueve ni sustituye `cuaderno-prod`.

Las [unidades de backup](../../deploy/cuaderno/backup/README.md) son ejemplos para systemd; el operador debe revisar usuario, rutas, privilegios Docker y ventana antes de activarlas. La retención y copia cifrada remota requieren un destino y política elegidos por el operador. No se configura un proveedor externo ni se activa un temporizador automáticamente.

Los scripts `delivery_backup.py`, `delivery_restore.py`, `delivery_rollback.py` y `upgrade_smoke.py` siguen restringidos a entornos sintéticos locales. No retirar sus guardas ni usarlos contra datos reales. La activación productiva y el rollback requieren una decisión del operador después de validar un destino restaurado; no ejecutar un binario antiguo sobre un esquema nuevo incompatible.

Antes de actualizar: congelar imagen y checkout, obtener una copia verificada, ensayar migración sobre un destino nuevo y revisar cambios de esquema. Si hay migraciones incompatibles, la vuelta atrás requiere restauración completa; no poner un binario antiguo sobre el esquema nuevo. No usar `down -v`, `docker system prune` ni borrar volúmenes para actualizar.

## Evidencia y límites

La identidad del preview, resultados reales y ensayos de recuperación están en [STATUS](STATUS.md) y [evidencia](evidence/2026-09-30-continuacion.md). [RESUME](RESUME.md) permite retomar los checks abiertos. No se certifican iPad físico, migración de datos del cliente, SMTP real ni VPS. El formato del programa antiguo bloquea únicamente su extractor: el importador genérico sigue disponible.
