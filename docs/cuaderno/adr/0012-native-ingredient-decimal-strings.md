# Cantidades nativas como cadenas decimales

La cantidad de un ingrediente admite 16 cifras enteras y 16 decimales en
PostgreSQL. Convertirla a un número JSON o JavaScript podía redondearla al
abrir y guardar una receta, incluso sin modificar sus ingredientes.

La API nativa devuelve `amount` como cadena decimal en ingredientes, recetas
y exportaciones. El esquema OpenAPI y el SDK generado declaran esa misma
cadena. Los clientes deben conservarla al editar y enviarla como cadena para
mantener todas las cifras. Se conserva la aceptación de entradas numéricas
compatibles; una precisión perdida antes de enviar el JSON no puede recuperarse.

La representación usa texto decimal fijo y elimina exclusivamente ceros finales
de la parte decimal. No usa `float` ni `Decimal.normalize()`, que puede aplicar
un contexto de precisión menor que el campo. La entrada acepta coma o punto y
espacios externos. Valores inválidos producen un error 400 en español antes de
crear o modificar entidades relacionadas.

El editor conserva cadenas durante lectura, edición y guardado. Normaliza las
entradas válidas y mantiene el borrador ante errores. El escalado persistente
usa enteros de precisión arbitraria; si el resultado excede los límites del
campo, conserva las cantidades y explica cómo ajustar las raciones. Las sumas
de la vista de pasos se presentan exactamente aunque superen el límite de un
ingrediente individual. El contrato numérico de listas de compra permanece
separado.

Las regresiones verifican el JSON real de GET → PUT, los IDs originales,
cantidades máximas y diminutas, edición de notas y rechazo atómico de entradas
inválidas. La aceptación de navegador también abre el editor nativo, comprueba
sus campos, rechaza una entrada inválida sin petición de escritura, corrige
una coma y guarda conservando las cantidades.
