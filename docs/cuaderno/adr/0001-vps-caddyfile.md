# ADR 0001 — El VPS publica Cuaderno con su Caddyfile

Estado: aceptado. Fecha: 2026-09-28.

## Contexto
El VPS donde se desplegará la aplicación ya usa un Caddyfile. Tandoor 2.6.15 trae nginx embebido que escucha en el puerto 80 del contenedor y habla con gunicorn por socket Unix. Django confía en `X-Forwarded-Proto` mediante `SECURE_PROXY_SSL_HEADER`.

## Decisión
El Caddy del VPS es el único proxy TLS público. El bloque del sitio vive en `docs/install/caddy/Caddyfile` y se importa en ese Caddyfile existente. Compose publica la app solo en `127.0.0.1:8080`. PostgreSQL no se publica. No se añade un contenedor Caddy, Traefik ni otro listener en 80/443.

El nginx embebido se conserva: es el servidor de la imagen del pin, no el borde TLS. `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS=https://<dominio>` salen del dominio real, que todavía no está fijado en el repo. `ALLAUTH_TRUSTED_PROXY_COUNT` queda en 1 (Caddy escribe el cliente y nginx añade un salto).

## Consecuencias
El despliegue externo sigue sin hacerse: faltan dominio, DNS y autorización de acceso al VPS. El perfil local de G0 no pasa por Caddy. Un dominio o un puerto distintos se cambian en el Caddyfile del VPS y en esas variables, sin otro proxy.
