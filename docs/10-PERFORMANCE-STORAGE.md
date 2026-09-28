# 10 · Rendimiento y almacenamiento medidos

## Objetivo, no publicidad

La queja de lentitud del programa anterior motiva medir la nueva app. No podemos afirmar ser X veces más rápidos sin datos comparables. Los siguientes son presupuestos iniciales de ingeniería; no resultados obtenidos ni garantías contractuales.

## Dataset y entorno

Seed fijo: 2.000 recetas, 5.000 ingredientes, 30.000 líneas; Profesional con DAG hasta profundidad 5; Integral con 100.000 movimientos y recepciones parciales. Separar escenario básico (sin ledger) del completo. Sin fotos en la primera medida; luego fotos optimizadas y medición de red.

Referencia de servidor para reproducir: 2 vCPU, 2 GiB RAM, SSD local; publicar CPU, SO, Node, SQLite, paquete/lock y commit reales. Si solo se prueba en el portátil, etiquetar LOCAL y no equivalerlo a VPS. Medir build de producción, después de calentamiento, al menos 100 operaciones por flujo y p50/p95/error rate.

## Presupuestos de salida

| Medida | Objetivo inicial |
|---|---:|
| Consulta/lista paginada en servidor, p95 | ≤250 ms |
| Búsqueda de ingredientes, p95 | ≤200 ms |
| Cálculo de receta de 30 líneas, p95 | ≤100 ms |
| Guardar receta o cambio de precio normal, p95 | ≤400 ms |
| JS de primera ruta, transferencia gzip | ≤170 KiB |
| CSS inicial gzip | ≤45 KiB |
| LCP en escenario móvil documentado | ≤2,5 s |
| CLS | ≤0,1 |
| Memoria RSS estable de app sin importación, fixture completo | ≤350 MiB |
| Build + dependencias runtime sin Node, media, DB o backups | ≤300 MiB |

No rebajar límites a posteriori para colorear un informe. Si uno no es viable, medir, explicar tradeoff y pedir revisión del líder con ADR. La métrica INP real depende del uso; tests de interacción sintéticos no se rotulan como datos de campo.

## Técnicas concretas

Paginación servidor, cargas de detalle perezosas, índices y EXPLAIN donde corresponda, evitar N+1 y transferir listas completas al navegador. Búsqueda normalizada, debounce alrededor de 200 ms, cancelación de respuestas obsoletas. Solo incorporar FTS5 si el patrón/medición lo necesita; no motor de búsqueda externo.

Recalcular costes con consultas por lote y memoización local del DAG. No recorridos completos de todas las recetas en cada pulsación. Proteger event loop de importaciones masivas y procesamiento de imágenes; trabajos acotados/worker thread si la medida demuestra bloqueo.

Separar guardar de subir imagen y ofrecer indicador de progreso. El cuerpo útil SSR debe aparecer sin esperar varias peticiones cliente.

## Imágenes y disco

Una foto opcional por receta al inicio; generar variante de ficha y miniatura, por ejemplo 1.280 px y 320 px. Objetivo de foto de ficha ≤350 KiB y miniatura ≤60 KiB, respetando calidad; medir percentiles, no prometer todos los originales al mismo peso.

No guardar fotos en base64 dentro de SQLite ni en HTML. Eliminar EXIF/GPS, no conservar el original enorme tras transformación validada salvo opción pactada. Deduplicar por hash cuando sea simple. Borrado físico diferido para no romper backups; recolección de huérfanos con dry-run y autorización de operación.

Ejemplo orientativo, no medición: 1.000 imágenes de 300 KiB suman unos 293 MiB, más miniaturas. Los backups multiplican el uso si se copian enteros; usar retención y deduplicación adecuadas.

Logs rotados (p. ej. 5×10 MiB), exportaciones temporales con caducidad, artefactos de E2E fuera de producción, guardar solo trazas/vídeo de fallos. Separar disco de desarrollo (dependencias + navegadores + caches, mayor) del runtime (menor). No prometer un desarrollo completo de pocos megabytes.

## Contención SQLite

Timeout acotado, transacciones cortas, un escritor; probar ráfaga de sesiones y reintentos. Mantener WAL con checkpoint sano; medir tamaño de -wal. La versión de SQLite debe contener los parches relevantes (incluido el arreglo de WAL-reset documentado en 2026); descartar releases retiradas y verificar driver real en G0.
