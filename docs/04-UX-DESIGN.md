# 04 · Interfaz profesional y adaptación a dispositivos

## Dirección visual

Producto de trabajo, no una landing comercial. Fondo claro cálido, texto carbón, un acento verde oliva y estados semánticos diferenciados. Tipografía de sistema para no descargar fuentes; números tabulares en importes. Espacios 4/8/12/16/24/32 px, radios moderados, sombras discretas, jerarquía clara. Tokens en `tooling/design-tokens.json` como punto de partida; verificar contraste final.

No usar gradientes gigantes, veinte tarjetas KPI vacías, emojis como iconos, animaciones decorativas ni varios kits de componentes. Iconos SVG locales seleccionados de una biblioteca cuya licencia se registre. No hace falta generar fotografías: recetas con foto opcional real del usuario y placeholder neutro; las demostraciones no simulan fotos reales del cliente.

## Navegación por edición

Esencial abre en **Recetas**. Menú: Recetas, Ingredientes, Ajustes. Buscador prominente y botón Nueva receta. No inventario oculto bajo candados ni banner de venta.

Profesional añade Planificación, subelaboraciones y presupuesto del menú. Integral añade Compras, Inventario y Proveedores; usuarios solo para responsables. Permisos además de edición: una persona de consulta no ve botones de edición y tampoco puede usarlos por URL.

Escritorio: sidebar compacta y contenido con ancho máximo; recetas list/grid con preferencia persistida. iPad: barra lateral plegable, objetivos táctiles grandes, orientación vertical/horizontal. Móvil: navegación inferior de 3–4 accesos y «Más»; listas en tarjetas legibles, no tabla de diez columnas miniaturizada.

## Pantallas obligatorias

### Recetas

Buscar por nombre/categoría; ordenar; paginación 24/48. Tarjeta con nombre, raciones, coste por ración y estado de completitud. Placeholder si falta foto. Estado vacío con una acción que lleva a un formulario real.

### Editor

Cabecera nombre/categoría/raciones; bloque ingredientes; preparación; resumen de costes. Buscador de ingrediente con combobox accesible y alta rápida conservando el borrador. No puede confundirse precio del paquete con precio/kg. Etiquetas visibles para cantidades y unidades, teclado decimal y error junto al campo.

En escritorio, resumen lateral; en móvil, bloque plegable y botón Guardar visible sin tapar el teclado. Guardado explícito, prevención de doble envío y aviso de cambios sin guardar. No almacenar por defecto recetas privadas en localStorage. Al fallar la red conservar el formulario en memoria y explicar que no se guardó; no fingir sincronización offline.

### Ficha de receta

Nombre, foto opcional, ingredientes, instrucciones, raciones base, selector de comensales, coste y fecha de precios. «Preparar para 35» es simulación, no edición automática. Botones Editar, Duplicar, Imprimir. Ficha básica A4 sin menús; técnica avanzada solo Profesional.

### Ingredientes

Nombre, formato, precio del formato, precio normalizado, fecha y recetas afectadas. Para editar precio mostrar antes/después; no confirmaciones modales para cada campo menor. Archivar con advertencia si se utiliza; no borrar referencias.

### Planificación

Semana/servicio en escritorio; agenda de día en móvil. Lista consolidada, presupuesto/comensal, hojas de producción. El conteo de reservas muestra si se usan comensales manuales o reservas confirmadas. No calendario drag-and-drop imprescindible: debe poder operarse con formulario/teclado.

### Integral

Compras y recepciones no se confunden; stock cuenta movimientos. Desperdicio: ingrediente, cantidad, motivo y confirmación. Mostrar fecha de actualización y aviso de que stock solo es fiable si se registran movimientos. Panel de compras sugeridas con explicación de cada cantidad.

## Accesibilidad y comportamiento

Objetivo de diseño WCAG 2.2 AA, no certificación automática: etiquetas, foco visible, contraste, estructura semántica, zoom 200 %, mensajes anunciados, reduced motion, controles táctiles de unos 44 px. No acciones exclusivas por hover/arrastrar. Diálogos con foco contenido y Escape; sin diálogos anidados.

Documentar el baseline de navegador real de las dependencias. Tailwind moderno tiene mínimos de Safari/Chrome/Firefox; no prometer iPad muy antiguo sin conocer su versión. Probar WebKit automatizado y anotar aparte Safari/iPad físico: una emulación no demuestra que se probó hardware real.

## Matriz de viewport

360×800, 390×844, 768×1024, 820×1180, 1024×768, 1366×768 y 1440×900. Comprobar también anchura pequeña en landscape, teclado, zoom, tablas extensas, nombres largos, receta con 30 líneas y errores.

No scroll horizontal global. Un bloque de tabla ancho puede tener scroll local con indicación. Capturas de referencia al aprobar G2, G3 y G4; usar datos sintéticos y no generar screenshots como sustituto de E2E funcionales.
