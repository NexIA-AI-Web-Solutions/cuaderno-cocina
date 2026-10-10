# Revisión estática del fallo de rendimiento local

Fecha: 2026-10-10. Revisión de solo lectura; no se ejecutó otra prueba pesada ni se modificaron consultas o umbrales. Comparación contra HEAD `4335e6e9b858581c724e154c799c095cddb88383` en `/home/kripta/cuaderno-reservas-20261010`.

La ejecución completa final observó p95 1704.959 ms para `movements_100_of_100000` con cinco usuarios concurrentes, frente al límite de 800 ms. El test `test_performance.py` exige ese límite explícitamente para cada endpoint concurrente, además de los límites secuenciales; este resultado incumple el gate local. El p95 1690.73 ms de una ejecución anterior también incumple el mismo límite. El código de salida 0 capturado en aquella ejecución anterior y la ausencia de resumen unittest en su log son inconsistentes con una afirmación de suite aprobada: no constituyen evidencia suficiente de aprobación.

La comparación `git diff HEAD` no muestra cambios de reservas en `MovementView.get`, `movement_document`, `MOVEMENT_SQL`, los permisos comunes, `recipes/test_settings.py` ni `cuaderno/tests/test_performance.py`. En `operational_reads.py` únicamente cambia la proyección de servicios: añade el enlace de reserva por `LEFT JOIN`; no interviene en el listado de movimientos. En `operations.py` las modificaciones añaden guardas a escrituras de servicios y producción, sin cambiar el GET de movimientos. No se ha demostrado una regresión de consulta causada por reservas.

El listado de movimientos materializa los identificadores de inventario autorizados, evalúa permisos y datos en una sola sentencia SQL, filtra movimientos por Space e inventario, ordena por ID descendente y limita a 100 filas antes de construir el documento JSON. El modelo ya declara el índice `(space, -id)`. No se obtuvo un nuevo EXPLAIN o perfil de CPU de esta ejecución; por ello no se afirma que el plan real utilice ese índice ni que exista un escaneo excesivo.

La inspección de recursos de los contenedores locales mostró:

| Contenedor aislado | CPU (`NanoCpus`) | Memoria |
| --- | ---: | ---: |
| `cuaderno-reservas-20261010-test` | 1000000000 (1 CPU) | 671088640 bytes (640 MiB) |
| `cuaderno-reservas-20261010-db` | 500000000 (0.5 CPU) | 268435456 bytes (256 MiB) |

Estos límites son contexto de medición, no una causa demostrada ni una exención del gate. El benchmark usa cinco clientes DRF en hilos, abre conexiones por ronda y mide tres rondas de solicitudes concurrentes. Sus resultados no representan latencia de navegador, red pública, LCP o INP.

Siguiente comprobación acordada: CI externo canónico, con comando, código de salida, resumen y métricas conservados, sin relajar el límite. Si también falla, el diagnóstico acotado sería ejecutar el módulo de rendimiento de forma aislada con `CUADERNO_PROFILE=1`, obtener el EXPLAIN y perfil existentes, y comparar la consulta actual con el baseline bajo los mismos recursos y fixture. Solo si ese diagnóstico prueba un defecto del plan o de la ejecución se plantearía una corrección mínima en `cuaderno/services/operational_reads.py` y sus pruebas de autorización/forma de consulta; una migración de índice necesitaría evidencia independiente. No se propone ahora modificar estos módulos.
