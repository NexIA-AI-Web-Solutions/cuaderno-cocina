# Producción, compras e inventario: una sola ruta de escritura

## Producción profesional
El plan semanal usa MealPlan/MealType; añadir entidades auxiliares solo para capacidad de servicio, reservas internas, estado de confirmación y snapshot. Consolidar por Food + unidad compatible. No sumar alimentos distintos por parecido textual; no colapsar “tomate fresco” y “tomate triturado” sin decisión del usuario.
Estados: borrador → confirmado → producido o cancelado. Confirmar congela necesidades calculadas con versiones; producir requiere acción explícita y afecta a stock solo en Integral. Cancelar un borrador no afecta a existencias.
Reserva interna: fecha, servicio, número de personas, nota no sensible, estado. No pagos ni datos personales detallados. Registrar zona horaria Europe/Madrid con UTC interno para instantes y fecha local para servicio. Probar cambio de hora.

## Extender inventario nativo
Tandoor ya declara InventoryEntry, InventoryLocation e InventoryLog. Antes de crear entidades, caracterizar semántica, API, importadores y borrados. No copiar el modelo de Grocy completo.
Requisito profesional: historial inmutable, autor, causa, unidad, lote cuando exista, documento origen e idempotencia. Si InventoryLog no lo garantiza, introducir ledger auxiliar que sea autoridad de movimientos; InventoryEntry mantiene la proyección de saldo en la misma transacción. No dos contadores independientes.
Definir explícitamente la fuente de verdad en ADR-004 y cubrir reconstrucción/reconciliación. Conserva IDs nativos; no crear otro Food, Location o una segunda API de stock sin adaptar las existentes.
Todas las escrituras nativas (UI, API, import, admin, comandos) deben pasar por el mismo servicio o quedar deshabilitadas para roles operativos. No basta con que la pantalla nueva respete el ledger y la API antigua lo salte.

## Documentos y movimientos
Pedido borrador/enviado NO mueve stock. Recepción confirmada sí; recepción parcial admitida con líneas/cantidades validadas. Plan de compra es propuesta, no pedido aprobado. Registrar desperdicio lo descuenta una vez, con causa; correcciones por reversión con referencia, no editar el movimiento pasado.
Consumo de producción: ingredientes y producción resultante en una sola transacción cuando se modele stock de subelaboraciones. No descontar materia prima y subelaboración a la vez. Si producción resultante no usa stock, declararlo en la ficha del flujo.

## Concurrencia e idempotencia
Transacción por operación de negocio; row locks en PostgreSQL sobre saldos ordenados por id para reducir deadlocks. Clave idempotente por Space + operación, UNIQUE en BD. Mismo key/payload devuelve resultado original; mismo key/payload diferente =>409. No reintento que duplique recepción, desperdicio o producción.
Falta de stock: por defecto rechazar y mostrar diferencia, sin parcial silencioso. Ajuste negativo por permiso explícito y causa solo si se pacta como excepción. Aislamiento de Space/Household también en comprobaciones FK.

## Valoración
Primera entrega: política claramente identificada, por ejemplo coste medio ponderado móvil por Food/ubicación, si el modelo la permite; no presentar FIFO/contabilidad sin implementarlos. Regla y redondeos se congelan antes de tests. Para estimación de recetas se mantiene precio de referencia, no mezclar automáticamente valoración de stock y precio de reposición.
Mínimos por Food/ubicación; propuesta de compra `max(necesidad_confirmada - disponible_utilizable,0)`, ajustada a envases con redondeo hacia arriba, y explicando excedente. Stock reservado, caducado y utilizable no son intercambiables.

## Tests obligatorios
Recepción repetida; dos consumos concurrentes sobre último stock; recepción parcial; cancelar borrador; revertir operación; merge Food; borrado con historial; entrada de otro Space; comprobación ledger/proyección; restauración; actualización de precio sin reescribir producción previa; conversión errónea provoca rollback completo.
