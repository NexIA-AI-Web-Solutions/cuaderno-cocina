# ADR 0015 — Trabajadores locales con evidencia y aprobación

Fecha: 2026-10-11. Estado: implementado en candidato local; despliegue pendiente.

## Decisión

Extender Django/DRF y Vue/Vuetify con ocho análisis deterministas, propuestas
revisables, historial de decisiones y programación de informes de solo lectura.
No crear un segundo motor de recetas, compras, inventario o autenticación.
La aplicación no necesita proveedores de IA, claves ni servicios externos.

Reutilización comprobada: `costing` y `price_history` para Decimal y subrecetas;
`service_plans`, `preparation`, `reservations` para fichas congeladas y reservas;
`purchasing.replenishment` y `create_order` para reposición y pedidos;
`household_inventory`, `visible_recipes`, `visible_foods` para autorizaciones;
`allergens` para declaraciones sin inferir ausencia. La simulación cambia el
contexto de precios en memoria y ejecuta el mismo motor de escandallos.

`WorkerRun` conserva parámetros, informe, política, propuesta, huellas SHA-256,
autor y resultado confirmado. `WorkerEvent` registra generación, aprobación,
aplicación, obsolescencia, descarte y ejecución programada. Es auditoría de
aplicación: no se afirma almacenamiento a prueba de manipulación por DBA.
`WorkerSchedule` añade cadencias opcionales de 24/168 horas. El comando
`run_cuaderno_workers` genera únicamente informes; no ejecuta propuestas.

## Acciones y permisos

Solo dos acciones permitidas: añadir versiones de precios de referencia y crear
un pedido nativo en borrador. Ambas requieren fuente/motivo, propuesta guardada,
confirmación booleana explícita y Responsable. Cocina puede preparar una
propuesta; Responsable puede revisar propuestas autorizadas del Space. El hogar
capturado del pedido se conserva aunque Responsable pertenezca a otro hogar.
El flujo nativo de recepción continúa exigiendo confirmación física separada.

El bloqueo de Space precede al de la ejecución; dentro se actualizan pertenencia
y rol desde PostgreSQL. Aplicar compara huella de datos/política y conserva el
resultado de la primera aplicación. Repetir la misma aprobación devuelve ese
resultado sin duplicar precios/pedidos. Nunca se acepta código, comandos ni URL
remota desde una propuesta. El CSV usa IDs explícitos, cantidades decimales y
límites; no fusiona alimentos por parecido ni interpreta instrucciones del texto.

El historial reautoriza IDs fuente, alimentos anidados, resultados, hogares y
existencias con los permisos actuales. Los agregados de inventario capturan el
hogar y si se usó supervisión de Responsable. Un cambio de permisos no convierte
un informe antiguo en una vía para leer datos actualmente privados.

## Límites deliberados

La invalidación es conservadora: huella de datos del Space (máximo 50.000 filas
incluyendo relaciones) en vez de un grafo incremental de eventos. Puede pedir una
revisión adicional por cambios ajenos a una propuesta; no aplica datos obsoletos.
Los informes/simulaciones tienen límites visibles; una selección no representa
el catálogo completo. El historial muestra hasta 20 ejecuciones autorizables
recientes. No es un archivo histórico paginado completo.

Reposición por defecto: hoy; períodos ordenados de hasta 366 días. Los pedidos
pendientes se muestran separados porque no hay fecha fiable de llegada. No se
cuentan como existencias. Evaluar cada plato no reserva stock para un menú entero.
Una mención dietética es candidata a revisión, nunca una declaración de aptitud.
Frecuencias registradas no son pronósticos ni ahorro demostrado.

Las programaciones se guardan, pero ningún temporizador se instala automáticamente.
La interfaz declara que el ejecutor no está activado; su integración operativa
es una tarea de despliegue explícita. No se promete OCR, extracción universal de
facturas, lectura de correo, envío a proveedores, optimización de capacidad,
aprendizaje automático de equivalencias ni predicción de demanda.

## Alternativas gratuitas investigadas

Se utiliza [csv de Python](https://docs.python.org/3.13/library/csv.html) y
[Decimal](https://docs.python.org/3.13/library/decimal.html), ya disponibles.
[pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) permite texto
de PDF digital, pero no OCR ni comprensión fiable de tablas;
[Tesseract](https://tesseract-ocr.github.io/tessdoc/) puede hacer OCR local con
paquetes/datos adicionales. Ninguno se ha instalado ni se anuncia como función
entregada. No se añade dependencia de runtime ni servicio de pago.

## Verificación

Pruebas PostgreSQL de lectura sin escrituras, Decimal, subrecetas, permisos,
concurrencia, propuestas obsoletas, handoff, resultados históricos y programación;
pruebas de Vue y navegador real contra instancia aislada. Comandos/resultados y
limitaciones en `../evidence/digital-workers-20261011/README.md`.
