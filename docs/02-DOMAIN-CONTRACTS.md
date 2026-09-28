# 02 · Contratos de dominio: lo que no puede fallar

## Representación

- Dinero de entrada: EUR, céntimos enteros no negativos para un precio de compra conocido. `null` significa desconocido; cero significa gratuito conocido, confirmado de forma explícita.
- Cantidades: strings decimales canónicos positivos, punto interno, sin separadores de millares. Máximo seis decimales para cantidades introducidas. Nunca `parseFloat` para el cálculo.
- Unidad base: `g`, `ml`, `unit`. Dimensión separada: masa, volumen, unidades. Una cantidad puede tener fracción de unidad; una cantidad de comensales es entera positiva.
- Aritmética: Decimal con precisión suficiente (por ejemplo 40 dígitos); redondear el dinero mostrado a céntimos con HALF_UP. No redondear cada término antes de sumar.
- Importes derivados pueden contener fracciones de céntimo. Persistirlos como decimal canónico o recalcularlos; no usar SQLite REAL. El valor de inventario operativo usa hasta doce decimales de céntimo y agota el residuo al consumir toda la existencia.
- Totales SQL no convierten TEXT a REAL. Para agregaciones monetarias usar representación entera acotada o el servicio decimal; comprobar límites y no pasar por Number fuera de enteros seguros.

## Localización

En formularios españoles `1,25` significa 1.25. También se acepta `1.25` sin separador de millares; `1.250` se interpreta como 1.250 decimal, nunca como mil doscientos cincuenta. Avisar junto al campo: «Sin separador de miles». Rechazar mezclas ambiguas como `1.234,56` y `1,234.56` salvo que el importador tenga locale explícito y vista previa.

EUR y formato de fecha se aplican al mostrar, no contaminan los valores almacenados. Instantes en UTC; fecha/hora del servicio según Europe/Madrid, con pruebas de cambio de hora y horas inexistentes/ambiguas. No convertir una fecha de menú en un instante por accidente.

## Coste de un ingrediente

```
precio_por_unidad_base = precio_del_formato / cantidad_base_del_formato
coste_de_linea = cantidad_base_utilizada * precio_por_unidad_base
coste_receta = suma_sin_redondeo_prematuro(coste_de_linea)
coste_racion = coste_receta / raciones_base
```

Un formato de 5 L de aceite a 32 € tiene 5.000 ml. Usar 200 ml cuesta 1,28 €. Las pruebas deben cubrir conversiones kg/g, L/ml y envases con varias unidades.

Masa y volumen NO son intercambiables. Para convertir 1 L de aceite en kg se necesita densidad explícita validada, no suponer agua; la versión inicial rechaza la conversión cruzada. «Una cebolla» no tiene peso universal: usar un peso por unidad específico documentado o mantener dimensión unidades.

Si una receta usa un ingrediente sin precio, devolver `{status: 'incomplete', knownSubtotal, missingIngredientIds}`. No mostrar un total completo o margen definitivo. Con cero conocido no aparece como faltante.

## Selección inequívoca del precio

Cada ingrediente tiene **un formato activo de referencia para calcular costes**. Aunque tenga varios envases/proveedores, la receta nunca escoge el más barato o el último de una lista de forma implícita. La pantalla de ingredientes identifica ese formato y permite cambiarlo con vista previa del precio normalizado. Editar el formato activo propaga el coste; editar otro formato no cambia los escandallos hasta seleccionarlo.

Una recepción Integral conserva su precio histórico. Puede proponer actualizar el precio de referencia, pero requiere una confirmación explícita en la recepción. Coste actual de receta, coste real de una recepción y valoración de existencias son conceptos distintos.

## Precio y actualización

Un cambio de precio incrementa su versión, registra fecha y evento mínimo, y modifica los costes actuales de sus recetas. Esencial ya tiene esta propagación. Integral añade consulta histórica y análisis de impacto, no cobra otra vez el recálculo básico.

Cargar todas las líneas/precios necesarias en pocas consultas. Si se cachea, cache por versiones y con invalidación demostrada; no comenzar con un cache distribuido.

Un menú futuro refleja precios actuales. Una producción confirmada o recepción registrada conserva snapshot/versiones de los importes usados; un cambio posterior no reescribe el pasado.

## Escalado

`factor = raciones_solicitadas / raciones_base` y cada cantidad se multiplica por ese factor. Vista previa sin mutar receta. No se redondean ingredientes a paquetes de compra en el escandallo; eso pertenece a la propuesta de compra. Raciones base y destino mayores que cero; límites explícitos; sin `NaN`, infinito o valores negativos.

Las cantidades pueden escalar linealmente. Los tiempos de horno, temperaturas y seguridad de cocción no se recalculan como si fueran cantidades; permanecen instrucciones a revisar por una persona.

## Profesional: mermas y subrecetas

