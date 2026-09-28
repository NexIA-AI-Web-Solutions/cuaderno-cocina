# Contratos de prueba entregados, no aplicación implementada
Los JSON son oráculos numéricos escritos independientemente del código productivo. Los `.feature` describen criterios. NO son pruebas de que Tandoor modificado ya cumpla nada, ni se ejecutan solos como tests de navegador.
Codex debe convertirlos en tests pytest/pytest-django y Playwright con los servicios/API reales, registrando red/green y revisión. No producir una API que devuelva estas fixtures ni calcular expected llamando a la función sometida a prueba.
Los tests ubicados en `tests/` en la raíz del ZIP (fuera de overlay) verifican herramientas de handoff, no estos recorridos de producto.
Comprobar casos inválidos: importe negativo, cero raciones, unidad ambigua, precio ausente, protección de receta privada y escalado simultáneo. Stock: SQL/transacciones/concurrencia reales; no sustituir con una lista Python.
