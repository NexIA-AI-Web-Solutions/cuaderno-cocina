# ADR 0013 — Reservas como origen de servicios nativos

Fecha: 2026-10-10. Estado: implementado localmente; publicación pendiente.

## Contexto

El calendario MealPlan, las plantillas MenuTemplate, las fichas ServicePlan y el libro StockMovement ya resuelven planificación, snapshots y producción. Falta la entidad que compromete cliente, contacto, menú y comensales. Los planes son acumulativos y Profesional incorpora reservas; Integral añade las consecuencias sobre compras y stock.

## Decisión

CustomerReservation guarda el compromiso y una copia del menú seleccionado. ReservationRevision conserva antes, después, motivo y autor. ReservationService vincula cada versión activa con un ServicePlan por plato y su MealPlan nativo. La migración 0020 es aditiva; no convierte ni modifica servicios anteriores.

La reserva conserva la identidad de los platos elegidos. Confirmar congela cantidades, merma y costes mediante los servicios existentes. Cambiar cantidades, fecha u opciones de menú de una confirmada retira los vínculos anteriores y genera nuevas fichas; editar solo contacto o nota conserva las fichas. Los vínculos retirados permanecen, pero sus proyecciones se excluyen del calendario operativo.

Las transiciones bloquean el Space y la reserva en una transacción PostgreSQL. La revisión enviada evita sobrescritura concurrente. Repetir la última transición con la misma revisión previa y motivo devuelve el resultado ya registrado. Cada plato recibe una clave de producción propia y estable; un fallo revierte toda la producción de la reserva.

Cocina y Responsable confirman; solo Responsable cambia menú y anula, según aclaración expresa del usuario. Consulta puede leer las reservas accesibles de su Space. Escrituras y consumo mantienen la pertenencia al hogar y las ACL de recetas existentes. La UI recibe capacidades por fila, también cuando falta hogar asignado.

Las operaciones genéricas de servicios, producción y calendario rechazan cambios sobre proyecciones de reservas. Reposición filtra estado, hogar y periodo antes del límite de consulta para que servicios recientes no confirmados no oculten necesidades antiguas. El total agrupa comensales por reserva, no por número de platos.

La aceptación real de Integral detectó que los rendimientos periódicos (por ejemplo 0,9) producían necesidades con más de 16 decimales y el ledger rechazaba la elaboración. Se conserva el cálculo congelado y se cuantiza únicamente la asignación parcial al lote, después de convertir a su unidad, con ROUND_CEILING a 16 decimales. La resta entre lotes usa contexto Decimal de 64 dígitos; la reversión compensa el movimiento almacenado. Las entradas explícitas del usuario siguen sometidas a su validación estricta de precisión. Tres regresiones prueban rendimiento periódico, lotes g/kg y una cola decimal que se perdería con el contexto por defecto de 28 dígitos.

## Consecuencias

Se reutilizan los algoritmos y movimientos existentes; planificación y confirmación no consumen. Pasar a cocina produce; servida cierra; anular en cocina compensa el consumo conservando su trazabilidad. Las reservas cerradas no admiten nueva edición. No hay pagos, mapas de mesas ni enlace público en este candidato.

El nuevo esquema debe migrarse antes de servir el frontend. Publicar requiere imagen, CI y controles de recuperación de esta fuente; reutilizar el runtime anterior en el ensayo local no certifica una nueva imagen de entrega.
