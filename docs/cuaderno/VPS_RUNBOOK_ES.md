# Operación de Cuaderno en el VPS compartido

Destino autorizado: `https://gex-dashboard.hopto.org/cuaderno-cocina/`. Esta guía
describe el procedimiento; STATUS y RELEASE_CHECKLIST registran cuáles de estos
pasos se han ejecutado realmente. No constituye un informe PASS.

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

El ImageID de Docker no es un tag ni necesariamente el digest de configuración:
Docker 29 con containerd puede identificar el manifiesto OCI. Antes de cargar,
verificar SHA256 del archivo, config digest del archivo, identidad de fuentes,
SBOM y procedencia. Después de cargar, verificar que el manifiesto local enlaza a
esa misma configuración. Registrar ambos identificadores cuando difieran; no
atribuir a otra imagen las pruebas de CI.

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
docker compose --project-name cuaderno-prod --env-file /etc/cuaderno-cocina/production.env -f deploy/cuaderno/compose.production.yml up -d --wait --wait-timeout 600
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

Playwright remoto debe usar cuentas sintéticas propias y destino explícito,
verificando login/logout, cookies/path, CSRF, assets/API/media, manifesto, worker,
roles, responsive, impresión y recargas. No instalar navegadores/build tools en
este VPS. No cambiar las guardas loopback del harness CI para apuntarlo a datos
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

Activar un timer propio solo después del primer backup/restauración. El servicio
debe usar estas rutas efectivas, `--include-env`, UMask=0077 y OnFailure para una
alarma local visible en journal. Retención máxima propuesta: siete bundles
cerrados; borrar únicamente bundles propios verificados, nunca datos activos.
No enviar correo ni activar servicios externos automáticamente.

La ubicación indicada está en este mismo VPS. **No hay copia externa configurada**.
No afirmar protección frente a pérdida del servidor. Una futura transferencia
requiere destino autorizado, cifrado antes de salir y comprobación de recepción.

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
