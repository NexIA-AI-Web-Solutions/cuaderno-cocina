# 11 · Windows, Linux, despliegue y copias

## Desarrollo

Windows 11 + Node 24 LTS + Git + gestor de paquetes congelado. Código independiente del sistema de archivos; construir rutas con API de Node. Native addons (SQLite/sharp) se instalan por plataforma: no copiar node_modules de Windows al VPS Linux. Probar Windows y Linux en CI.

Docker no es obligatorio. Se puede incluir un Dockerfile opcional más adelante si hay una necesidad concreta, pero no dos mecanismos de producción sin mantener ambos. La vía principal es servicio Linux con Caddy.

## Directorios de producción

```
/opt/cuaderno-cocina/releases/<id>/      build inmutable
/opt/cuaderno-cocina/current            enlace a release
/etc/cuaderno-cocina/app.env            configuración privada
/var/lib/cuaderno-cocina/site-1/db/
/var/lib/cuaderno-cocina/site-1/media/
/var/backups/cuaderno-cocina/site-1/
```

Usuario de servicio sin login, solo permisos necesarios; app en localhost tras proxy HTTPS. `ORIGIN` configurado con el dominio exacto, cookies seguras y proxy confiable. Migraciones como paso de publicación explícito, no un `push` de esquema destructivo al arrancar.

No escribir un dominio o IP real inventados. Los ejemplos de Caddy/systemd no se habilitan hasta completar los valores y confirmar destino. No tocar configuraciones de J&A u otros proyectos del propietario.

## Pipeline de release

Instalar lockfile → pruebas → build → auditar dependencias → backup previo → migrar copia de prueba → mantenimiento breve si necesario → migración real autorizada → cambiar release → readiness y smoke → cerrar mantenimiento. Si falla, mantener release previa y seguir runbook; el rollback de código no implica que una DB migrada sea reversible.

Migraciones destructivas evitadas mediante expand/contract. Antes de tocar datos reales, disponer de backup verificado y ventana acordada. No vender cero downtime con SQLite de una instancia.

## Backup consistente

No basta copiar `database.sqlite` mientras WAL está activo. Usar la API de backup SQLite del driver probado o snapshot equivalente documentado. Verificar integridad y que no falten transacciones confirmadas.

Media inmutable por hash, primero archivo escrito/renombrado y después referencia DB en transacción. Backup snapshot de la DB; enumerar los media referenciados por ESE snapshot; impedir eliminación física concurrente hasta acabar. Generar manifiesto con schemaVersion, commit, timestamp, hashes y assets. Si se elige mantenimiento para simplificar consistencia, bloquear todas las mutaciones empresariales y demostrarlo; no fingir que basta cerrar una pantalla.

Backups de imagen y DB coherentes; ningún snapshot se marca completo si falta un archivo referenciado. Comprobar SHA-256 y restaurar en carpeta aislada. No incluir cookies reutilizables en exportaciones funcionales; al restaurar un backup técnico, invalidar sesiones como paso de recuperación.

## Retención y copia externa

Propuesta operativa inicial: diario, siete diarios y cuatro semanales, con límites de espacio y alerta de fallo. Objetivo de recuperación de datos de hasta 24 h condicionado a ejecución real del scheduler; no es un SLA firmado. Una copia en el mismo VPS no protege frente a su pérdida: configurar destino externo cifrado con autorización/credenciales del propietario.

Si no hay destino externo todavía, terminar scripts y prueba local y marcar OFFSITE_BACKUP_PENDING. No afirmar protección completa en producción.

## Prueba de restauración obligatoria

1. Crear datos, receta, imagen, cambio de precio, recepción y desperdicio sintéticos.
2. Generar backup.
3. Restaurar a otra carpeta con app detenida para ese destino, no sobre la fuente.
4. Verificar integridad, FK, recuentos, recetas/costes, archivos y saldos.
5. Arrancar una segunda instancia en puerto libre y ejecutar smoke.
6. Registrar duración, hashes y resultados. Limpiar solo temporales creados por ese test.

Repetir antes de release y documentar cómo repetirlo periódicamente. Restaurar no tiene éxito porque exista un ZIP.

## Servicios mensuales y alcance

Las mensualidades 17/20/30 € no cambian la arquitectura ni autorizan soporte ilimitado. Los scripts facilitan hosting, copias y mantenimiento básico; cambios funcionales, carga manual y migración específica son trabajo adicional. No implementar un sistema de cobro de mantenimientos como parte de esta app.
