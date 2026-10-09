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

## Seguimiento de la validación de navegador

La ejecución GitHub Actions `37953516292`, fuente `309d809`, terminó su matriz
raíz con 683 pruebas aprobadas y un fallo en WebKit: al abrir «Platos del
periodo», el desplegable tenía un mínimo de 736 px y un máximo disponible de
720 px. El navegador notificó un ciclo de ResizeObserver antes de seleccionar
el plato; la subida y las cuatro descargas PDF/PNG completaron sus aserciones.
Se conserva el fallo original.

La corrección limita solo ese desplegable al ancho disponible y elimina su
mínimo implícito. Una regresión de selección múltiple con nombres largos y
Consulta pasó de RED a GREEN; 32 pruebas enfocadas aprobaron. Falta confirmar
esta nueva corrección en WebKit y completar la release de producción. No se
modifican el colector de errores, las barreras de lectura ni los tiempos.


### Resultado posterior y corrección en curso

La [CI 37961329952](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37961329952)
de `42c420d` confirma que la primera corrección fue insuficiente: raíz 683
PASS / 1 FAIL y prefijo 799 PASS / 1 FAIL, por el mismo ResizeObserver en
WebKit. G7 falla y no produce el aggregate de diecisiete controles. La release
no se publica; producción mantiene V12 saludable.

El diagnóstico nativo V8 reproduce el ciclo al crear/recargar la portada y
preparar el documento, antes del raster: lista 720→744 px y filas 688→712 px,
sin cambio de altura. Sus contenedores se limpian sin OOM registrado; el estado
final de la unidad browser no se capturó. La campaña raster V7 conserva su OOM
y descargas parciales, sin certificación. Chromium V5 conserva seis PASS de
fuente `2abd98b` y tests `309d809`, con ese alcance histórico.

La nueva fuente de trabajo prepara una anchura estable de 38 rem, limitada al
viewport menos 48 px, únicamente en «Platos del periodo» mediante
`cuaderno-menu-recipe-options`; sus 32 pruebas focalizadas pasan. El diagnóstico
CSS V9 pasa un caso WebKit en 57,1 s, con collector estricto, sin pageerror
ni snapshots, cgroups finales sin OOM/kill y limpieza propia. Su CSS experimental
afecta todos los VSelect solo durante el diagnóstico y no certifica el cambio
final limitado a ese selector. La CI completa, commit e imagen final siguen
pendientes. Se mantienen collector,
permisos, barreras de lectura, tiempos y cero retries. Los artefactos oficiales
y gates pendientes constan en [STATUS](STATUS.md#resizeobserver-nativo-y-evidencia-retenida--9-de-octubre-de-2026)
y [RELEASE_CHECKLIST](RELEASE_CHECKLIST.md#resizeobserver-nueva-fuente-de-trabajo-y-gates-abiertos-2026-10-09).
La admisión requiere nueva CI completa, G7, aceptación pública de nueve cuentas
y administrador, y backup/restauración del nuevo runtime.
