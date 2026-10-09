# Cuaderno Cocina: funciones principales y comparación con alternativas

## Estado actual: V12 admitida en producción

La [CI oficial V12 37905852791](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37905852791) completó **9/9 jobs SUCCESS**: **626 casos raíz, 742 bajo `/cuaderno-cocina/` y 9 de cantidades, 1.377 PASS**, más **17 registros G7** con cadena verificada offline. Frontend: 395 pruebas y TypeScript/build PASS; backend Cuaderno: 620; nativo: 1.296 y 21 subpruebas; tooling: 463 Python y 11 Node. Estas cifras corresponden a V12 y no suman campañas históricas.

La fuente congelada es `643e37ada841b182890daf77790e3e21768d5952`, SHA `9205105e02bccdb45ff5cc6048720e2a293532b660db2c3ee46e52394f52623b`. La imagen local atestada `sha256:0f2cb8a04379038b907b1f7de95c56cd372e3fc277c7d3d1f4becc276fcd3ee3` está saludable en el web `33de2a64d5054a05c67130a5971b9b6d086ca92ebde7214e550ee609ea69cb88`; la base persistente se conserva. El ID de configuración del archivo de CI es distinto: `sha256:edf352177c7cc470589326fd6b686177380c31198972d2d7e3b9d07be6185b21`.

La aceptación anónima aprueba **4 casos y 12 PNG**; se inspeccionaron dos login originales. Cantidades aprueba nueve cuentas/cuatro anchos, con **180 PNG originales** y **24 tarjetas revisadas manualmente**, hashes y dimensiones concordantes. La copia OLD y su restauración aislada pasan. El deployer original conserva su **FAIL** en `new-web-healthy`; la continuación separada **PASS** instaló únicamente wrapper/unit de backup y recargó systemd, sin recrear web ni mutar DB o entorno. La frescura OLD se refiere al inicio real del despliegue original, no al momento de la continuación.

**Producción V12 admitida el 9 de octubre de 2026 a las 11:49:25 UTC.** El recibo separado `consulta-v12-final-production-admission.json`, SHA `6bd0ac7d5474098604d30ad5f2e675fe8a8791190676d0cdae7528044949613d`, declara `production_admitted=true`. La observación final del host PASS conserva su propio campo de admisión false y queda vinculada por SHA `e7dabf4fdf7c44cf31f98267f4e88827aab10eeb6526b1de9ee2b4783544739d`; no se alteran los recibos previos.

La campaña pública V3 completó **diez cuentas, tres Consulta, veinte comprobaciones anónimas y trece PNG**, sin errores de navegador ni infracciones de red; collector SHA `b23b6adaf62102477e426ccf26f18faacb6fd9e343e1a9e4e6e31285a01fb7a9`. Se revisaron sus seis originales Consulta a 1440×900. La copia coherente NEW `20261009T113538Z-73dff108e3a0` y el restore nativo aislado PASS verificaron **123 tablas, 330 migraciones, filas, media y 119 secuencias**. El fingerprint DDL figura no comparado; no se afirma esa verificación.

El cierre conserva la DB, **27 recursos propios de clon detenidos**, **19 contenedores ajenos exactos** según sus baselines tipados y Caddy con seis sitios activos y sus 220 pins. El timer está habilitado, activo/en espera y su servicio inactivo. En el boot actual `46317f80-a29d-4877-9072-43038cb02eed`, la observación completa y la ventana desde el despliegue registran cero OOM; los seis más tres OOM históricos permanecen separados, sin afirmación entre arranques ni atribución de actor. El espacio libre puntual final fue 3.696.984.064 bytes, aproximadamente 3,44 GiB.

La etiqueta anotada [production-20261009-643e37a](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/tree/production-20261009-643e37a) está publicada y verificada remotamente: objeto `3b0e1f84e2fe94b21bfb40b7504f66361855ae38`, destino `643e37ada841b182890daf77790e3e21768d5952`. V1/V2 y probes conservan sus resultados originales; el PASS completo V3 no demuestra la causa de los fallos anteriores y conserva los mismos criterios.

