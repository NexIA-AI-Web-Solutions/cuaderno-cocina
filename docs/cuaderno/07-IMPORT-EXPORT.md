# Migración sin pérdida ni importadores duplicados

## Orden
Primero evaluar import/export de Tandoor. Para un formato soportado: ejecutar round-trip sobre fixtures, no reescribir. Para hueco real: estudiar el migrador correspondiente de Mealie, conservar casos y adaptar serialización/validación a Tandoor. No importar modelos SQLAlchemy ni levantar su API.
No conocer el programa antiguo bloquea únicamente SU extractor, no el importador genérico ni el resto de la app.

## Pipeline
Recibir archivo autorizado → validar tamaño/MIME/zip → copiar a staging privado → detectar formato/version → parsear a representación intermedia → mapear Food/Unit → vista previa con errores → confirmación → importación transaccional por conjunto acordado → informe de conteos y hashes.
Límites explícitos: tamaño comprimido/descomprimido, número de archivos, tamaño por imagen y tiempo. Rechazar Zip Slip, symlinks, rutas absolutas, path traversal, bombas de compresión y HTML/scripts peligrosos. No ejecutar macros ni scripts de un archivo.

## Modelo intermedio
id_externo, fuente/formato/version, receta, raciones, ingredientes con texto original, cantidad decimal o desconocida, unidad y Food propuestos, pasos, notas, etiquetas, imágenes y avisos. Conservar el texto original cuando el parser sea ambiguo. No convertir automáticamente “una pizca” en cantidad cero válida.
Deduplicar por fuente + id_externo y mapping explícito. Nunca solo por nombre. Replay del mismo import no duplica datos. Un import parcial explica rechazados, no los oculta. Una importación de precios no crea compras ni stock.

## Exportación
Datos portables estructurados y fotografías con manifiesto; incluye unidades, formato, precio, rendimientos y vínculos de subreceta cuando existan. Mantener propiedad privada y permisos, no exportar recetas de otra persona/Space por ser administrador de un espacio diferente. Exportar/backup no son lo mismo: backup recupera instalación completa, export sirve para portabilidad.

## Programa de Elisabeth
Solicitud comercial aparte: nombre/versión y una exportación de ejemplo autorizada. No intentar credenciales ajenas ni scraping del programa en producción. Antes de migrar datos reales: backup inmutable de origen, import staging, recuentos de recetas/ingredientes/imágenes, muestreo aprobado y comparación de cálculos; no apagar el antiguo sin comprobación.
