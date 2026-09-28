---
name: cocina-inventario
description: Extender compras, stock y producción nativos de Tandoor.
---

# cocina-inventario

Lee `AGENTS.md` y `docs/cuaderno/05-PRODUCTION-AND-STOCK.md`.

## Procedimiento
1. Auditar InventoryEntry/Log y todos sus escritores.
2. Definir autoridad única y transacción.
3. Añadir idempotencia y bloqueos en PostgreSQL.
4. Probar reintentos y dos consumos concurrentes.
5. Verificar ledger/proyección y reversión sin borrado.

## Salida
Resumen breve, rutas/commit, pruebas ejecutadas y limitaciones. No sustituye evidencia de ejecución. No modifica repos de referencia ni realiza acciones externas.