El benchmark V12 mide p95 de formatos **125,726 ms**, movimientos **87,549 ms**, servicios **93,939 ms** y escandallo **23,612 ms**, dentro de listas **800 ms** y escandallo **300 ms**. Es DRF APIClient en proceso, cinco usuarios por tres rondas, PostgreSQL 16.15 sin JIT, Python 3.13.16/Django 5.2.17 y cuatro CPU visibles; no mide Internet, LCP/INP ni dispositivos físicos. Los registros históricos posteriores conservan su candidato y fecha; este cierre sustituye sus afirmaciones de estado actual; las limitaciones operativas configuradas siguen vigentes.

Informe de producto basado en investigación consultada el **9 de octubre de 2026**. El catálogo se refiere a la fuente V12 congelada y admitida. V8 conserva diez accesos históricos aprobados; el runtime actual V12 completó su propia campaña pública, copia NEW, restore, host y admisión final. Contenido publicable; las funciones probadas corresponden a las campañas identificadas en sus evidencias, con sus límites de alcance.

## Método y alcance

Se consultaron páginas oficiales de cinco productos: Tandoor Recipes, Paprika, meez, Apicbase y MarketMan. Sus funciones son declaraciones documentadas por cada fabricante, no resultados de una evaluación independiente ni de pruebas de sus productos. Las tarifas son las visibles al consultar esas páginas; no se compró ni contrató ningún servicio. No se equiparan monedas, impuestos, promociones, implantación, soporte, número de usuarios ni cobertura funcional. Que una función no aparezca en las páginas consultadas no demuestra que el competidor carezca de ella.

## Funciones de Cuaderno Cocina con respaldo de implementación y pruebas

Cuaderno Cocina amplía Tandoor, conservando su recetario y sus modelos de planificación y compra. La documentación del producto define tres ediciones acumulativas y tres roles, Consulta, Cocina y Responsable. El selector de edición configura funciones del espacio; no es una pasarela de cobro ni un sistema de suscripciones.

| Función principal | Esencial | Profesional | Integral |
|---|---|---|---|
| Recetario, búsqueda, edición de pasos y cantidades exactas | Sí | Sí | Sí |
| Ingredientes, unidades y formatos de compra con precio manual | Sí | Sí | Sí |
| Escandallo total y por ración | Sí | Sí | Sí |
| Fotos adicionales, favoritas personales y variantes vinculadas | Sí | Sí | Sí |
| Ocho declaraciones dietéticas manuales y estado desconocido visible | Sí | Sí | Sí |
| Calendario de una a cinco semanas y listas de compra | Sí | Sí | Sí |
| Tipos de plato dentro de cada comida (extensión Cuaderno), plantillas reutilizables y filtro dietético | — | Sí | Sí |
| Eventos y ausencias del equipo | — | Sí | Sí |
| Impresión individual vertical u horizontal de menús | — | Sí | Sí |
| Impresión conjunta de entre uno y cinco menús | — | Solo uno | Sí |
| Editar rendimiento, merma y alérgenos propios de Cuaderno | Consulta de datos existentes | Sí | Sí |
| Editar precio de venta y presupuesto por persona | Consulta de datos existentes | Sí | Sí |
| Servicios internos, preparación, confirmación y producción | — | Sí, sin movimientos de stock | Sí, con consumo controlado |
| Proveedores, ofertas, pedidos y recepciones | — | — | Sí |
| Movimientos Cuaderno, mínimos y propuesta de reposición | — | — | Sí |
| Importación/exportación y JSON Cuaderno | Sí | Sí | Sí |
| PWA instalable; copia y recuperación de la instalación | Infra común | Infra común | Infra común |

Los planes son acumulativos; los permisos de rol, hogar, espacio y privacidad se aplican además de la edición. El inventario nativo conserva sus permisos heredados; no está bloqueado íntegramente por un paywall Integral. El historial e impacto de precios conservan lectura por API en las tres ediciones, aunque el catálogo comercial sitúe su flujo en Integral. Consulta conserva favoritas personales y algunas reglas nativas de propiedad: no equivale a una prohibición global de toda escritura. Véase el [informe técnico detallado](INFORME_TECNICO_FUNCIONES_Y_PLANES_20261009.md) para los límites de cada acción y referencias de código.

La suite de navegador de la campaña V4 histórica completó **599 casos**, con ejecución de proyectos en Chromium, Firefox y WebKit, además de pruebas PostgreSQL, frontend y contrato de API. Este dato indica el alcance de esa campaña concreta; no demuestra ausencia universal de bugs. Los escenarios comprueban persistencia, límites por edición y permisos por rol, incluyendo planificación, dietas manuales, variantes, fotografía e impresión. La corrección de cantidades incluye pruebas de edición nativa sin pérdida decimal, rechazo de entradas inválidas y normalización de coma decimal; su evidencia adicional V8 se detalla a continuación, sin sustituir la aceptación pública pendiente.

