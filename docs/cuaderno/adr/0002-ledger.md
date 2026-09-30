# Ledger único sobre el inventario nativo

El saldo de cocina sigue siendo `InventoryEntry.amount`. `InventoryLog` conserva el
historial nativo. `StockMovement` guarda la clave de idempotencia, la cantidad,
el saldo histórico posterior y, si procede, qué movimiento revierte. Un pedido (`PurchaseOrder`) y
un servicio (`ServicePlan` / `MealPlan`) no escriben ese saldo.

No hay una segunda tabla de existencias. La recepción, el consumo, el desperdicio y
la reversión pasan por `cuaderno.services.ledger.apply_movement`, con
`select_for_update` primero sobre Space y después sobre el movimiento previo y la
existencia. Este orden compartido por los escritores evita carreras de claves aún
no creadas; sacrifica concurrencia entre existencias del mismo Space por sencillez
y corrección. El benchmark013745Z medido a gran escala mantiene tres fallos
concurrentes; no se declara cumplimiento del presupuesto de rendimiento.

Los importes equivalentes se canonicalizan para la huella de idempotencia. Una
reversión es un movimiento compensatorio, no un borrado; solo se permite una por
original y no revertir una reversión. La migración 0006 rellena el saldo histórico
únicamente cuando existe log auditado conocido: no inventa históricos usando el
saldo actual. La API nativa de inventario debe respetar esta misma ruta de escritura.

Estado: implementación en revisión (2026-09-29). Las pruebas finales y hallazgos
pendientes figuran en STATUS y evidencia; esta decisión no certifica G4.

La reversión genérica de un movimiento con origin.type=service_plan está
bloqueada: devolver una parte del stock dejaría el servicio producido y su
snapshot incoherentes. RED3/4→GREEN4/4, commit413abf14e. La reversión completa
del documento de producción todavía no está disponible; no se simula desde
este guard. Compras conserva su reversión documental; WASTE independiente
puede revertirse como movimiento compensatorio.

Desde53e2c0671, el desperdicio independiente por API exige motivo textual
recortado de1–256 puntos de código sin C0/C1 ni surrogates aislados. La causa
es parte del origen congelado y de la huella; un cambio con la misma clave
produce409. Los WASTE históricos sin origin pueden reintentarse con el
payload original incluso si incluía cause ignorada: bajo lockSpace se compara
la misma huella histórica y nunca se crea otro movimiento sin causa. El SHA
mantiene JSON ASCII escapado; el límite de origen mide2048bytes UTF8 por
separado. Las fronteras e idempotencia pasan13pruebas PostgreSQL. Esto no
autoriza un desperdicio extra de limpieza sobre un consumo bruto de servicio.
