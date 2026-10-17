# Corrección visual de Cuaderno Cocina · 2026-10-17

Solicitud: revisar y arreglar la web productiva con varios agentes y sesiones de navegador en los tres planes. Rama `fix/ui-visual-20261017`; fuente base `d6ee958` (backend productivo `617bb7b` más documentación).

## Correcciones verificadas

- Buscador inicial: etiqueta externa asociada al input, estable durante foco/escritura/borrado; búsqueda global sin placeholder duplicado.
- Recetas: coste detrás de ingredientes/pasos, antes de metadatos; extras y cálculo avanzado desplegables mediante teclado, conservados en impresión.
- Compras: barra flexible sin selector ni acciones recortados en 360/390 px.
- Subtítulos de tarjetas: instrucciones completas en varias líneas; títulos de diálogos ajustables y cierre con nombre accesible.
- Reservas: se elimina la fila vacía cuyo margen negativo solapaba el estado vacío; historial con contraste legible.
- Almacén: cantidades exactas sin ceros decimales sobrantes, notas completas y contraste del historial; formulario manual sin estiramiento artificial.
- Trabajadores: contexto extenso desplegable, avisos y propuestas visibles; traducción de campos/estados observados.

## Evidencia

Tres agentes reales con sesiones Chromium separadas: recetas/Esencial, módulos/Profesional y auditoría independiente/Integral. Producción explorada sin guardar datos de negocio. Candidato validado interceptando exclusivamente navegación/estáticos y manteniendo API real; no equivale por sí solo a despliegue.

Viewports: 390×844, 768×1024, 1024×768, 1440×900; auditoría adicional de 360 px. Recetas: Enter/Espacio, impresión y límites de controles; Reservas: estados vacío/poblado, historial y editor; auditoría: inicio vacío/foco/texto/borrado, compras, almacén, trabajadores, despensa y opciones. No es una certificación exhaustiva de todos los flujos.

- Vite build: exit 0.
- Vue typecheck completo: exit 0.
- Regresión focalizada: 111/111; después de ajustes finales, 26/26 de reservas/formato decimal.
- Test rojo/verde de cantidades: reproduce falta de formateador; verifica precisión superior a Number.MAX_SAFE_INTEGER y fracción mínima sin redondeo.
- Revisión independiente: SHIP después de corregir contraste del historial de almacén.
- `git diff --check`: limpio.

Evidencia extensa local (capturas y logs): `/home/kripta/cuaderno-ui-evidence-20261017/`. Los estados de autenticación permanecen fuera de Git y no se publican. Ninguna contraseña se incluye en este informe.

Comandos reproducibles desde la raíz:

```sh
/opt/jaautomation/runtime/node-v24.19.0/bin/node --test vue3/src/cuaderno/stockMovementUi.test.mjs vue3/src/cuaderno/reservationsPage.test.mjs
cd vue3
/opt/jaautomation/runtime/node-v24.19.0/bin/node node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.app.json --pretty false
/opt/jaautomation/runtime/node-v24.19.0/bin/node node_modules/vite/bin/vite.js build
```

## Entrega y límites

Imagen derivada del runtime productivo exacto, sólo añade activos Vue y collectstatic. Sin cambios de modelos, migraciones, Caddy ni permisos. Copia de configuración y dump PostgreSQL: `/var/backups/cuaderno-cocina/ui-20261017` (acceso restringido). Aceptación pública completada en los tres planes: `deployment.json` y `public-checks.json`. Sólo se recreó web; servicio sano, cero reinicios, manifest público idéntico al candidato. El navegador bloqueó los tres registros automáticos de visita a receta para evitar escrituras durante esta comprobación.

Sólo Chromium emulado: Firefox/WebKit e iPad físico no comprobados. No se realizaron escrituras/persistencia de datos productivos para probar cambios de presentación.


Recuperación de interfaz (no restaura ni modifica datos): cambiar sólo `CUADERNO_IMAGE` por `cuaderno-workers:20261011-617bb7b` en `/etc/cuaderno-cocina/production.env` y ejecutar el mismo Compose productivo con `up -d --no-deps --pull never web`. La imagen anterior permanece disponible. No restaurar la BD para una reversión de estos estáticos.