La campaña V6 completó **599/599 casos en raíz y 715/715 bajo el prefijo**. La prueba dedicada de cantidades terminó con **8/9 pruebas aprobadas y un fallo de agregación**: se rechazó la validación de dimensiones de los PNG en los registros de las nueve cuentas. Se conservaron 36 capturas de panel y 144 de tarjeta. La inspección manual de 24 tarjetas originales mostró las cantidades mínima y máxima completas en las tres ediciones y cuatro anchos, con los controles visibles; esa revisión no cambia el resultado fallido de la campaña.

El candidato V7 mantuvo las funciones de V6 y corrigió la comprobación de dimensiones de capturas con 15 pruebas específicas. Su CI terminó fallida: **599/599 casos en raíz y 714/715 bajo el prefijo**, con un fallo Firefox en la espera de carga global antes de abandonar la ficha de una favorita. Cantidades **no se ejecutó**. G7 V7 completó **17 registros PASS**, incluidos los 599 casos en raíz; ese resultado no convierte el fallo del prefijo ni la falta de campaña de cantidades en una aceptación global. La imagen V7 nunca se cargó ni desplegó en el servidor de producción.

V8 conserva la aplicación V7 y completa las esperas del harness en las entradas y recargas autenticadas, distinguiéndolas de las transiciones SPA. Sus 13 pruebas nuevas reproducen la carga tardía: contra el código V7 original dieron **5 PASS y 8 FAIL**; con V8, el conjunto de pruebas puras dio **62 PASS, 0 FAIL y 0 SKIP**, y TypeScript E2E terminó sin diagnósticos. La **CI V8 completó 9/9 jobs SUCCESS**: **599/599 casos en raíz, 715/715 bajo el prefijo y 9/9 de cantidades, 1323 PASS sin fallos ni skips**. G7 V8 reunió **17 registros PASS**, con la cadena de evidencia verificada offline. G7 V6 cancelado y G7 V7 aprobado se conservan como campañas históricas distintas.

La campaña de cantidades V8 conserva **180 PNG originales**, 36 de panel y 144 de tarjeta. Se inspeccionaron manualmente 24 tarjetas originales de los tres responsables y cuatro anchos: las cantidades mínima y máxima aparecen completas, sin recortes ni controles superpuestos visibles. Hashes, bytes y dimensiones coinciden con los reportes y el ZIP. Esta muestra no constituye una evaluación de contraste, accesibilidad o todas las pantallas.

V8 se desplegó el **9 de octubre de 2026 desde las 05:01 UTC**, sustituyendo a `c79`, con la fuente e imagen identificadas en el informe técnico. La comprobación pública anónima aprobó cuatro anchos y produjo 12 capturas. La bienvenida del espacio principal guardó sus dos flags de configuración mediante el botón nativo «Saltar» y PATCH 200, con los demás datos preservados según comparación nativa; ese recorrido falló posteriormente en `home-ready` y no se declara aprobado. **La campaña posterior de diez cuentas V8, la nueva copia con restore nativo aislado y la observación del host terminaron PASS; la admisión final de V12 se completó a las 11:49:25 UTC con evidencias propias.**

V12 mejora el flujo de Consulta: oculta Crear/Importar en la portada y navegación y oculta Editar, Duplicar y Crear variante en la ficha. Las URL directas explican el permiso requerido, ofrecen volver a recetas y no muestran formularios mutadores; se conserva la exportación JSON Cuaderno de lectura. Cocina y Responsable mantienen sus formularios autorizados. La UI espera una membresía activa única del espacio y vuelve a verificarla antes de guardar/importar, sin sustituir la seguridad del servidor ni eliminar las favoritas personales. Estas funciones están implementadas en la fuente V12; su campaña pública V3 ha aprobado diez cuentas, incluidas las tres Consulta, con cero errores e infracciones. Tras el reinicio externo observado hacia las 06:31 UTC, la observación previa a la admisión registra cero OOM en ese arranque y conserva los nueve históricos de arranques anteriores. Ese dato puntual no acredita un host sin incidentes ni la aceptación final.

