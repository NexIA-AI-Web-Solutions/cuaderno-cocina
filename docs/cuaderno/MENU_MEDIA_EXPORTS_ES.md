# Fotos de ingredientes, portadas y documentos de menús

La ampliación del 9 de octubre extiende los ingredientes `Food` y las plantillas
de menús existentes. Conserva recetas, calendario, Spaces, historial y permisos
nativos. No incorpora otro servicio ni envía imágenes a proveedores externos.

| Función | Esencial | Profesional | Integral |
|---|---|---|---|
| Foto de ingrediente: subir, sustituir, descripción y eliminar | Sí | Sí | Sí |
| Foto y galería de recetas existentes | Sí | Sí | Sí |
| Portada opcional de plantilla de menú profesional | — | Sí | Sí |
| Documento de menús: impresión, PDF y PNG | — | Sí | Sí |
| Combinar menús profesionales en un documento | — | — | Sí |

Consulta puede ver imágenes autorizadas y descargar los documentos disponibles
en su edición. Cocina y Responsable pueden modificar imágenes. Una receta
privada y sus ingredientes exclusivos conservan su visibilidad nativa; tener
privilegios globales no concede acceso a otra Space ni a una receta privada.

## Uso

En la edición de un ingrediente guardado, utiliza **Foto del ingrediente**.
Selecciona JPG, PNG, WebP o GIF, añade una descripción opcional y pulsa
**Guardar imagen**. Para un ingrediente nuevo, guárdalo primero y vuelve a
abrir su edición. **Eliminar imagen** pide confirmación y conserva el resto del
ingrediente. Una fusión conserva la foto del destino; si no tiene, transfiere
la del origen.

En **Organización de menús**, puedes seleccionar una portada al guardar una
plantilla y cambiarla después en su tarjeta. En la pestaña **Impresión**, añade
los platos del periodo, selecciona opcionalmente la portada de una plantilla,
elige orientación y declaración dietética y pulsa **Preparar documento**.
Comprueba la vista previa y utiliza **Descargar PDF**, **Descargar PNG** o la
impresión del navegador. Los estados desconocidos de dietas no se presentan
como aptos; el documento conserva sus avisos.

## Correcciones automáticas y límites

Las imágenes admiten hasta 5 MiB y 25 megapíxeles, con un único fotograma.
El servidor corrige la orientación EXIF, elimina metadatos y reduce imágenes
grandes a 2048 píxeles en su lado mayor, conservando la proporción. Una imagen
dañada, un formato no admitido o una operación sin permisos muestra un mensaje
en español. Un fallo al subir la portada conserva el intento y permite
reintentarlo sin crear otra plantilla.

El documento usa A4 vertical u horizontal y renderiza al doble de resolución:
1588 × 2246 o 2246 × 1588 píxeles. El PDF contiene páginas rasterizadas; su texto
no es seleccionable. PNG genera un archivo por página y el navegador puede
solicitar autorización para varias descargas. Los límites son cinco grupos,
cien platos por grupo, cuarenta páginas y 40 MiB; divide un documento que los
supere. Las portadas se obtienen únicamente de rutas autorizadas de la app.

## Implementación y pruebas

- `cuaderno/models.py` y `migrations/0019_food_and_menu_images.py`: extensiones
  `FoodImage` y `MenuTemplateImage`, ligadas a los modelos y Space existentes.
- `cuaderno/api/entity_media.py`, `services/entity_media.py` y `urls.py`: API
  autenticada de metadatos, subida, borrado y contenido privado.
- `cuaderno/services/recipe_extras.py`: normalización de imágenes compartida;
  `services/food_merge.py` y `cookbook/views/api.py`: fusión nativa con fotos.
- `cuaderno/services/planning.py`: portada autorizada en plantillas/documentos.
- `vue3/src/cuaderno/components/EntityImagePanel.vue`,
  `components/model_editors/FoodEditor.vue` y `pages/MenuPlanningPage.vue`:
  controles de subida, mensajes, permisos, vista previa y descargas.
- `vue3/src/cuaderno/menuExport.mjs` y `menuExportBrowser.ts`: paginación,
  renderizado acotado y PDF, sin nuevas dependencias.
- `cuaderno/tests/test_entity_media.py`: PostgreSQL, roles, privacidad, Space,
  normalización, rollback, concurrencia, eliminación y fusión real de Food.
- `tests/cuaderno/e2e/menu-media-exports.spec.ts`: subidas y descargas reales,
  persistencia, permisos y cuatro tamaños de pantalla. Sus fotografías CC0
  y procedencia están en `tests/cuaderno/e2e/assets/menu-media/`.

La presencia de los tests no acredita su ejecución. Los resultados del
candidato, navegador y despliegue se registran por separado en las evidencias
de la release; esta guía describe el comportamiento implementado.
