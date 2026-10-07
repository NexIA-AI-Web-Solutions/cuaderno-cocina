# Modernización del 7 de octubre de 2026

## Estado posterior a la CI y ampliación funcional

El runtime publicado es `ff3b685`, con CI 37651982834: nueve jobs PASS,
Playwright de raíz 367 y prefijo 483, incluidos 348 casos de modernización,
sin retries, skips ni flaky; G7 17/17 del mismo candidato. GPT-6 Astra revisó
independientemente las 80 clasificaciones, veinte distintas por categoría.
Los resultados no significan que cada una se haya reproducido personalmente
en el VPS. Un recorrido personal Astra abrió diez rutas distintas en 22 casos
y revisó sus 22 capturas; es anterior al ajuste de keepalive propio de Caddy.

La aceptación pública posterior conserva READ 25 PASS/1 FAIL y un caso sin
ejecutar por fallo de control exacto del worker. La fase WRITE no abrió navegador
al detectar dos OOM y el gestor de usuario fallido durante otro despliegue
comunicado por el propietario. No hay cierre final de aceptación de `ff3b685`.
La nueva fuente reduce el precache inicial al SVG propio y liga `clients.claim()`
a `activate.waitUntil`; once pruebas unitarias pasan tras tres fallos de aserción
significativos previos. La causa exacta del fallo de navegador no está demostrada.
Plazos, collectors y retries de Playwright se conservan.

Las funciones adicionales se distribuyen según
[recetas y planificación por edición](../09-FUNCTIONAL-PLANS.md). Su persistencia,
UI, compilación y aceptación deben verificarse con una nueva CI/imagen. Los
apartados siguientes conservan las clasificaciones y evidencias históricas.

Estado preparatorio: las nuevas fuentes todavía no están publicadas en producción. El runtime vigente continúa en `60aca2d`; sus pruebas históricas no certifican estos cambios.

Se exige una categoría primaria por resultado distinto: bug funcional en una operación normal, gestión de errores ante un fallo, UX para facilitar una tarea, o UI para mejorar la presentación. GPT-6 Astra revisa las clasificaciones y evidencias. El cliente admitió un agente Astra; dos intentos adicionales alcanzaron el límite de threads. Los escritores heredados no se atribuyen a Astra.

Las 40 correcciones funcionales tienen revisión independiente y pruebas de los scripts realmente enviados: la misma suite dio 47 FAIL sobre las fuentes previas y 47 PASS después. Una corrección adicional del calendario aporta ocho pruebas, con siete FAIL previos y 55 PASS combinados. Estas pruebas usan APIs sintéticas y stubs de ciclo de vida; no sustituyen compilación Vue, DOM o aceptación de roles en navegador.

Las 40 mejoras UI/UX siguientes están implementadas y clasificadas por Astra, con 430 archivos de frontend congelados y 46 comprobaciones de fuente PASS. Aún no cuentan como verificadas en navegador. Hay trece capturas reales anteriores, de un recorrido que conservó su FAIL al bloquear una creación automática de token en calendario. Los fallos del harness de onboarding/logout se conservan y no se contabilizan como bugs de la aplicación.

## Correcciones funcionales y gestión de errores

La ejecución real del candidato `808724b` en el CI 37608974757 dio raíz
290/367 PASS y prefijo 406/483 PASS, con 77 fallos en cada matriz. No hubo
retries ni skips y G7 rechazó el candidato; su imagen no se cargó ni desplegó.
El informe oficial de raíz, ligado por SHA256, solo permite atribuir resultados
parciales de 14 UX y 15 UI a casos aprobados. No cierra los mínimos ni la release.
Las trazas confirmaron tres GET 403 de supermercados para Consulta, Ayuda con
ancho inline superior al límite y navegación temática oculta en escritorio.
Se corrigen esos comportamientos, el nombre accesible de búsqueda y dos
interacciones del harness: VSelect por teclado y foco después de visibilidad.
Los permisos nativos, collector, retries y plazos permanecen intactos. Estas
correcciones suplementarias no añaden resultados al registro de 80.

