# Interfaz: conservar Tandoor y añadir valor sin recargarlo

## Dirección vinculante
Al usuario le gusta la interfaz de Tandoor. NO producir un dashboard genérico distinto, una landing comercial ni imitar Grocy visualmente. Partir de la versión ejecutable, conservar tarjetas, fotos, editor, lectura de receta, menús, tipografía, espaciados y Vuetify; modificar únicamente branding acordado y módulos necesarios.
Guardar capturas de baseline local antes de editar. Las screenshots de documentación sirven de orientación, no sustituyen el baseline del pin. No afirmar equivalencia visual por comparar solo nombres de componentes.

## Pantallas y recorridos
1. Inicio/recetas: búsqueda clara, categorías y tarjetas nativas. Acciones Nueva, Importar; evitar siete KPIs vacíos.
2. Receta: Ingredientes, Elaboración y pestaña/panel Costes; selector de raciones que no guarda por sí mismo. Aviso “Faltan 2 precios” visible, imprimir incluyendo estado incompleto.
3. Ingredientes y precios: tabla en escritorio, tarjetas compactas móvil; formato, cantidad, unidad, precio, €/base, fecha; formulario “5 L por 32 €” sin stock obligatorio.
4. Menús: calendario nativo; vista lista móvil; servicio, comensales, coste presupuestado y generar hoja de producción.
5. Lista compartida: agrupación, añadir rápido, marcar estado explícito, deshacer; fuente de receta y avisos de sincronización. Patrón de KitchenOwl adaptado a Vue, no su frontend completo.
6. Integral: existencias y movimientos nativos mejorados; recepción distinta de pedido; desperdicio con confirmación. Flujos guiados, no desplegar todos los campos administrativos a un cocinero.

## Responsividad / accesibilidad
Probar 390×844, 768×1024, 1024×768 y 1440×900. Targets táctiles >=44 CSS px como objetivo; foco visible, etiquetas, teclado, contraste AA, sin acciones únicamente hover. Tablas con alternativa móvil y columna de acción fija si hace falta. Teclado numérico decimal donde proceda, tolerar coma española.
No depender de arrastrar como único método. Estado vacío con acción real. Error conserva entrada. Guardando/guardado/fallo de red distinguidos. Evitar confirmaciones cuando no existe riesgo y exigirlas cuando sí lo hay.

## Compatibilidad
Chromium, Firefox y WebKit en tests. WebKit emulado no prueba un iPad físico: dejar checklist pendiente hasta prueba real. No fijar una versión mínima de iPadOS sin medir el pin/dependencias; registrar navegador exacto en reporte.
No añadir otra librería visual ni sistema Tailwind paralelo. Reutilizar tokens, icons y localización existentes; traducciones españolas para nuevas funciones y mensajes de backend.

## PWA y offline
El pin incorpora dependencias Workbox. Auditar el service worker antes de alterar su caché. No afirmar offline completo porque la app sea instalable. En primera entrega: sin escrituras offline de costes/stock; fallo de red visible y seguro. No guardar recetas privadas en cachés compartidas entre cuentas; logout limpia lo sensible. Cola offline de compras únicamente fase opcional posterior con versionado, logout, reintento y conflictos probados.

## Aceptación visual
Sin pantallas vacías, botones muertos, ejemplos hardcoded en modo real, páginas placeholder o enlaces a otra app. Cada pantalla nueva debe ser aprobada por QA visual independiente con screenshot, viewport, estado, commit y explicación del cambio.
