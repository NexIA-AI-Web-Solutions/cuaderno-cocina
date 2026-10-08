# Rendimiento y almacenamiento: medir antes de optimizar

## Presupuestos de aceptación propuestos, no resultados medidos
Dataset sintético reproducible: 3000 recetas, 1500 alimentos, 15 ingredientes medios/receta, 10 usuarios de prueba y 100000 movimientos para Integral. Referencia pequeña: 2 vCPU/2 GiB de RAM para probar adecuación, no garantía comercial. Registrar hardware, versiones, red y parámetros.
APIs listas/paginadas objetivo p95 <=800ms; escandallo de receta corriente <=300ms en red local excluyendo carga de imagen; test concurrencia 5 usuarios. Si baseline upstream excede, documentar y optimizar recorridos críticos sin maquillar dataset. El propietario ha actualizado este presupuesto de 500 a 800 ms; el cambio del criterio de aceptación no implica una mejora de rendimiento medida.
UI objetivo LCP <=2.5s e INP <=200ms en perfil declarado, no universal. Evitar regresión >20% frente a baseline. Bundle adicional del módulo Esencial objetivo <=100 KiB comprimidos sobre entrada; lazy load de gráficos/Integral. No imponer un límite total inventado al bundle heredado sin medirlo.

## Estrategias
Paginación/caps, índices compuestos por Space/Food/fecha, select_related/prefetch_related, coste por lotes, no N+1. Query count estable al variar tamaño de página dentro de límite; EXPLAIN sobre consultas lentas. Recalcular únicamente recetas visibles/afectadas; snapshot y cache key con versión de receta/precio y Space si hay caché.
No Redis por reflejo. No inicializar cuatro backends ni exportar toda BD para cada lista. No descargar imágenes originales en miniaturas; conservar compresión/reorientación nativa y ampliar tamaños si falta.

## Disco
Medir imágenes, datos, Git, dependencias, cachés y backups POR SEPARADO. Los clones donantes no son datos de producción. Clon parcial de Tandoor conserva historia sin descargar todos los blobs; clones superficiales para referencias.
Fotos con límites y miniaturas; backups rotados; no raw uploads repetidos para cada retry; no `node_modules`, `.git`, caches pip, playwright browsers, fixtures ni referencias en imagen final. No borrar originales del cliente sin autorización.
Multi-stage build solo después de reproducir upstream. Build Vue y tests no deben instalarse en runtime innecesariamente. Revisar dependencias opcionales después de pruebas de importación y funciones; no borrar módulos a ciegas porque ocupan espacio.

## Cuota mensual
17/20/30 € son importes ofertados, no dimensionamiento. Entregar medición y coste operativo estimado por instalación al propietario; no prometer soporte humano ilimitado ni hardware dedicado a ese precio. Infraestructura compartida entre clientes solo si se diseña y prueba aislamiento; no habilitar ahora un SaaS multi-tenant público.