Merma de ingrediente modelada como `yield = aprovechable / comprado`, en (0,1]. Si 1 kg comprado a 2 € rinde 0,8 kg limpio, 1 kg limpio cuesta 2,50 €. Cada línea declara `quantityBasis = as_purchased | usable`. Las líneas de Esencial y las importadas sin otra indicación se conservan como `as_purchased`. Solo una línea marcada «producto aprovechable» (`usable`) divide por yield para calcular compra necesaria. Si la cantidad ya representa producto comprado, no volver a aplicarle la merma. Cambiar esta base requiere una acción explícita con vista previa; activar Profesional no reinterpreta recetas existentes en silencio.

La salida de una elaboración tiene su propia cantidad/unidad de rendimiento. Una salsa que cuesta 10 € y produce 2.000 g cuesta 0,005 €/g. 300 g en otro plato aportan 1,50 €. No aplicar otra vez las mermas de los ingredientes cuando se inserta esa salsa.

Grafo dirigido acíclico: impedir autorreferencias, A→B→A y ciclos largos dentro de la transacción. Límite de profundidad inicial 10 con error explicado; memoización de subárboles. Propagar precios faltantes e ingredientes/alérgenos transitivos, sin inferir seguridad para consumidores.

No admitir recetas vinculadas como subelaboraciones en Esencial por importación o endpoint directo si esa capacidad no está habilitada. La exportación de datos previamente existentes no se destruye al bajar de edición.

## Menús, producción y reservas internas

Servicio tiene fecha, nombre, capacidad opcional y platos con raciones explícitas. Reserva es un grupo/referencia interna con plazas y estado (pendiente, confirmada, cancelada). Las plazas confirmadas actualizan previsión de comensales sin duplicarla con un contador manual. Elegir una única fuente por servicio: `manual` o `reservations`; no sumarlas indiscriminadamente.

Planificar no mueve stock. Confirmar producción en Integral sí crea consumo. Necesidades consolidadas explotan subrecetas y suman ingredientes base, sin descontar dos veces una subelaboración y sus ingredientes. No se inventa inventario de producto terminado en esta entrega.

## Presupuesto y rentabilidad

Siempre disponible en Profesional: comparar coste por ración con presupuesto objetivo. Si no hay precio de venta, no mostrar «beneficio».

Para venta, todos los importes se comparan en la misma base elegida (neta o con impuestos incluidos); no asumir situación fiscal ni calcular IVA por su cuenta. Contribución sobre ingredientes = precio comparable − coste ingredientes. Porcentaje de coste = coste / precio ×100. No incluye salarios, energía, alquiler o resultado contable. Cero/desconocido en venta no produce divisiones inválidas.

## Integral: existencias y valoración

Movimientos append-only: opening, receipt, consumption, waste, adjustment, reversal. Cantidad firmada; referencia/actor/instante y motivo. No editar/eliminar movimientos confirmados: registrar compensación.

Stock disponible = suma de movimientos válidos. No admitir saldo negativo por defecto. Comprobar saldo y escribir el movimiento en la MISMA transacción (`BEGIN IMMEDIATE` o equivalente probado). Conflictos se responden con estado recuperable, no perdida silenciosa.

Coste medio ponderado operativo: 10 kg a 2 €/kg + 10 kg a 4 €/kg = 20 kg valorados en 60 €, media 3 €/kg. Consumir 5 kg baja 15 €, quedan 15 kg/45 €. Desperdiciar 2 kg baja 6 €, quedan 13 kg/39 €. No recalcular ese valor histórico con el último precio de catálogo.

Cuando el saldo se agota exactamente, retirar todo el valor residual para no dejar céntimos fantasma. No introducir ajustes contables fiscales. Un ajuste de inventario requiere motivo y valoración explícita para entradas no compradas.

Compras: pedir no equivale a recibir. Recepción parcial crea movimientos solo de las cantidades recibidas. Idempotencia obligatoria por operación; reintentar la misma recepción/producción no duplica stock. Claves únicas servidor, no confiar solo en desactivar un botón.

Anular una entrada ya consumida puede dejar saldo imposible: bloquear y exigir corrección operativa explícita; no forzar negativos para hacer pasar el test. Registrar eventos conservando trazabilidad.

Propuesta de compra normalizada: `max(0, necesidad − disponible)`, después empaquetado redondeado al alza según proveedor. Si faltan equivalencias entre dimensiones, producir una incidencia a revisar, no un número supuesto. Es una propuesta, no una orden enviada.

## Concurrencia y borrado

Receta/ingrediente tienen `version`. Editar exige expectedVersion: si alguien guardó antes, devolver conflicto 409 y conservar ambos cambios para revisión. Archivar un ingrediente referenciado no borra el pasado. Reemplazar requiere acción explícita y transacción.

Invariantes de actor, edición y rol en servidor para importaciones, descargas, lecturas de importes, endpoints y jobs, no solo botones de UI.