Los candidatos V9 y V10 se conservaron rechazados: V9 falló por una dependencia real ausente en el harness de impresión (394/395 pruebas); V10 aprobó 395/395 y falló TypeScript por no estrechar explícitamente una membresía posiblemente ausente. V11 corrigió ambos puntos y aprobó los jobs previos de su CI 37899361033, pero el navegador terminó con **617 PASS y 9 FAIL en raíz; 733 PASS y 9 FAIL bajo el prefijo**. Fallaron los nueve casos Consulta al analizar el cuerpo vacío observado de una respuesta de exportación, aunque constaban GET 200 y descarga blob; cantidades no se ejecutó. No se desplegaron esos candidatos. V12 conserva la aplicación y verifica el archivo descargado real, la preparación de portada y el título responsive. Sus 14 regresiones locales pasan y TypeScript E2E no presenta diagnósticos; **la CI V12 y su aceptación pública están aprobadas; la admisión de producción se completó a las 11:49:25 UTC**. No se suman los 1323 casos V8 como si fueran resultados V12.

Los estados dietéticos son **no declarado**, **apto declarado manualmente** y **no apto declarado manualmente**. Un dato desconocido permanece desconocido. No se presenta esa información como diagnóstico, garantía sanitaria ni cálculo automático de seguridad alimentaria. Planificar necesidades tampoco implica consumir stock.

Fuentes del producto: `docs/cuaderno/01-SCOPE.md`, `docs/cuaderno/09-FUNCTIONAL-PLANS.md`, `tests/cuaderno/e2e/acceptance.spec.ts`, `functional-extensions-acceptance.spec.ts`, `ingredient-quantity-precision.spec.ts` y `browser-acceptance.spec.ts`. La implementación final, el detalle de directorios y el estado de producción pertenecen al informe técnico del release.

## Alternativas y funciones publicadas

### Tandoor Recipes