| ID | Resultado | Fuente | Estado |
| --- | --- | --- | --- |
| BUGFIX-01 | La consulta de selector más reciente prevalece frente a respuestas antiguas. | `vue3/src/components/inputs/VModelSelect.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-02 | Una búsqueda de ID pendiente no restaura una selección cambiada o eliminada. | `vue3/src/components/inputs/VModelSelect.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-04 | Editar un ID ausente conserva las demás selecciones. | `vue3/src/components/inputs/VModelSelect.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-05 | Cambiar el filtro guardado reemplaza los criterios anteriores. | `vue3/src/pages/SearchPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-06 | Escribir un nombre filtra los libros visibles. | `vue3/src/pages/BooksPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-07 | La lista de libros incluye las páginas siguientes. | `vue3/src/pages/BooksPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-08 | Cambiar de libro en la misma ruta carga su contenido. | `vue3/src/pages/BookViewPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-09 | Las flechas del libro respetan los extremos de la paginación. | `vue3/src/pages/BookViewPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-10 | Borrar una propiedad elimina su ID del estado local. | `vue3/src/pages/PropertyEditorPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-11 | Guardar propiedades incorpora los IDs y valores devueltos por el servidor. | `vue3/src/pages/PropertyEditorPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-12 | El editor incluye todas las páginas de tipos de propiedad. | `vue3/src/pages/PropertyEditorPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-13 | El filtro de ingredientes más reciente prevalece frente a respuestas antiguas. | `vue3/src/pages/IngredientEditorPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-14 | Reintentar un borrado por lotes procesa solo los elementos fallidos. | `vue3/src/components/dialogs/BatchDeleteDialog.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-15 | El diálogo espera que terminen las automatizaciones antes de completar el lote. | `vue3/src/components/dialogs/ModelMergeDialog.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-16 | Reabrir la combinación limpia destino y resultados anteriores. | `vue3/src/components/dialogs/ModelMergeDialog.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-17 | Salir del importador cancela sus temporizadores de seguimiento. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-18 | Compartir URL y texto inicia una única lectura de origen. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-19 | Una búsqueda antigua cancelada conserva la carga de la consulta vigente. | `vue3/src/pages/SearchPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-20 | La vista previa de origen más reciente prevalece frente a respuestas antiguas. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| BUGFIX-22 | Abrir el importador no crea un token de marcador sin acción explícita. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-01 | El importador maneja errores de red o respuestas no JSON sin otra excepción. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-02 | Un fallo de importación por IA termina el estado de carga. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-03 | Un fallo de imagen posterior al alta se gestiona y permite abrir la receta guardada. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-04 | Un fallo de imagen en un lote se gestiona y permite continuar la cola. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-05 | El lote maneja errores que carecen de respuesta HTTP. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-06 | Un resultado sin receta libera la carga y continúa el lote. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-07 | El fallo de importación de archivo se gestiona. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-08 | La subida de imagen rechaza un status HTTP fallido antes de interpretar el resultado. | `vue3/src/composables/useFileApi.ts` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-09 | La subida de archivo rechaza un status fallido o un import_id ausente. | `vue3/src/composables/useFileApi.ts` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-10 | La recuperación de un ID seleccionado maneja el rechazo. | `vue3/src/components/inputs/VModelSelect.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-11 | Un filtro guardado con JSON inválido muestra un error recuperable. | `vue3/src/pages/SearchPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-12 | Un guardado fallido de ingrediente conserva los cambios pendientes. | `vue3/src/pages/IngredientEditorPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-13 | El asistente conserva su vista si falla el guardado del espacio. | `vue3/src/pages/WelcomePage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-14 | El asistente comprueba los rechazos de ajustes antes de avanzar. | `vue3/src/pages/WelcomePage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-15 | Omitir el hogar no navega si falla el guardado. | `vue3/src/pages/HouseholdPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-16 | Un guardado fallido conserva cambios pendientes y evita navegar como si hubiera pasado. | `vue3/src/composables/useModelEditorFunctions.ts` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-17 | Un rechazo del hook previo al guardado termina la carga. | `vue3/src/composables/useModelEditorFunctions.ts` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-18 | Una combinación fallida aparece como fallo y permite reintento. | `vue3/src/components/dialogs/ModelMergeDialog.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-19 | El marcador maneja fallos de consulta y creación de token. | `vue3/src/pages/RecipeImportPage.vue` | PASS fuente/unitario; CI y navegador pendientes |
| ERRORFIX-20 | La creación de hogar sin contexto activo termina la carga y explica el error. | `vue3/src/pages/HouseholdPage.vue` | PASS fuente/unitario; CI y navegador pendientes |

## Mejoras de UX y UI

| ID | Resultado implementado | Fuente | Estado |
| --- | --- | --- | --- |
| UX01 | Panel de ajustes móvil accesible sin recorrer todo el menú. | `vue3/src/pages/SettingsPage.vue` | PASS fuente; CI y navegador pendientes |
| UX02 | Destinos de navegación móvil con etiquetas visibles. | `vue3/src/apps/tandoor/Tandoor.vue` | PASS fuente; CI y navegador pendientes |
| UX03 | Menú de cuenta operable por teclado. | `vue3/src/apps/tandoor/Tandoor.vue` | PASS fuente; CI y navegador pendientes |
| UX04 | Enlace para saltar la navegación y enfocar el contenido. | `vue3/src/apps/tandoor/Tandoor.vue` | PASS fuente; CI y navegador pendientes |
| UX05 | Título de receta como enlace accesible por teclado. | `vue3/src/components/display/RecipeCard.vue` | PASS fuente; CI y navegador pendientes |
| UX06 | Acción de colección con nombre y acceso por teclado. | `vue3/src/components/display/HorizontalRecipeWindow.vue` | PASS fuente; CI y navegador pendientes |
| UX07 | Controles del calendario con nombre y superficie táctil adecuada. | `vue3/src/components/display/MealPlanCalendarHeader.vue` | PASS fuente; CI y navegador pendientes |
| UX08 | Estado visible mientras se obtiene el recuento inicial. | `vue3/src/pages/StartPage.vue` | PASS fuente; CI y navegador pendientes |
| UX09 | Lista de compras vacía con explicación y siguiente acción. | `vue3/src/components/display/ShoppingListView.vue` | PASS fuente; CI y navegador pendientes |
| UX10 | Búsqueda e input con nombres accesibles y localizados. | `vue3/src/components/inputs/GlobalSearchDialog.vue` | PASS fuente; CI y navegador pendientes |
| UX11 | Selección de búsqueda expuesta mediante combobox y listbox. | `vue3/src/components/inputs/GlobalSearchDialog.vue` | PASS fuente; CI y navegador pendientes |
| UX12 | Búsqueda pendiente distinguible de ausencia de resultados. | `vue3/src/components/inputs/GlobalSearchDialog.vue` | PASS fuente; CI y navegador pendientes |
| UX13 | Nombres completos del espacio y hogar legibles. | `vue3/src/components/display/MenuUserInfo.vue` | PASS fuente; CI y navegador pendientes |
| UX14 | Acceso al hogar mediante enlace de teclado. | `vue3/src/components/display/MenuUserInfo.vue` | PASS fuente; CI y navegador pendientes |
| UX15 | Los dieciséis temas de ayuda redactados en español. | `vue3/src/components/display/HelpView.vue` | PASS fuente; CI y navegador pendientes |
| UX16 | Ayuda sobre privacidad ajustada a la autorización de recetas. | `vue3/src/components/display/HelpView.vue` | PASS fuente; CI y navegador pendientes |
| UX17 | Ayuda que explica la disponibilidad real de IA. | `vue3/src/components/display/HelpView.vue` | PASS fuente; CI y navegador pendientes |
| UX18 | Pestañas de compra móvil con etiquetas de tareas visibles. | `vue3/src/components/display/ShoppingListView.vue` | PASS fuente; CI y navegador pendientes |
| UX19 | Selector de ayuda etiquetado y tema actual identificable. | `vue3/src/components/display/HelpView.vue` | PASS fuente; CI y navegador pendientes |
| UX20 | Selectores de intercambio explican la estructura de los archivos compatibles. | `vue3/src/utils/integration_utils.ts` | PASS fuente; CI y navegador pendientes |
| UI01 | Paleta cobre y oliva con contraste de texto comprobado. | `vue3/src/vuetify.ts` | PASS fuente; CI y navegador pendientes |
| UI02 | Identidad propia con vectores originales de Cuaderno Cocina. | `vue3/src/assets/cuaderno-logo.svg` | PASS fuente; CI y navegador pendientes |
| UI03 | Navegación de escritorio con destino activo y ritmo visual claros. | `vue3/src/apps/tandoor/Tandoor.vue` | PASS fuente; CI y navegador pendientes |
| UI04 | Navegación móvil con indicador visual del destino activo. | `vue3/src/apps/tandoor/Tandoor.vue` | PASS fuente; CI y navegador pendientes |
| UI05 | Una receta conserva proporciones de tarjeta en escritorio. | `vue3/src/components/display/HorizontalRecipeWindow.vue` | PASS fuente; CI y navegador pendientes |
| UI06 | Imagen ausente sustituida por ilustración vectorial propia centrada. | `vue3/src/components/display/RecipeImage.vue` | PASS fuente; CI y navegador pendientes |
| UI07 | Tarjeta de receta con nombre y metadatos en una composición contenida. | `vue3/src/components/display/RecipeCard.vue` | PASS fuente; CI y navegador pendientes |
| UI08 | Inicio con título y contexto del recetario. | `vue3/src/pages/StartPage.vue` | PASS fuente; CI y navegador pendientes |
| UI09 | Periodo del calendario legible también en móvil. | `vue3/src/components/display/MealPlanCalendarHeader.vue` | PASS fuente; CI y navegador pendientes |
| UI10 | Calendario con límites, cabeceras y día actual distinguibles. | `vue3/src/components/display/MealPlanView.vue` | PASS fuente; CI y navegador pendientes |
| UI11 | Ajustes de escritorio con paneles visualmente diferenciados. | `vue3/src/pages/SettingsPage.vue` | PASS fuente; CI y navegador pendientes |
| UI12 | Preferencias de apariencia y recetas agrupadas visualmente. | `vue3/src/components/settings/CosmeticSettings.vue` | PASS fuente; CI y navegador pendientes |
| UI13 | Ayuda con anchura de lectura y espaciado adecuados. | `vue3/src/components/display/HelpView.vue` | PASS fuente; CI y navegador pendientes |
| UI14 | Tema activo de ayuda distinguible en escritorio. | `vue3/src/components/display/HelpView.vue` | PASS fuente; CI y navegador pendientes |
| UI15 | Cobertura de traducción con porcentajes y encabezados legibles. | `vue3/src/components/display/HelpView.vue` | PASS fuente; CI y navegador pendientes |
| UI16 | Resultado seleccionado de búsqueda con indicación visual propia. | `vue3/src/components/inputs/GlobalSearchDialog.vue` | PASS fuente; CI y navegador pendientes |
| UI17 | Barra de compras contenida y organizada con adaptación al ancho. | `vue3/src/components/display/ShoppingListView.vue` | PASS fuente; CI y navegador pendientes |
| UI18 | Pendientes y completados en grupos visuales separados. | `vue3/src/cuaderno/pages/ListaPage.vue` | PASS fuente; CI y navegador pendientes |
| UI19 | Formularios y estados de producción con jerarquía visual. | `vue3/src/cuaderno/pages/ProduccionPage.vue` | PASS fuente; CI y navegador pendientes |
| UI20 | Acciones y auditoría del almacén con jerarquía visual. | `vue3/src/cuaderno/pages/AlmacenPage.vue` | PASS fuente; CI y navegador pendientes |

La suite previa de presentación conservó catorce fallos de contratos/estructura y dos fallos del harness al faltar una expresión Intl y el nuevo estado de carga. No se presentan como dieciséis reproducciones funcionales. La compilación y los recorridos DOM son las comprobaciones necesarias de las mejoras visuales.

Los resultados adicionales de carga inicial, enlaces de ayuda inválidos, límites del teclado de búsqueda, rechazo sin `cause` y token del calendario permanecen separados del mínimo de 80. La identidad visual repetida en varias pantallas cuenta una sola vez; tampoco se cuentan individualmente cada traducción, token CSS o formato de importación.

Los seis recorridos nuevos de Playwright tienen alcance explícito: UI01 mide el tema activo en DOM y las pruebas de fuente comprueban ambos temas; UX20 comprueba los seis formatos del selector de exportación en DOM y las definiciones de los veinticinco importadores en fuente; UX15 revisa los dieciséis temas en fuente y renderiza recetas, IA y traducciones. Cada resultado condicionado por ancho o edición solo puede acreditarse en los proyectos donde se ejecuta su comprobación. Estos recorridos todavía no se han ejecutado contra la nueva imagen.

La publicación requiere CI completo del nuevo commit, identidad de imagen inmutable, aceptación de ediciones/roles, capturas y revisión final de Astra, backup coherente, restauración aislada y rollback compatibles. El resto de aplicaciones y correo se compara con su referencia actual; no se instala toolchain de build en el VPS. Las copias autorizadas son locales en `backups/`: continúa pendiente un destino externo. Licencias, avisos, historia e identificadores de protocolos se conservan.
