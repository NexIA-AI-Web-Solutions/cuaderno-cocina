---
name: cocina-orquestacion
description: Coordinar implementación de Cuaderno por tareas y agentes sin colisiones.
---

# cocina-orquestacion

Lee `AGENTS.md` y `docs/cuaderno/13-ORCHESTRATION.md`.

## Procedimiento
1. Leer tareas y dependencias DONE.
2. Asignar packet con paths y test.
3. Spawn hasta dos escritores y un revisor/explorador.
4. Esperar resultados, inspeccionar diff, ejecutar integración.
5. Checkpoint y siguiente tarea; no aprobar sin revisión.

## Salida
Resumen breve, rutas/commit, pruebas ejecutadas y limitaciones. No sustituye evidencia de ejecución. No modifica repos de referencia ni realiza acciones externas.
