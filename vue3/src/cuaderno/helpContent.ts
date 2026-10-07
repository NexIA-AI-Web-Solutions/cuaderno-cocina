export type HelpAction = {title: string; icon: string; to: {name: string; params?: {model: string}}}
export type HelpSection = {id: string; title: string; icon: string; paragraphs: string[]; actions?: HelpAction[]}
const action = (title: string, name: string, icon: string, model?: string): HelpAction => ({title, icon, to: {name, ...(model ? {params: {model}} : {})}})

/** Product guidance; historical section IDs remain valid for existing links. */
export const helpSections: HelpSection[] = [
    {id: 'start', title: 'Start', icon: 'fa-solid fa-house', paragraphs: [
        'Cuaderno Cocina reúne tus recetas, la planificación de comidas y la lista de la compra. Usa el menú para pasar de una tarea a otra sin perder el contexto de tu espacio.',
        'Las funciones operativas disponibles dependen de la edición y de tu rol. Consulta permite leer; las acciones de escritura requieren la autorización correspondiente.',
    ], actions: [action('Recipes', 'StartPage', '$recipes')]},
    {id: 'space', title: 'Space', icon: 'fa-solid fa-database', paragraphs: [
        'Un espacio reúne los datos de una familia, un equipo o una organización. Comprueba el nombre del espacio activo antes de trabajar; puedes pertenecer a varios espacios.',
        'El acceso a una receta depende de su visibilidad y de los permisos. Los libros, las listas y los planes pueden tener sus propias opciones de acceso compartido.',
        'Las invitaciones y los roles se administran desde los ajustes del espacio. Pertenecer al mismo espacio no concede automáticamente todas las acciones.',
    ], actions: [action('YourSpaces', 'UserSpaceSettings', '$spaces'), action('SpaceSettings', 'SpaceSettings', '$settings'), action('Invites', 'SpaceMemberSettings', 'fa-solid fa-users')]},
    {id: 'recipes', title: 'Recipes', icon: '$recipes', paragraphs: [
        'Una receta contiene pasos, ingredientes, instrucciones y tiempos. Cada ingrediente combina cantidad, unidad y alimento; estos datos permiten escalar las raciones y preparar la compra.',
        'Una receta privada requiere autorización de su autor o un acceso compartido válido. Revisa su privacidad y las personas autorizadas antes de compartirla; no todas las recetas son públicas.',
        'Los enlaces compartidos sólo están disponibles si el espacio permite compartir. Cualquier persona con un enlace válido puede acceder a su contenido autorizado: entrega el enlace con cuidado.',
    ], actions: [action('Create', 'ModelEditPage', '$create', 'Recipe'), action('Search', 'SearchPage', '$search')]},
    {id: 'import', title: 'Import', icon: '$import', paragraphs: [
        'Puedes incorporar una receta desde una dirección web o introducir sus datos manualmente. Revisa los ingredientes, las unidades y las instrucciones importadas antes de guardarla.',
        'Para un archivo de exportación, elige el formato que coincide con su estructura. Las descripciones distinguen texto, XML, JSON, Markdown y archivos comprimidos; un ZIP no identifica por sí solo el formato.',
        'La importación mediante imágenes o PDF requiere que la IA esté habilitada y configurada para tu espacio. La importación normal no necesita activar esas funciones.',
    ], actions: [action('Import', 'RecipeImportPage', '$import')]},
    {id: 'ai', title: 'AI', icon: '$ai', paragraphs: [
        'Las funciones de IA pueden ayudar a interpretar imágenes o documentos cuando están habilitadas para el espacio. Su disponibilidad depende de la configuración del servidor y del proveedor.',
        'Revisa el resultado antes de guardar: cantidades, ingredientes, alérgenos y pasos pueden necesitar correcciones. Una respuesta de IA no sustituye la revisión de una receta.',
        'Si tienes permiso para administrar proveedores, revisa también el registro de uso y los límites configurados. No se envían documentos a un proveedor por abrir esta ayuda.',
    ], actions: [action('AiProvider', 'ModelListPage', '$ai', 'AiProvider'), action('AiLog', 'ModelListPage', '$ai', 'AiLog'), action('SpaceSettings', 'SpaceSettings', '$settings'), action('Import', 'RecipeImportPage', '$import')]},
    {id: 'unit', title: 'Unit', icon: 'fa-solid fa-scale-balanced', paragraphs: [
        'Las unidades expresan las cantidades de ingredientes y compras. Una unidad base permite convertir entre unidades compatibles de masa o volumen, aunque sus nombres sean distintos.',
        'Una conversión de volumen a masa necesita la densidad del alimento. Por ejemplo, una taza de harina y una taza de aceite no pesan lo mismo: declara la conversión adecuada.',
    ], actions: [action('Unit', 'ModelListPage', 'fa-solid fa-scale-balanced', 'Unit'), action('Conversion', 'ModelListPage', 'fa-solid fa-arrow-right-arrow-left', 'UnitConversion')]},
    {id: 'food', title: 'Food', icon: 'fa-solid fa-carrot', paragraphs: [
        'Los alimentos son los ingredientes reutilizables de tus recetas y listas. Usar el mismo alimento evita duplicados y permite relacionar cantidades, propiedades y compras.',
        'En su editor puedes añadir propiedades o relacionar un alimento con otra receta. Revisa el nombre y la unidad al seleccionar ingredientes para un cálculo.',
    ], actions: [action('Food', 'ModelListPage', 'fa-solid fa-carrot', 'Food')]},
    {id: 'keyword', title: 'Keyword', icon: 'fa-solid fa-tags', paragraphs: [
        'Las palabras clave organizan la colección por tipo de comida, cocina, dieta u otro criterio. Puedes crearlas desde el editor de recetas o desde su lista.',
        'Elige nombres consistentes y evita duplicados. Un emoji puede ayudar a reconocer una categoría, pero conserva un nombre que explique su significado.',
    ], actions: [action('Keyword', 'ModelListPage', 'fa-solid fa-tags', 'Keyword')]},
    {id: 'recipe_structure', title: 'RecipeStructure', icon: 'fa-solid fa-diagram-project', paragraphs: [
        'Divide una receta en pasos con instrucciones y sus ingredientes. Un paso puede incluir tiempos, archivos o una referencia a otra receta.',
        'Las propiedades, los comentarios y las palabras clave aportan contexto. Para los cálculos operativos de subrecetas, el rendimiento declarado es distinto del número de raciones.',
    ]},
    {id: 'properties', title: 'Properties', icon: 'fa-solid fa-database', paragraphs: [
        'Las propiedades añaden información a alimentos y recetas, como nutrientes u otros valores medibles. Primero define el tipo de propiedad y después sus valores y cantidades de referencia.',
        'Las conversiones de unidad permiten comparar cantidades compatibles. Un dato ausente no equivale a cero: revisa las advertencias antes de interpretar un total.',
        'El editor de propiedades permite revisar los alimentos de una receta. Los identificadores de bases de datos externas ayudan a importar valores, que debes comprobar para tu alimento concreto.',
    ], actions: [action('Property', 'ModelListPage', 'fa-solid fa-database', 'PropertyType')]},
    {id: 'recipe_search', title: 'Search', icon: '$search', paragraphs: [
        'La búsqueda rápida encuentra recetas y ofrece acceso a la búsqueda avanzada. Usa los filtros cuando quieras combinar palabras clave, ingredientes, valoraciones u otros criterios.',
        'Si no aparece la receta esperada, comprueba el espacio activo, su visibilidad y los filtros. Cambiar un filtro no modifica las recetas guardadas.',
    ], actions: [action('Search', 'SearchPage', '$search')]},
    {id: 'search_filter', title: 'SavedSearch', icon: 'fa-solid fa-bookmark', paragraphs: [
        'Una búsqueda guardada conserva una combinación de filtros para reutilizarla. Sus resultados pueden cambiar cuando añades o modificas recetas que cumplen esos filtros.',
        'Ponle un nombre que explique el criterio, por ejemplo una dieta o los ingredientes que quieres aprovechar. Guardar una búsqueda no crea copias de las recetas.',
    ]},
    {id: 'books', title: 'Books', icon: '$books', paragraphs: [
        'Los libros reúnen recetas de una colección. Puedes organizarlos por temporada, ocasión o cualquier criterio que te resulte útil.',
        'Revisa las opciones de acceso del libro antes de compartirlo. Añadir una receta a un libro no elimina sus propias restricciones de privacidad.',
    ], actions: [action('Books', 'BooksPage', '$books')]},
    {id: 'shopping', title: 'Shopping', icon: '$shopping', paragraphs: [
        'Añade alimentos directamente o incorpora los ingredientes de una receta. Revisa las raciones y las unidades antes de comprar; varias recetas pueden contribuir al mismo alimento.',
        'Selecciona la lista y el supermercado que necesitas. Los filtros pueden ocultar alimentos marcados o aplazados: revisa los ajustes si parece que falta una línea.',
        'Los cambios necesitan conexión para guardarse. Si aparece una advertencia de sincronización, conserva la lista y comprueba el resultado antes de repetir una operación.',
    ], actions: [action('Shopping_list', 'ShoppingListPage', '$shopping'), action('Settings', 'ShoppingSettings', '$settings')]},
    {id: 'meal_plan', title: 'Meal_Plan', icon: '$mealplan', paragraphs: [
        'El plan de comidas organiza recetas o notas por fecha y tipo de comida. Usa las flechas para cambiar de periodo y el control de hoy para volver a la fecha actual.',
        'Comprueba las raciones antes de enviar ingredientes a la compra. El calendario y la producción operativa son tareas diferentes: abrir un plan no produce un servicio ni descuenta existencias.',
        'Los tipos de comida permiten clasificar las entradas y definir horarios. La suscripción de calendario se gestiona desde su opción específica; protege sus enlaces de acceso.',
    ], actions: [action('Meal_Plan', 'MealPlanPage', '$mealplan'), action('Meal_Type', 'ModelListPage', 'fa-solid fa-utensils', 'MealType')]},
]

export function validHelpSection(section: unknown): string {
    return typeof section === 'string' && (section === 'translations' || helpSections.some(topic => topic.id === section)) ? section : 'start'
}
