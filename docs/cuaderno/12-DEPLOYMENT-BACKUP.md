# Entorno, despliegue y recuperación

## Desarrollo Windows
Bootstrap requiere Git y Python >=3.11 (el usuario tiene Python en Windows). App: preferir devcontainer/Compose Linux para respetar Python 3.13 y dependencias de Tandoor; Node y compilación frontend en entorno aislado compatible con Vite fijado. No reinstalar Python del sistema ni forzar requirements sobre el host. Codex puede editar desde Windows.
El propietario habilita Docker/virtualización o usa un Linux de desarrollo; no instalar servicios del SO sin permiso. No es necesario borrar Windows, usar GPU ni levantar Flutter/PHP.

## Pasos técnicos a implementar por Codex
1. Reproducir devcontainer/Compose oficial del pin, sin credenciales reales.
2. Documentar comando único de entorno y arranque local que realmente haya ejecutado; documentarlo como `local:up` o script equivalente según las herramientas del pin. Si se añade al registry, usar un comando que arranque servicios desacoplados y termine; no un servidor bloqueante sin límite.
3. Seed sintético y admin local generado/solicitado de forma segura, nunca default en prod.
4. Build personalizado desde el fork, no imagen upstream sin nuestras modificaciones.
5. Health/readiness con DB/migraciones, sin exponer secretos ni depender de servicio remoto.
6. Profile prod probado localmente con datos demo. En el VPS, TLS y dominio los sirve el Caddyfile ya instalado: importar `docs/install/caddy/Caddyfile`, publicar la app solo en `127.0.0.1:8080` y definir `ALLOWED_HOSTS` más `CSRF_TRUSTED_ORIGINS=https://<dominio>`. Secretos fuera de Git. No levantar un segundo proxy.
7. README de operación, backup, restore, actualización/rollback e importación.

## Datos persistentes
Volumen PostgreSQL persistente y mediafiles privados; config no secreta versionada, `.env` real fuera de Git. Exponer DB solo en red interna. Proxy limita upload y timeout acordados. Proceso sin privilegios innecesarios según soporte del pin. No afirmar rootless hasta medirlo.

## Copias de seguridad
Dump PostgreSQL consistente + manifiesto y hashes de media + versión app/migraciones/config no sensible. Para snapshot conjunto DB/media: pausar escrituras o mecanismo coherente documentado, no copiar carpetas activas sin consistencia. Cifrado para copias externas y credenciales separadas.
Retención propuesta, a acordar con espacio real: 7 diarias y 4 semanales; almacenar una copia fuera de la máquina principal cuando se configure destino autorizado. No se afirma que esté contratada o activa.
Restaurar en BD y directorio NUEVOS, verificar conteos, hashes, permisos, costes golden y saldo. RPO/RTO solo después de prueba; guardar duración/resultado. No restore sobre prod en tests.

## Actualización
Congelar pin/digest, backup verificado, rama ensayo, migración, smoke y pruebas. Rollback debe contemplar compatibilidad de esquema; si migración irreversible, restauración completa ensayada. No hacer downgrade binario sobre esquema incompatible.

## Límites de autorización
Preparar y probar despliegue local: sí. Conectar al VPS del usuario, publicar DNS, enviar email real, cargar recetas del cliente o activar dominio de producción: requiere datos y autorización específicos. Que esto quede pendiente no impide completar y verificar la aplicación local.