La web oficial documenta recetas, búsqueda, espacios compartidos con permisos, listas sincronizadas, planificación, importación y cálculo de propiedades de ingredientes, incluidos precios. También ofrece instalación gestionada por el propio usuario. Estas capacidades se solapan directamente con la base de Cuaderno Cocina: compartir, planificar o calcular un precio no son exclusividades de nuestra ampliación. [Funciones y alojamiento de Tandoor](https://tandoor.dev/).

La misma página muestra alojamiento Free, Basic, Standard y Premium AI con límites de miembros, recetas o almacenamiento. Véanse las tarifas en la tabla siguiente. La opción self-host exige gestionar la instalación; no debe confundirse software gratuito con coste operativo cero. [Planes de Tandoor](https://tandoor.dev/).

### Paprika

La versión comercial presentada en su web permite organizar recetas, importar desde la web, generar listas que agrupan ingredientes, planificar comidas, escalar cantidades y sincronizar dispositivos. Cada versión de plataforma se vende por separado. [Funciones de Paprika](https://www.paprikaapp.com/).

Paprika 3 para Windows conserva datos localmente y admite uso sin conexión; su sincronización está incluida en la compra. No se verificó un precio monetario actual en esa página. [Paprika 3 para Windows](https://www.paprikaapp.com/windows/).

Es relevante distinguir la versión estable de **Paprika 4 en beta abierta**, anunciada el 28 de septiembre de 2026: añade escaneo de recetas, importación social, cuentas familiares, ubicaciones de despensa y otras funciones. El anuncio indica que las funciones premium requerirán suscripción tras la beta; no fija aquí una tarifa final. No describir Paprika de forma general como un producto sin suscripción. [Anuncio oficial de Paprika 4](https://paprikaapp.com/news/2026/09/28/paprika-4-is-now-in-open-beta/).

### meez

La página oficial distingue Starter, Pro, Premium y Enterprise. Starter incluye recetas y libros, escalado/conversión, rendimientos y coste básico. Pro añade gestión de inventario. Premium incluye un flujo de costes actualizado desde facturas y conexiones con sistemas de gestión; Enterprise añade integraciones y analítica. Esto confirma solapamiento profesional en costes, recetas y operaciones. No demuestra que los resultados de coste sean equivalentes a los de Cuaderno ni que nuestra aplicación implemente sus integraciones. [Funciones por plan y tarifas de meez](https://www.getmeez.com/pricing).

### Apicbase

Sus planes Growth, Professional y Enterprise se orientan a operaciones con varios establecimientos. Growth publica gestión de recetas e ingeniería de menús, compras, inventario y analítica; Professional incorpora previsión de demanda y opciones adicionales de gestión. Planificación de menús, producción, trazabilidad y otras capacidades aparecen como complementos. La página no ofrece un importe monetario verificable en el contenido consultado: invita a contactar al equipo comercial. [Planes de Apicbase](https://get.apicbase.com/pricing-plans/).

La ayuda oficial del cálculo de coste contempla ingredientes, desperdicio, costes de personal/producción y cálculo de precio objetivo. No se debe afirmar que Cuaderno inventa el escandallo con mermas ni que ofrece toda esta cobertura. [Cálculo de coste en Apicbase](https://support.apicbase.com/help/food-cost-calculation).

### MarketMan

La página canónica de precios documenta coste de recetas, comparación real/teórica, desperdicio, conexiones con proveedores y procesamiento de facturas; Growth añade pedidos por receta y automatizaciones. Su página de producto describe cálculo por ración basado en compras/inventario, subrecetas y actualización del coste al cambiar precios. [Planes de MarketMan](https://www.marketman.com/pricing-for-restaurant-inventory-management-system), [Coste de recetas](https://www.marketman.com/platform/recipe-costing-software).

Estas funciones representan un alcance de gestión de restaurante más amplio que el compromiso actual de Cuaderno. No se trasladan a nuestra aplicación sus capacidades de OCR, integraciones TPV, contabilidad o automatización de proveedores.

## Precios publicados y condiciones observadas

| Producto | Tarifas verificadas en las fuentes citadas | Condiciones importantes |
|---|---|---|
| Tandoor | Free 0 €/mes; Basic 1,99 €/mes; Standard promocionado 3,49 €/mes, precio mostrado anterior 4,49; Premium AI promocionado 4,99 €/mes, anterior 6,49. | Facturación mensual; límites distintos por plan; la web declara permanente el descuento mostrado. [Fuente](https://tandoor.dev/). |
| Paprika | Sin importe actual verificado para esta comparación. | Compra separada por plataforma en la oferta existente; Paprika 4 sigue en beta y anuncia posterior suscripción premium sin tarifa final verificada aquí. [Oferta](https://www.paprikaapp.com/), [Beta](https://paprikaapp.com/news/2026/09/28/paprika-4-is-now-in-open-beta/). |
| meez | Starter 24 USD/mes, o 19 USD/mes con pago anual; Pro 119 o 89; Premium 199 o 179; Enterprise personalizado. | Los importes reducidos son equivalentes mensuales con facturación anual. Hay complementos y condiciones de dispositivos/conexiones. [Fuente](https://www.getmeez.com/pricing). |
| Apicbase | Importe no publicado/verificado en la página consultada; contacto comercial. | Planes por alcance y establecimientos. [Fuente](https://get.apicbase.com/pricing-plans/). |
| MarketMan | Starter 249/mes; Growth 299/mes; Enterprise desde 449, según los símbolos monetarios publicados. | La página utiliza «$» sin especificar aquí moneda contractual; Enterprise y complementos requieren revisar la oferta concreta. Se tomó la página canónica, no páginas de campaña con otras tarifas. [Fuente](https://www.marketman.com/pricing-for-restaurant-inventory-management-system). |
| Cuaderno Cocina | Esencial 500 € iniciales + 17 €/mes; Profesional 1.000 € + 20 €/mes; Integral 1.500 € + 30 €/mes. | Importes ofertados en la documentación del producto; no se ha verificado aquí un proceso de contratación o cobro. Fuente: `docs/cuaderno/09-FUNCTIONAL-PLANS.md`. |

No procede afirmar «el más barato»: hay pagos iniciales, monedas, cobertura y modalidades diferentes. Tampoco se ha calculado un ahorro operativo, un retorno de inversión ni un coste total de propiedad.

## Claves del producto para comunicar al cliente

| Clave | Qué aporta hoy | Plan mínimo del flujo |
|---|---|---|
| Una ficha de receta conectada al trabajo de cocina | Ingredientes, cantidades, formatos, coste y planificación comparten los modelos de la aplicación. Se conservan importación y exportación. | Esencial |
| Trabajo por responsabilidad | Responsable, Cocina y Consulta operan dentro de su espacio, con privacidad y permisos de objetos. El rol y el plan son dimensiones separadas. | Esencial |
| Cantidades precisas y correcciones comprensibles | La edición preserva cantidades decimales; la coma decimal se normaliza y los valores inválidos se rechazan con un mensaje sin guardar datos corruptos. | Esencial |
| Dietas con estados explícitos | La declaración manual distingue desconocido, apto declarado y no apto declarado, evitando convertir ausencia de información en una afirmación de aptitud. | Esencial |
| Del menú a la preparación | Plantillas, tipos de plato, eventos, ausencias, impresión y servicios internos organizan el trabajo del equipo. | Profesional |
| Del pedido al stock utilizable | Un pedido todavía no aumenta existencias; la recepción confirmada y la producción generan los movimientos correspondientes. Las reversiones conservan historia. | Integral |
| Instalación bajo control del propietario | Esta entrega funciona en su servidor con PostgreSQL y copias completas verificables. Las funciones centrales funcionan con IA y conectores externos desactivados. | Infraestructura común |

Estas claves describen el encaje y la implementación de Cuaderno. Frente a los productos investigados, la propuesta se centra en una cocina que necesita esos flujos en español y una instalación propia. Son diferencias de alcance y configuración; no constituyen una prueba de exclusividad ni superioridad frente a todos los competidores.

## Diferenciación defendible e hipótesis a validar

**Hechos sobre el producto:** Cuaderno combina una base Tandoor con flujos acordados para esta instalación, interfaz en español, tres ediciones y permisos concretos por rol. Se han implementado declaraciones dietéticas manuales con desconocidos visibles, planificación que no modifica automáticamente existencias y validación de cantidades decimales. Estas propiedades son argumentos del producto; las fuentes consultadas no prueban que sean exclusivas del mercado.

**Frente a Tandoor:** la diferenciación está en la ampliación operativa y el alcance contratado por edición, no en apropiarse de recetas, importación, listas, permisos o planificación que ya aporta la base. Hay que distinguir en el informe de código qué se reutiliza y qué se extiende.

**Frente a Paprika:** un posible encaje diferente es el trabajo web de un equipo con permisos y flujos profesionales por edición. Se trata de una inferencia de adecuación al usuario, no de una prueba de mejor usabilidad ni de una ausencia de colaboración en Paprika 4.

**Frente a meez, Apicbase y MarketMan:** un posible encaje es resolver un conjunto acotado de operaciones de una instalación sin asumir proyectos de TPV, contabilidad, OCR o una cadena multiestablecimiento. La menor extensión del compromiso puede ayudar a explicarlo al cliente, pero no demuestra menor esfuerzo de aprendizaje, mayor rapidez ni superioridad funcional.

**Mensajes que requieren evidencia adicional:** facilidad de uso con personas reales, tiempo ahorrado, rapidez frente a otros productos, seguridad superior, disponibilidad garantizada y ahorro económico. Ninguno queda probado por esta investigación o por el número de tests internos.

## Registro de consulta

Todas las páginas enlazadas se consultaron el **2026-10-09** mediante búsqueda y apertura web. Se utilizaron exclusivamente fuentes oficiales para los hechos incluidos. Las tarifas y el estado beta deben volver a comprobarse si se reutiliza este informe más adelante. Los textos son resúmenes propios; no se reproducen artículos, testimonios ni credenciales de demostración.

## Referencia técnica de esta entrega

Fuente del candidato: `643e37ada841b182890daf77790e3e21768d5952`, identidad `643e37ada841b182890daf77790e3e21768d5952+worktree.9205105e02bccdb45ff5cc6048720e2a293532b660db2c3ee46e52394f52623b`. La CI oficial V12 completó nueve jobs SUCCESS, 1.377 casos de navegador y 17 registros G7 verificados. La campaña pública V3 aprobó diez cuentas y veinte controles anónimos, sin errores ni infracciones. V12 está admitida en producción desde las 11:49:25 UTC del 9 de octubre de 2026, con copia coherente, restore aislado y observación final del host aprobados. El tag `production-20261009-643e37a` está publicado y verificado en GitHub. Los resultados de V8 permanecen históricos y no sustituyen los de V12. El código y sus anclas están detallados en el informe técnico enlazado. Los precios de nuestros planes son informativos: 500 € + 17 €/mes, 1.000 € + 20 €/mes y 1.500 € + 30 €/mes; no se han activado cobros automáticos.
