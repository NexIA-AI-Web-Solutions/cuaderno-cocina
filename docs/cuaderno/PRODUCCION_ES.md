# Cuaderno Cocina: preparación de producción

El código se mantiene en la rama `cuaderno/main` de `NexIA-AI-Web-Solutions/cuaderno-cocina`. Es un único producto Tandoor/Django/DRF/Vue/Vuetify/PostgreSQL; no hay que instalar los donantes.

**Estado de esta entrega:** el build y los ensayos locales están comprobados; G7 sigue abierto. No se ha desplegado este procedimiento en un VPS. Antes de admitir datos reales deben cerrarse los pendientes de [RELEASE_CHECKLIST](RELEASE_CHECKLIST.md): rendimiento, navegador, regresión final y auditoría de imagen. Las instrucciones siguientes son una preparación para el operador, no un despliegue certificado.

## Uso local comprobado

Desde la raíz del checkout, con Docker Desktop disponible:

```powershell
$env:CUADERNO_ENV='local'
python scripts/cuaderno/check.py local-up --allow-isolated-mutations
$env:CUADERNO_DEMO_PASSWORD='Demo-Cocina-2026!'
docker exec -e CUADERNO_ENV=local -e CUADERNO_DEMO_PASSWORD cuaderno-release-web /opt/recipes/venv/bin/python manage.py seed_cuaderno_demo
python scripts/cuaderno/check.py release-http --allow-isolated-mutations
```

Abre http://127.0.0.1:18081. Cuentas **solo DEMO**: `demo-esencial`, `demo-profesional`, `demo-integral`; contraseña `Demo-Cocina-2026!`. Cada cuenta usa un Space independiente. El seed está restringido al entorno local; no ejecutarlo en producción. Uso de costes, menús, compras, preparación y reversión en [MANUAL_ES](MANUAL_ES.md).

El build puede reutilizar stages cacheados y tarda varios minutos. No editar el checkout ni crear commits durante el build: su identidad incluye HEAD y el hash de los archivos locales. Los precios 500+17, 1000+20 y 1500+30 son metadata comercial, no una pasarela de cobro.

## Preparación del servidor, solo cuando se autorice el despliegue

Necesita Linux con Docker/Compose, espacio para PostgreSQL/media/copias y un dominio con HTTPS. Usar el Caddy que ya sirve el VPS: [fragmento Caddy](../install/caddy/Caddyfile). No arrancar un segundo proxy. El servicio web debe publicar **solo `127.0.0.1:8080:80`**; PostgreSQL no publica puertos. No reutilizar nombres, redes ni volúmenes `cuaderno-release` de la demo.

1. Obtener la rama y fijar un commit revisado, sin modificaciones locales. Construir con `deploy/cuaderno/Dockerfile`, no con el Dockerfile upstream ni una imagen Tandoor sin nuestros módulos. En un checkout limpio de Linux:

```bash
commit=$(git rev-parse HEAD)
source_hash=$(python3 -c 'from scripts.cuaderno.delivery_backup import source_manifest; print(source_manifest()["sha256"])')
docker build -f deploy/cuaderno/Dockerfile --build-arg "SOURCE_COMMIT=$commit+worktree.$source_hash" -t "cuaderno-cocina:release-$commit" .
docker image inspect "cuaderno-cocina:release-$commit" --format '{{.Id}}'
```

2. Conservar el Image ID resultante y el commit; configurar `CUADERNO_IMAGE=sha256:<ID>` en el fichero de entorno del servidor. Un Image ID local no es un digest de registro: no escribirlo como `repositorio@sha256:...`. No se ha publicado una imagen Docker. Si se construye en otro equipo, transferir un `docker image save` y verificar su SHA-256 antes de `docker image load`.

3. Guardar secretos fuera de Git, por ejemplo `/etc/cuaderno/production.env`, con permisos `0600`. Generar valores nuevos y largos para `CUADERNO_SECRET_KEY` y `CUADERNO_DB_PASSWORD`; no usar contraseñas DEMO ni copiar `data/cuaderno/local/compose.env`. Definir también `CUADERNO_DOMAIN=recetas.ejemplo.es`, sin esquema ni ruta.

4. Preparar `/etc/cuaderno/production_settings.py`. El pin reconoce el proxy HTTPS, pero no expone variables de entorno para `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`: poner esos nombres en el `.env` no basta. Este módulo separado debe montarse en solo lectura; no modifica el núcleo Tandoor:

```python
from recipes.settings import *
from django.core.exceptions import ImproperlyConfigured

if DEBUG or SECRET_KEY == 'INSECURE_STANDARD_KEY_SET_IN_ENV' or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Producción exige DEBUG=0 y SECRET_KEY propia de al menos 50 caracteres.')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
ENABLE_SIGNUP = False
SPACE_AI_ENABLED = False
```

5. Preparar `/etc/cuaderno/compose.yml` con este ejemplo. **Ejemplo operativo no arrancado aquí**; validar en el servidor antes de usarlo. Solo usa los servicios propios y el PostgreSQL fijado:

