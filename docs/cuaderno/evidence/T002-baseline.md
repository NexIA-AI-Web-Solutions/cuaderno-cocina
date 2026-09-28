# T002 — Tandoor del pin arrancado en local

Fecha: 2026-09-28.

## Resultado

Imagen construida del checkout `f77a459f` (pin `7e1c427a`, tag `2.6.15`), etiqueta `cuaderno-g0-t002-app:f77a459f` (`sha256:68946d4df135…`). PostgreSQL `16.15` (`postgres:16-alpine`, digest `sha256:721873c34ceb…`) en el volumen `cuaderno-g0-t002-db`. Web en `127.0.0.1:18080`.

El primer `docker run` falló porque el checkout Windows tenía CRLF y el Dockerfile creó el enlace `http.d\r` en vez de sustituir el `http.d` de nginx. El arranque usable corrige eso dentro del contenedor, sin parchear el repositorio: `sed` de `*.sh`/`*.template` y `ln -sfn /opt/recipes/http.d /etc/nginx/http.d`. Vue se compiló con Node `v24.18.1` de la imagen (`yarn build`); el manifiesto quedó en `cookbook/static/vue3`.

## Comprobado

- `GET /setup/` → 200, título Cookbook Setup.
- Alta del usuario `demo` (superusuario) por el formulario nativo. Contraseña local `Demo-Cocina-2026!`.
- `POST /api/recipe/` → 201, receta `Caldo demo G0`, id 1, 4 raciones iniciales.
- Reapertura `GET /api/recipe/1/` → 200.
- PostgreSQL: fila en `cookbook_recipe`, `auth_user` y `cookbook_space` (`demo's Space`).

## Sigue activo

`cuaderno-g0-t002-db`, red `cuaderno-g0-t002-pub`, contenedor `cuaderno-g0-t002-web`. No se ha hecho `docker compose down -v`.
