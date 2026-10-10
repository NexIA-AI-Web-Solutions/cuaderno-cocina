# Reservas de clientes

Ampliación local del 10 de octubre de 2026. Disponible en Profesional (1.000 € + 20 €/mes) e Integral, que hereda las funciones de Profesional. Esencial conserva su calendario nativo y no incluye este módulo. La implementación todavía no está publicada en el servidor.

## Registrar y organizar el servicio

Abre **Reservas** y selecciona el día. **Nueva reserva** permite anotar cliente o grupo, teléfono o correo, fecha, hora, menú guardado, comensales y una nota de organización. El menú se elige por plantilla, día de la plantilla y comida; debe contener recetas. La nota admite alergias o una mesa concreta, pero no acredita que un plato sea apto.

El alta queda **Solicitada**. Cocina y Responsable pueden **Confirmar reserva**. La confirmación crea las fichas de los platos y conserva sus cantidades y costes. No descuenta existencias. El resumen suma los comensales una sola vez por reserva: 20 + 15 + 30 + 10 son 75 comensales y 75 raciones de cada plato del menú. Versiones distintas de una plantilla se muestran separadas para conservar lo comprometido.

Las cantidades de ingredientes proceden de las fichas confirmadas y aplican las raciones base y la merma declarada en cada receta. Una necesidad incompleta produce un aviso. Las fichas y los ingredientes pendientes se pueden consultar antes de iniciar la elaboración.

## Roles y cambios

| Acción | Consulta | Cocina | Responsable |
|---|---|---|---|
| Consultar reservas e historial del espacio, respetando recetas privadas | Sí | Sí | Sí |
| Registrar, confirmar, cambiar datos o comensales | — | Su hogar operativo | Sí |
| Cambiar el menú después del alta | — | — | Sí |
| Pasar a cocina y marcar servida | — | Su hogar operativo | Sí |
| Anular | — | — | Sí |

Para operar hace falta un hogar asignado al usuario. Las fichas y movimientos mantienen esa separación existente en la aplicación. Responsable puede gestionar reservas de otros hogares del mismo espacio.

Cada registro, edición o cambio de estado exige un motivo y conserva una revisión con los datos anteriores y posteriores. Si dos personas editan la misma revisión, la segunda recibe un aviso; su borrador se conserva y puede recargar la versión actual. Los datos de una reserva solicitada o confirmada se pueden modificar. En cocina, servida y anulada no admiten edición de ficha.

Al cambiar fecha, hora, comensales o menú de una confirmada, se sustituyen sus fichas activas y se conservan las anteriores en el historial. Las antiguas entradas del calendario dejan de aparecer como comidas programadas. Las fichas vinculadas se gestionan desde la reserva.

## Producción, cierre y existencias

**Pasar a cocina** registra la producción de todos los platos de la reserva en una única operación. En Profesional no genera movimientos de existencias. En Integral consume los ingredientes disponibles mediante movimientos del libro de stock. Si un plato no puede producirse, la operación completa se revierte y la reserva sigue confirmada.

Si el rendimiento o una conversión produce decimales periódicos, la necesidad calculada conserva su precisión. El consumo se redondea hacia arriba al último decimal que admite el stock (16 decimales), en la unidad de cada lote, para evitar consumir menos de lo necesario. La anulación devuelve exactamente la cantidad registrada.

**Marcar servida** cierra una reserva en cocina. Deja de contar como trabajo pendiente y conserva el consumo ya realizado. Una confirmada anulada sale de la preparación y de las necesidades sin tocar stock. Si Responsable anula una reserva en cocina, la interfaz avisa de que también se revierte su producción y se crean movimientos compensatorios. No se borran los movimientos originales. Una servida permanece cerrada.

En Integral, **Compras → Reposición** permite seleccionar las fechas del periodo. La propuesta incorpora reservas y otros servicios confirmados; las reservas ya producidas no vuelven a contar como necesidad. Crear o enviar un pedido no incrementa existencias: lo hace la recepción confirmada. La propuesta sigue las reglas existentes de mínimos, formatos y ofertas.

## Alcance

El alta se realiza desde el equipo autenticado. No se implementan cobros, un plano de mesas ni un enlace público de solicitudes en esta entrega. No se deduce que una alergia esté resuelta por haberla anotado.

La lista pagina las reservas del día; el resumen incluye todas las accesibles dentro del límite de 2.000 reservas por consulta. Reposición admite hasta 2.000 servicios del periodo. Si se supera el límite se pide reducir fechas, sin presentar un total truncado como completo.

Decisión técnica: [ADR 0013](adr/0013-customer-reservations.md). Validación y limitaciones: [evidencia de reservas](evidence/reservations-20261010/README.md).
