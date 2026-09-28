---
name: cocina-entrega
description: Validar build, rendimiento, backup, restore y handoff de la aplicación real.
---

# cocina-entrega

Lee `AGENTS.md` y `docs/cuaderno/12-DEPLOYMENT-BACKUP.md`.

## Procedimiento
1. Build limpio a partir del fork y lockfiles.
2. Ejecutar registry real y medir métricas.
3. Backup/restore en destino nuevo con hashes.
4. Revisión de source provenance y patches.
5. Marcar release solo con evidencia; separar local de prod.

## Salida
Resumen breve, rutas/commit, pruebas ejecutadas y limitaciones. No sustituye evidencia de ejecución. No modifica repos de referencia ni realiza acciones externas.
