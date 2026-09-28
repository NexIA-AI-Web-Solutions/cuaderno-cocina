# Ledger único sobre el inventario nativo

El saldo de cocina sigue siendo `InventoryEntry.amount`. `InventoryLog` conserva el
historial nativo. `StockMovement` solo guarda la clave de idempotencia, la cantidad
del movimiento y, si procede, qué movimiento revierte. Un pedido (`PurchaseOrder`) y
un servicio (`ServicePlan` / `MealPlan`) no escriben ese saldo.

No hay una segunda tabla de existencias. La recepción, el consumo, el desperdicio y
la reversión pasan por `cuaderno.services.ledger.apply_movement`, con
`select_for_update` sobre el movimiento previo y sobre la existencia.
