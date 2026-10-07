# Recetas y planificación por edición

Distribución acordada el 7 de octubre de 2026. Las funciones nuevas se añaden al
recetario, al calendario y a las listas existentes. Cada edición conserva las
funciones de las anteriores y las funciones nativas útiles.

| Función | Esencial | Profesional | Integral |
|---|---|---|---|
| Recetas propias, notas, categorías, compartir y cantidades por comensal | Sí | Sí | Sí |
| Galería de hasta 20 fotos fijas por receta | Sí | Sí | Sí |
| Favoritas personales y variantes vinculadas al original | Sí | Sí | Sí |
| Ocho declaraciones dietéticas manuales por receta | Sí | Sí | Sí |
| Calendario de comidas de 1 a 5 semanas | Sí | Sí | Sí |
| Lista de compra con cantidades, secciones y recetas de origen | Sí | Sí | Sí |
| Tipos de plato dentro de cada comida | — | Sí | Sí |
| Plantillas reutilizables de 1 a 5 semanas | — | Sí | Sí |
| Filtro dietético del menú, rojo para «No apto» y desconocidos explícitos | — | Sí | Sí |
| Eventos y anotaciones de ausencias de personal | — | Sí | Sí |
| Ficha de producción y preparación profesional | — | Sí | Sí |
| Impresión individual en vertical u horizontal | — | Sí | Sí |
| Impresión conjunta de hasta cinco menús | — | — | Sí |
| Proveedores, pedidos, recepciones y movimientos de existencias | — | — | Sí |

Los importes existentes son información comercial: Esencial 500 € + 17 €/mes,
Profesional 1.000 € + 20 €/mes e Integral 1.500 € + 30 €/mes. El selector de
edición configura los flujos del espacio; no tramita cobros o suscripciones.
La comparación aparece en Ajustes del espacio. Los costes de recetas y las
funciones nativas básicas siguen disponibles en todas las ediciones.

Consulta puede leer sus datos autorizados, gestionar sus favoritas personales e
imprimir los menús permitidos por su edición. Cocina y Responsable pueden
modificar recetas y planificación dentro de sus permisos nativos. Las ausencias
de personal son visibles y modificables exclusivamente por Responsable. Cambiar
la edición requiere el permiso de administración del espacio.

Las dietas son celíacos, colesterol, diabetes, hiposódica, gástrica, fibra,
sin fructosa y sin lactosa. Cada declaración conserva estado y nota: «No
declarado», «Apto · declaración manual» o «No apto · declaración manual».
No declarado significa desconocido. La aplicación no infiere aptitud clínica ni
ausencia de alérgenos a partir de ingredientes incompletos.

Las plantillas crean entradas del calendario nativo. Reemplazar una aplicación
requiere confirmación y conserva los demás menús; si existen vínculos de compras
o producción, se rechaza el reemplazo. Aplicar una plantilla no consume stock.
Las revisiones de edición rechazan escrituras obsoletas. Mover un plato a otra
comida conserva su entrada y procedencia y retira el tipo de plato incompatible.

## Estado de verificación

Implementación y revisión de fuente en curso. Las pruebas PostgreSQL, Vue,
compilación, OpenAPI y Playwright del nuevo candidato deben pasar en CI antes de
desplegar. Las evidencias de `ff3b685` corresponden únicamente a esa versión anterior, no a estas
funciones nuevas. La aceptación HTTPS y la recuperación del siguiente candidato
se registrarán con su propia identidad de fuente e imagen.
