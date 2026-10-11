# Trabajadores digitales locales

Candidato del 11 de octubre de 2026. Ruta de interfaz: `/cuaderno/trabajadores`.
No usa LLM, claves API ni servicios externos de pago. La producción no cambia
hasta el despliegue autorizado de este candidato.

## Qué puedes hacer

| Trabajador | Resultado |
|---|---|
| Completar costes | Localiza cantidad, formato, precio, rendimiento o conversión faltante; agrupa preguntas compartidas y enlaza recetas. |
| Vigilar precios | Compara versiones guardadas, costes congelados y actuales; simula una tarifa propuesta sin guardarla. |
| Preparar el servicio | Reúne reservas, fichas congeladas, necesidades y checklist de la fecha seleccionada. |
| Revisar requisitos | Muestra declaraciones y menciones explícitas de notas para su confirmación. Desconocido nunca significa ausente. |
| Preparar compras | Reposición nativa y mínimos, existencias utilizables y pedidos abiertos por separado; prepara un borrador revisable. |
| Revisar entregas | Comprueba coherencia de pedidos, recepciones, conversiones y movimientos ya registrados. |
| Proponer platos | Compara recetas existentes, coste por ración y presupuesto. En Integral añade disponibilidad registrada por plato. |
| Aprender del registro | Cuenta servicios, producción, cancelaciones y frecuencias registradas; no predice demanda. |

Esencial incluye costes/precios; Profesional añade servicio, requisitos, platos y
registro; Integral añade compras/recepciones y disponibilidad de inventario.
Los límites y fuentes aparecen en cada informe. Los botones contextuales están
en receta, precios, reservas, producción y almacén.

## Tarifa CSV y aprobación

En Vigilar precios, pulsa **Preparar cambio de precio**, elige formato y precio,
o pega un CSV. Indica la fuente revisada. Ejemplo sintético (sustituye el ID):

```csv
package_id,amount,explicit_free,note
123,12.50,false,Tarifa revisada
```

Máximo 50 filas; cabecera e IDs exactos; no hay coincidencias por nombre. Cero exige
`explicit_free=true`. El formato/contenido del envase se mantiene; cambiar de
5 kg a 4 kg requiere corregir el formato en el flujo correspondiente y generar
una propuesta nueva. No se inventa equivalencia ni densidad.

Generar conserva informe/evidencia, sin cambiar precios ni stock. Responsable
revisa efectos, marca confirmación y aplica. El resultado contiene las versiones
de precio o el pedido realmente guardados. Cocina puede preparar propuestas para
Responsable, sujeto a visibilidad actual. Si cambiaron los datos, genera una
versión nueva: la aprobación anterior ya no sirve. Reintentar la misma aplicación
no duplica la operación.

El borrador de compra conserva hogar, envases y oferta seleccionada. No se envía
al proveedor, no recibe mercancía y no cambia existencias. La recepción continúa
en Compras con confirmación humana. No hay procesamiento de pagos.

## Informes periódicos

Puedes guardar cadencias de 24 o 168 horas y pausarlas. La opción inicial usa
la fecha del día en cada ejecución y los períodos predeterminados del trabajador;
si la desmarcas se conservan las fechas fijas del formulario. Son intervalos transcurridos,
no una promesa de la misma hora civil durante cambios de horario. Los permisos
se revisan en cada ejecución. Como máximo 10 activas/20 guardadas por persona.
La programación nunca lleva una propuesta de escritura.

El ejecutor se invoca dentro del runtime de la aplicación:

```sh
/opt/recipes/venv/bin/python manage.py run_cuaderno_workers --limit 20
```

El administrador debe integrarlo con un temporizador local si desea ejecuciones
periódicas. Este candidato no modifica cron/systemd ni instala un servicio en
producción. La pantalla informa de que el ejecutor no está activado. El comando
es idempotente respecto de la ocurrencia vencida y registra fallos sin exponer
las fuentes privadas en el mensaje.

## Evidencia y límites

Puedes copiar o descargar informe en texto/JSON con versión de fuente. Lo impreso
o descargado es una instantánea y no se actualiza solo. El historial reciente
muestra hasta 20 ejecuciones y vuelve a comprobar permisos para revelar fuentes.
No es una bandeja infinita ni una certificación sanitaria/contable.

La revisión de entregas opera sobre datos estructurados ya guardados; no lee
PDF/fotos de albaranes. La lectura documental universal, OCR, sinónimos aprendidos,
planificación de equipo/tiempos y predicción siguen fuera de esta entrega. Esas
funciones no están bloqueadas necesariamente por una clave LLM: necesitan datos,
interfaces y validación adicionales, y algunas pueden hacerse con herramientas
locales gratuitas. No hay una funcionalidad entregada que espere una clave API.
