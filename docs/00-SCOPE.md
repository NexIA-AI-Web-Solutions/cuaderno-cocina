# 00 · Alcance y oferta autoritativa

## Necesidad demostrada y supuestos

Elisabeth pidió un programa sencillo con recetas e ingredientes con su precio. Después explicó que su programa actual es lento y desea preservar sus recetas. Todavía no conocemos nombre/formato del programa, número de recetas, dispositivo iPad exacto, número de usuarios, servidor o dominio. No inventar estos datos ni presentar un benchmark comparativo con ese programa. El desarrollo interno con fixtures no equivale a que la clienta haya autorizado iniciar el trabajo comercial o cargar sus datos; había pedido no avanzar hasta concretarlo.

El objetivo de ingeniería pedido por Álvaro es construir los tres niveles; la entrega comercial inicial prevista es Esencial. No confundir construir una capacidad reutilizable con regalar su activación o la migración personalizada.

## Ediciones acumulativas

| Edición | Desarrollo comunicado | Mensualidad | Qué habilita |
|---|---:|---:|---|
| esencial | 500 € | 17 € | Ingredientes, formatos, precios, recetas, coste, escalado, búsqueda, fotos, ficha básica |
| profesional | 1.000 € | 20 € | Lo anterior más subelaboraciones, mermas, fichas avanzadas, alérgenos, menús, producción, reservas internas y presupuestos/margen |
| integral | 1.500 € | 30 € | Lo anterior más proveedores, compras, movimientos de stock, pérdidas, reposición, histórico e impacto de precios y roles |

Precios tomados del WhatsApp enviado el 23/09/2026. Son contexto comercial, no tarifa calculada por la app. No añadir impuestos, descuentos, obligaciones ni facturas a la funcionalidad. Los documentos comerciales definitivos se acuerdan fuera del software.

## Esencial: historias que deben estar completas

- Iniciar sesión con cuenta individual; no acceso público ni cuentas compartidas como solución técnica.
- Crear ingrediente con dimensión (masa/volumen/unidades), formato y precio conocido o desconocido; fecha y nota.
- Crear receta con título, categoría, instrucciones básicas, raciones, cantidades, foto opcional; guardar, editar, duplicar y archivar.
- Elegir ingredientes existentes y ver el coste desglosado; una modificación del precio se refleja en las recetas relacionadas sin editar cada receta.
- Cambiar comensales para simular cantidades sin sobrescribir la receta original. Guardar como variante solo por acción explícita.
- Buscar, filtrar, paginar y abrir fichas imprimibles. Exportación de datos propios y copias restaurables incluidas como calidad básica, no función de lujo.
- Mostrar claramente recetas incompletas cuando falten precios/cantidades; no dar importes engañosos.

Esencial puede tener un propietario de la instalación; no necesita el panel de invitaciones/roles comerciales. Autenticación, autorización, protección de archivos y recuperación administrativa siguen siendo obligatorias.

## Profesional: trabajo de un servicio completo

- Subrecetas reutilizables con rendimiento y unidad de salida, sin referencias circulares.
- Mermas explícitas de limpieza/rendimiento del ingrediente y rendimiento de la elaboración, sin duplicar pérdidas.
- Menús semanales y servicios con varias recetas, raciones por receta y lista consolidada de ingredientes.
- Reservas **internas**: referencia de grupo, número de comensales, servicio, estado y capacidad. No son un portal público, plano de mesas, pagos, SMS ni reservas de habitaciones.
- Ficha completa con pasos, tiempos estimados, responsable opcional, observaciones y alérgenos verificados manualmente.
- Presupuesto por comensal aunque no se venda comida. Si se informa precio de venta comparable, mostrar contribución sobre ingredientes y porcentaje de coste, nunca beneficio neto empresarial.

## Integral: cerrar entradas y salidas

- Proveedores y sus referencias de productos; comparar formatos normalizados, no solo precio del paquete.
- Compras en borrador, recepciones parciales o completas y registro de los precios realmente pagados.
- Un almacén por instalación. Libro de movimientos inmutable con entradas, consumos, desperdicios, ajustes y compensaciones.
- Valoración operativa por coste medio ponderado; no contabilidad fiscal ni gestión de lotes/caducidades.
- Lista sugerida de compra = necesidades previstas menos stock registrado, con faltantes y mínimos; nunca emitir pedidos sin decisión humana.
- Histórico de precios y recetas afectadas; consultas sobre stock y desperdicio con filtros por fechas.
- Roles individuales: responsable, cocina y consulta. Los permisos se comprueban en servidor.

## Fuera de esta entrega

OCR/IA, conexión a ERP/TPV/banco, facturación fiscal, cobros de suscripciones, traducciones múltiples, multi-centro, tienda pública, sincronización offline, nutrición médica, recomendaciones para alergias, control sanitario certificado, extracción del programa antiguo sin muestras/autorización, SLA 24/7.

La importación genérica se desarrolla y se prueba con datos sintéticos. La migración del programa real necesita diagnóstico posterior; no promete éxito ni precio de 100 € sin examinar el formato.

## Supuestos y límites configurables

EUR; interfaz `es-ES`; fechas de cocina en `Europe/Madrid`; una organización/almacén por instancia; bajo número de usuarios concurrentes. El número comercial de usuarios o recetas no se limita arbitrariamente en código. Se aplican topes de tamaño/filas por solicitud para seguridad y rendimiento, documentados.

La interfaz de Esencial no enseña inventario o pantallas bloqueadas a modo de publicidad. El operador activa la edición en configuración servidor; no hay selector público para autoascender. Una bajada de edición no destruye datos, y la exportación del propietario conserva información existente.