```yaml
services:
  db:
    image: postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
    environment:
      POSTGRES_DB: cuaderno_prod
      POSTGRES_USER: cuaderno_prod
      POSTGRES_PASSWORD: ${CUADERNO_DB_PASSWORD:?secreto requerido}
    volumes:
      - database:/var/lib/postgresql/data
    healthcheck:
      test: [CMD-SHELL, pg_isready -U cuaderno_prod -d cuaderno_prod]
      interval: 5s
      timeout: 3s
      retries: 20
  web:
    image: ${CUADERNO_IMAGE:?Image ID local requerido}
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "127.0.0.1:8080:80"
    environment:
      DJANGO_SETTINGS_MODULE: recipes.cuaderno_production_settings
      SECRET_KEY: ${CUADERNO_SECRET_KEY:?secreto requerido}
      DB_ENGINE: django.db.backends.postgresql
      DB_OPTIONS: "{'options': '-c jit=off'}"
      POSTGRES_HOST: db
      POSTGRES_PORT: "5432"
      POSTGRES_DB: cuaderno_prod
      POSTGRES_USER: cuaderno_prod
      POSTGRES_PASSWORD: ${CUADERNO_DB_PASSWORD:?secreto requerido}
      ALLOWED_HOSTS: 127.0.0.1,localhost,${CUADERNO_DOMAIN:?dominio requerido}
      CSRF_TRUSTED_ORIGINS: https://${CUADERNO_DOMAIN:?dominio requerido}
      ALLAUTH_TRUSTED_PROXY_COUNT: "1"
      TZ: Europe/Madrid
      CUADERNO_LANGUAGE: es
      SPACE_AI_ENABLED: "0"
      SPACE_DEFAULT_ALLOW_SHARING: "0"
      ENABLE_SIGNUP: "0"
      DEBUG: "0"
      GUNICORN_MEDIA: "0"
      GUNICORN_WORKERS: "2"
      GUNICORN_THREADS: "2"
      GUNICORN_TIMEOUT: "30"
    volumes:
      - media:/opt/recipes/mediafiles
      - type: bind
        source: /etc/cuaderno/production_settings.py
        target: /opt/recipes/recipes/cuaderno_production_settings.py
        read_only: true
        bind:
          create_host_path: false
    healthcheck:
      test: [CMD, /opt/recipes/venv/bin/python, -c, "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1/health/ready/', timeout=5))['ready'] is True"]
      interval: 10s
      timeout: 8s
      start_period: 180s
      retries: 60
volumes:
  database:
  media:
```

6. Validar sin imprimir secretos. El primer arranque aplica migraciones; hacerlo inicialmente con una BD nueva, nunca como ensayo contra la base real de un cliente:

```bash
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno/production.env -f /etc/cuaderno/compose.yml config --quiet
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno/production.env -f /etc/cuaderno/compose.yml up -d --wait --wait-timeout 600
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno/production.env -f /etc/cuaderno/compose.yml exec web /opt/recipes/venv/bin/python manage.py createsuperuser
```

Crear el administrador interactivamente, sin credenciales por defecto. Importar el fragmento Caddy en su configuración existente y validar/recargar con el procedimiento del operador. Su variable `CUADERNO_DOMAIN` debe configurarse en el servicio de Caddy, o reemplazarse por el dominio concreto: el `.env` de Compose no se aplica automáticamente a Caddy. Comprobar HTTPS, login/logout, CSRF, cookies Secure, dirección real del cliente, media privada, dos Spaces, exportación y readiness. El contador de proxies debe ajustarse a los saltos realmente comprobados; no asumir que el ejemplo sirve para cualquier topología.

El fragmento limita el cuerpo a 54 525 952 bytes, exactamente 52 MiB como el nginx embebido; se dejan los 2 MiB adicionales al límite nativo agregado de 50 MiB para el multipart. Así no se confunden MB decimales y MiB ni se reduce el límite útil nativo. No subir un solo límite suponiendo que cambian los demás. La [directiva oficial Caddy](https://caddyserver.com/docs/caddyfile/directives/request_body) admite tamaños en bytes. Los 300 s del transporte Caddy no garantizan operaciones de esa duración: el timeout de worker Gunicorn se mantiene explícitamente en 30 s y su comportamiento depende de la clase de worker. Medir importaciones/exportaciones y ajustar la cadena completa antes de cambiarlo. `2 workers × 2 threads` es un punto inicial, **no dimensionamiento certificado**: el gate concurrente sigue rojo. Activar HSTS solo después de comprobar HTTPS y dominio reales, valorando previamente subdominios y recuperación.

## Copias, actualización y recuperación

La copia debe incluir dump PostgreSQL consistente, media, hashes, Image ID, commit, versión de migraciones y configuración no secreta. Pausar **todos** los escritores durante el snapshot conjunto, con ventana comunicada, y reanudarlos incluso si falla la copia. No copiar media activa suponiendo coherencia. Guardar secretos por separado y cifrar copias externas; retención y destino externo aún no están configurados.

Los scripts `delivery_backup.py`, `delivery_restore.py`, `delivery_rollback.py` y `upgrade_smoke.py` están restringidos a entornos sintéticos locales. **No quitar sus guardas ni apuntarlos a producción.** El procedimiento productivo de copia/restauración debe prepararse y ensayarse para sus nombres y credenciales propios: restaurar a BD y media NUEVAS, comparar hashes/conteos/secuencias/permisos/costes/saldos y solo entonces decidir la activación. No hay rollback productivo automático configurado.

Antes de actualizar: congelar imagen y checkout, obtener una copia verificada, ensayar migración sobre un destino nuevo y revisar cambios de esquema. Si hay migraciones incompatibles, la vuelta atrás requiere restauración completa; no poner un binario antiguo sobre el esquema nuevo. No usar `down -v`, `docker system prune` ni borrar volúmenes para actualizar.

## Evidencia y límites

La identidad del preview, resultados reales y ensayos de recuperación están en [STATUS](STATUS.md) y [evidencia](evidence/2026-09-30-continuacion.md). [RESUME](RESUME.md) permite retomar los checks abiertos. No se certifican iPad físico, migración de datos del cliente, SMTP real ni VPS. El formato del programa antiguo bloquea únicamente su extractor: el importador genérico sigue disponible.
