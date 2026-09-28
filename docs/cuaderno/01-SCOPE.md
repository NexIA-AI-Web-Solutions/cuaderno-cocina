# Producto, límites y ediciones

## Usuario y problema confirmado
Elisabeth solicita un recetario sencillo con ingredientes y precios. Hay recetas en otro programa lento; no conocemos el nombre ni formato. No asumir restaurante, TPV, contabilidad, ventas o volumen concreto. Usar ejemplos sintéticos. La app estará en español y se usará desde navegador en iPad, móvil y ordenador.

## Esencial — 500 € y 17 €/mes
Catálogo de ingredientes (Food), formatos/medidas de compra y precio manual; receta con cantidades/raciones/foto/pasos básicos/categorías; búsqueda; duplicar; coste total y por ración; cambio de comensales sin alterar el original; impresión; actualización del coste al cambiar un precio; avisos de datos incompletos; acceso privado; exportación; backups y restauración.
Criterio clave: registrar aceite 5 L / 32 €, usar 400 mL y ver 2,56 €. No exigir existencias o compras ficticias para fijar un precio.
No incluir por defecto: recepciones, contabilidad, seguimiento de stock, reservas públicas, lector de facturas, sincronización offline de escrituras.

## Profesional — 1000 € y 20 €/mes
Todo Esencial; subelaboraciones con rendimiento de salida; mermas explícitas; coste aprovechable; alérgenos declarados y estados desconocidos; fichas de producción; menús por día/servicio; reservas INTERNAS de número de comensales; suma de necesidades de varias recetas; checklist de preparación; presupuesto por persona y, cuando se use, relación coste/precio de venta.
Reutilizar MealPlan/MealType/ShoppingList de Tandoor. No calendario paralelo. Las reservas son planificación interna, no mesas, web pública, cobro, mensajería ni recordatorios externos.
La lista calculada indica NECESIDAD, no una orden de compra ni inventario real. No descontar stock al planificar.

## Integral — 1500 € y 30 €/mes
Todo Profesional; proveedores y ofertas por formato; pedidos simples y recepciones confirmadas; ubicaciones y existencias; consumos de producción y desperdicios; mínimos y lista de reposición; evolución de precios; impacto en escandallos; propuestas de compra según necesidad menos disponible; trazabilidad de autor/fecha; roles operativos.
Extender InventoryEntry/InventoryLocation/InventoryLog, no crear un almacén desconectado. Validar requisitos de ledger, idempotencia y concurrencia. Lotes/caducidad usar soporte existente si encaja; cumplimiento sanitario regulatorio NO prometido.
No incluir: TPV, ERP, contabilidad general, facturación fiscal, multiempresa comercial con autoservicio, ecommerce, OCR universal ni optimización automática nutricional.

## Funciones nativas ya presentes
Si Tandoor trae libros, notas, menús o subrecetas útiles en Esencial, no borrarlas para simular un escalón de precio. La edición define menú simplificado y flujos profesionales soportados. El servidor protege operaciones profesionales acordadas, no bloquea arbitrariamente ver/exportar datos ya existentes. Al bajar de edición: datos conservados y exportables, sin borrado automático.

## Datos y migración
Importador genérico y exportador sí forman parte del producto. Extracción del programa antiguo es trabajo separado tras muestra autorizada. No prometer que todo fichero es importable. Nunca cargar credenciales reales ni información privada en agentes/remotos.

## Instalación inicial
Una instalación por cliente; utilizar su Space y usuarios nativos. Limitar registro público y compartir por defecto. Mantener el aislamiento de Spaces incluso en instalación con un cliente. Confirmar uso de precios netos o con impuestos: el usuario debe elegir una política consistente por Space; no inferir régimen fiscal. Moneda inicial EUR, sin conversión de divisas.
