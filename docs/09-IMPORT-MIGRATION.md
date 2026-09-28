# 09 · Migración del recetario y portabilidad

## Dos trabajos distintos

1. Implementar un importador/exportador general probado: parte de la calidad técnica del producto.
2. Extraer y transformar los datos del programa antiguo de Elisabeth: servicio específico, pendiente de conocer el sistema, formato, volumen y autorización.

No prometer recuperación de todos los datos, contraseñas o imágenes sin inspección. No hacer scraping de cuentas reales, romper controles de acceso o desarrollar OCR sin necesidad. Preguntar por nombre del programa, opción de exportar y un archivo pequeño representativo anonimizado cuando llegue ese momento.

## Formato canónico v1

JSON UTF-8 con `schemaVersion`, `currency`, `priceBasis`, ingredientes/formatos, recetas/líneas, categorías e instrucciones. Números decimales como strings. IDs externos conservados separados de IDs internos. Las referencias se resuelven por ID, no emparejando nombres automáticamente.

`examples/import/canonical-v1.json` es una muestra mínima ficticia para Esencial, no una copia de datos del cliente. El esquema definitivo se valida con Zod y tiene tests de upgrade entre versiones.

CSV por entidades: ingredientes, recetas y líneas, con `external_id`, separador/locale explícitos. Un formato desconocido se transforma mediante adaptador por fuente, fuera del motor de costes. Importar `.xlsx` no es requisito inicial ni obliga a instalar Office; una exportación CSV/JSON basta para el contrato base.

## Flujo seguro

Archivo → validación → normalización → vista previa → incidencias → confirmación humana → transacción/import por lote controlado → informe → comprobación.

Previsualización muestra cuántas recetas/ingredientes hay, campos ignorados, unidades sin equivalencia, precios desconocidos, referencias rotas y duplicados posibles. No crea recetas parciales silenciosamente ni rellena cantidades inventadas.

Tamaño inicial hasta 10 MiB de JSON/CSV por lote y 10.000 filas como techo de seguridad configurable; para datasets mayores usar lotes/CLI en entorno de importación, no incrementar sin medir el timeout de HTTP. La interfaz conserva informe descargable sin datos privados en logs.

Idempotencia por fuente, external_id y hash de contenido. Reimportar el mismo archivo es no-op; conflicto de cambio se presenta y necesita política explícita. Un batch inválido no deja escrituras parciales. No deduplicar ingredientes por coincidencia aproximada sin decisión del usuario.

## Comprobación posterior

Comparar recuentos, referencias, número de líneas, precios/unidades e imágenes; seleccionar una muestra de recetas para cotejo humano. La suma de costes solo compara datos con precios completos. Exportar de nuevo y validar roundtrip semántico; no exigir timestamps/IDs internos idénticos.

La copia previa se realiza antes de una importación real. Trabajar primero en instalación de prueba; no sobrescribir la única copia del origen. El cliente conserva siempre su exportación original sin modificar.

## Handoff de migración

Entregar plantilla de petición de muestra, reporte de diagnóstico, propuesta de mapeo y lista de datos que no pueden transferirse. Cuando falte el programa origen, el estado correcto es CLIENT_MIGRATION_PENDING, no fallo del motor genérico ni importación real completada.
