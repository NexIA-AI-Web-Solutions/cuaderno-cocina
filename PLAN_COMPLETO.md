# Cuaderno Cocina · plan completo para Codex

Versión de arranque: 28/09/2026. Este archivo reúne el plan. No es una aplicación terminada ni evidencia de pruebas de producto.

## Documentos incluidos

- `00-SCOPE.md`
- `01-ARCHITECTURE.md`
- `02-DOMAIN-CONTRACTS.md`
- `03-DATA-MODEL.md`
- `04-UX-DESIGN.md`
- `05-AGENT-ORCHESTRATION.md`
- `06-TDD-QUALITY.md`
- `07-IMPLEMENTATION-PLAN.md`
- `08-SECURITY.md`
- `09-IMPORT-MIGRATION.md`
- `10-PERFORMANCE-STORAGE.md`
- `11-DEPLOY-BACKUP.md`
- `12-DEFINITION-OF-DONE.md`
- `13-COMMERCIAL-BOUNDARIES.md`
- `14-SOURCES.md`
- `15-DEPENDENCIES-LICENSES.md`



---

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


---

# 01 · Arquitectura y decisiones técnicas

## Stack elegido

| Capa | Elección | Razón de diseño |
|---|---|---|
| Runtime | Node.js 24 LTS, parche mantenido | Una sola plataforma Windows/Linux y menos runtimes |
| App | SvelteKit + Svelte, versiones estables compatibles | Servidor y UI en un repositorio; renderizado servidor y formularios con mejora progresiva |
| Lenguaje | TypeScript `strict` | Contratos compartidos, errores antes del despliegue |
| Estilo | Tailwind CSS estable, tokens propios y componentes pequeños | CSS compilado; no kit de administración gigantesco |
| UI compleja | Primitivas accesibles mantenidas solo cuando necesarias | No reinventar foco/teclado de un diálogo o combobox |
| Datos | SQLite, `better-sqlite3` mantenido, Drizzle | Archivo local, migraciones auditables, sin servicio de BD separado |
| Acceso | Better Auth con adaptador Drizzle/SQLite | Sesiones/contraseñas de una librería mantenida; sin autenticación artesanal |
| Validación | Zod | Límites y contratos en cada entrada servidor |
| Costes | decimal.js | Precisión decimal; sin floats monetarios |
| Imágenes | sharp, si la versión tiene binarios compatibles | Redimensionar y re-codificar; no conservar fotos gigantes por defecto |
| Pruebas | Vitest, Playwright, axe | Dominio, integración, navegadores y accesibilidad |
| Publicación | adapter-node + Caddy + servicio Linux | Un proceso de app; TLS/proxy separados; sin depender de proveedor cloud |

No se incluyen versiones menores inventadas. En T001 se consultan fuentes oficiales/registro, se eligen releases no preliminares compatibles, se auditan y se fija todo con versión exacta y lockfile. Comprobar también el SQLite realmente embebido con `select sqlite_version()`; no basta instalar un paquete npm reciente.

## Por qué no elegir una arquitectura grande

No React + API Python + Redis + PostgreSQL + workers + almacenamiento remoto + IA. El problema inicial es edición de recetas y aritmética. La decisión de un monolito modular busca reducir piezas que actualizar, datos que respaldar y errores de integración. No es una afirmación de que otro framework sea lento.

Tampoco se clona un gestor gastronómico completo antes de verificar el encaje. Se reutilizan dependencias y patrones con procedencia registrada. Un fork completo obligaría a cargar su funcionalidad, licencias, actualizaciones y modelo de datos.

## Flujo

```text
Navegador / icono de inicio
       HTTPS
Caddy —> SvelteKit (Node, 127.0.0.1)
                | acciones/load con auth + validación
                v
       servicios de aplicación
          |             |
     dominio puro   repositorios SQL
                         |
                 SQLite + archivos privados
                         |
              backup coherente y verificable
```

Usar `load` del servidor y form actions; no remotes experimentales ni fetches en cascada innecesarios. La UI puede simular cálculos con el mismo dominio puro, pero el servidor recalcula y valida todo lo guardado.

## Separación

`domain/` no conoce framework ni DB. `application/` coordina casos de uso y transacciones. `server/db/` contiene esquema y consultas concretas. `routes/` adapta HTTP a casos de uso. `components/` muestra datos y recoge intención.

Interfaces de repositorio solo donde aporten un límite real: costes, persistencia y almacenamiento de imágenes. No crear veinte capas por cada CRUD.

## SQLite y crecimiento

Un proceso de app, disco local persistente, WAL, foreign keys, transacciones cortas y timeout acotado. SQLite no se comparte por SMB/NFS/OneDrive, no va en un filesystem efímero y no se replica copiando un archivo vivo. Las operaciones importación/backup se serializan con las escrituras cuando lo exija el runbook.

WAL permite concurrencia de lectores y escritor, no varios escritores simultáneos. Evitar `await` o llamadas de red dentro de transacciones de better-sqlite3. Trabajos pesados: scripts de administración o worker threads puntuales, no bloquear el event loop durante miles de filas o compresión.

Reconsiderar PostgreSQL si se necesitan varios servidores de app con escritura, alta concurrencia de cambios o multiempresa compartida. La portabilidad se facilita con servicios y exportación versionada; migrar a PostgreSQL requiere una migración probada, no se promete cambiar un string y listo.

Si ya se hubiese acordado PostgreSQL expresamente con la clienta, conservar ese acuerdo y registrar una revisión arquitectónica antes de cambiarlo. En la conversación aquí solo se propuso previamente como recomendación, no consta su aceptación.

## Runtime sin herramientas de desarrollo

Producción contiene el build y las dependencias de ejecución, no pnpm store, tests, vídeos, Chromium, fuentes de ejemplo o SDK de Codex. No imprimir PDFs ejecutando un navegador pesado en cada servidor: fichas HTML con CSS de impresión, que el navegador del usuario puede guardar como PDF.

Manifest y acceso desde pantalla de inicio son comodidad opcional. Esta versión requiere conexión para guardar; no lleva service worker que almacene recetas, sesiones o stock en caché privada. No venderlo como app offline.


---

# 02 · Contratos de dominio: lo que no puede fallar

## Representación

- Dinero de entrada: EUR, céntimos enteros no negativos para un precio de compra conocido. `null` significa desconocido; cero significa gratuito conocido, confirmado de forma explícita.
- Cantidades: strings decimales canónicos positivos, punto interno, sin separadores de millares. Máximo seis decimales para cantidades introducidas. Nunca `parseFloat` para el cálculo.
- Unidad base: `g`, `ml`, `unit`. Dimensión separada: masa, volumen, unidades. Una cantidad puede tener fracción de unidad; una cantidad de comensales es entera positiva.
- Aritmética: Decimal con precisión suficiente (por ejemplo 40 dígitos); redondear el dinero mostrado a céntimos con HALF_UP. No redondear cada término antes de sumar.
- Importes derivados pueden contener fracciones de céntimo. Persistirlos como decimal canónico o recalcularlos; no usar SQLite REAL. El valor de inventario operativo usa hasta doce decimales de céntimo y agota el residuo al consumir toda la existencia.
- Totales SQL no convierten TEXT a REAL. Para agregaciones monetarias usar representación entera acotada o el servicio decimal; comprobar límites y no pasar por Number fuera de enteros seguros.

## Localización

En formularios españoles `1,25` significa 1.25. También se acepta `1.25` sin separador de millares; `1.250` se interpreta como 1.250 decimal, nunca como mil doscientos cincuenta. Avisar junto al campo: «Sin separador de miles». Rechazar mezclas ambiguas como `1.234,56` y `1,234.56` salvo que el importador tenga locale explícito y vista previa.

EUR y formato de fecha se aplican al mostrar, no contaminan los valores almacenados. Instantes en UTC; fecha/hora del servicio según Europe/Madrid, con pruebas de cambio de hora y horas inexistentes/ambiguas. No convertir una fecha de menú en un instante por accidente.

## Coste de un ingrediente

```
precio_por_unidad_base = precio_del_formato / cantidad_base_del_formato
coste_de_linea = cantidad_base_utilizada * precio_por_unidad_base
coste_receta = suma_sin_redondeo_prematuro(coste_de_linea)
coste_racion = coste_receta / raciones_base
```

Un formato de 5 L de aceite a 32 € tiene 5.000 ml. Usar 200 ml cuesta 1,28 €. Las pruebas deben cubrir conversiones kg/g, L/ml y envases con varias unidades.

Masa y volumen NO son intercambiables. Para convertir 1 L de aceite en kg se necesita densidad explícita validada, no suponer agua; la versión inicial rechaza la conversión cruzada. «Una cebolla» no tiene peso universal: usar un peso por unidad específico documentado o mantener dimensión unidades.

Si una receta usa un ingrediente sin precio, devolver `{status: 'incomplete', knownSubtotal, missingIngredientIds}`. No mostrar un total completo o margen definitivo. Con cero conocido no aparece como faltante.

## Selección inequívoca del precio

Cada ingrediente tiene **un formato activo de referencia para calcular costes**. Aunque tenga varios envases/proveedores, la receta nunca escoge el más barato o el último de una lista de forma implícita. La pantalla de ingredientes identifica ese formato y permite cambiarlo con vista previa del precio normalizado. Editar el formato activo propaga el coste; editar otro formato no cambia los escandallos hasta seleccionarlo.

Una recepción Integral conserva su precio histórico. Puede proponer actualizar el precio de referencia, pero requiere una confirmación explícita en la recepción. Coste actual de receta, coste real de una recepción y valoración de existencias son conceptos distintos.

## Precio y actualización

Un cambio de precio incrementa su versión, registra fecha y evento mínimo, y modifica los costes actuales de sus recetas. Esencial ya tiene esta propagación. Integral añade consulta histórica y análisis de impacto, no cobra otra vez el recálculo básico.

Cargar todas las líneas/precios necesarias en pocas consultas. Si se cachea, cache por versiones y con invalidación demostrada; no comenzar con un cache distribuido.

Un menú futuro refleja precios actuales. Una producción confirmada o recepción registrada conserva snapshot/versiones de los importes usados; un cambio posterior no reescribe el pasado.

## Escalado

`factor = raciones_solicitadas / raciones_base` y cada cantidad se multiplica por ese factor. Vista previa sin mutar receta. No se redondean ingredientes a paquetes de compra en el escandallo; eso pertenece a la propuesta de compra. Raciones base y destino mayores que cero; límites explícitos; sin `NaN`, infinito o valores negativos.

Las cantidades pueden escalar linealmente. Los tiempos de horno, temperaturas y seguridad de cocción no se recalculan como si fueran cantidades; permanecen instrucciones a revisar por una persona.

## Profesional: mermas y subrecetas

Merma de ingrediente modelada como `yield = aprovechable / comprado`, en (0,1]. Si 1 kg comprado a 2 € rinde 0,8 kg limpio, 1 kg limpio cuesta 2,50 €. Cada línea declara `quantityBasis = as_purchased | usable`. Las líneas de Esencial y las importadas sin otra indicación se conservan como `as_purchased`. Solo una línea marcada «producto aprovechable» (`usable`) divide por yield para calcular compra necesaria. Si la cantidad ya representa producto comprado, no volver a aplicarle la merma. Cambiar esta base requiere una acción explícita con vista previa; activar Profesional no reinterpreta recetas existentes en silencio.

La salida de una elaboración tiene su propia cantidad/unidad de rendimiento. Una salsa que cuesta 10 € y produce 2.000 g cuesta 0,005 €/g. 300 g en otro plato aportan 1,50 €. No aplicar otra vez las mermas de los ingredientes cuando se inserta esa salsa.

Grafo dirigido acíclico: impedir autorreferencias, A→B→A y ciclos largos dentro de la transacción. Límite de profundidad inicial 10 con error explicado; memoización de subárboles. Propagar precios faltantes e ingredientes/alérgenos transitivos, sin inferir seguridad para consumidores.

No admitir recetas vinculadas como subelaboraciones en Esencial por importación o endpoint directo si esa capacidad no está habilitada. La exportación de datos previamente existentes no se destruye al bajar de edición.

## Menús, producción y reservas internas

Servicio tiene fecha, nombre, capacidad opcional y platos con raciones explícitas. Reserva es un grupo/referencia interna con plazas y estado (pendiente, confirmada, cancelada). Las plazas confirmadas actualizan previsión de comensales sin duplicarla con un contador manual. Elegir una única fuente por servicio: `manual` o `reservations`; no sumarlas indiscriminadamente.

Planificar no mueve stock. Confirmar producción en Integral sí crea consumo. Necesidades consolidadas explotan subrecetas y suman ingredientes base, sin descontar dos veces una subelaboración y sus ingredientes. No se inventa inventario de producto terminado en esta entrega.

## Presupuesto y rentabilidad

Siempre disponible en Profesional: comparar coste por ración con presupuesto objetivo. Si no hay precio de venta, no mostrar «beneficio».

Para venta, todos los importes se comparan en la misma base elegida (neta o con impuestos incluidos); no asumir situación fiscal ni calcular IVA por su cuenta. Contribución sobre ingredientes = precio comparable − coste ingredientes. Porcentaje de coste = coste / precio ×100. No incluye salarios, energía, alquiler o resultado contable. Cero/desconocido en venta no produce divisiones inválidas.

## Integral: existencias y valoración

Movimientos append-only: opening, receipt, consumption, waste, adjustment, reversal. Cantidad firmada; referencia/actor/instante y motivo. No editar/eliminar movimientos confirmados: registrar compensación.

Stock disponible = suma de movimientos válidos. No admitir saldo negativo por defecto. Comprobar saldo y escribir el movimiento en la MISMA transacción (`BEGIN IMMEDIATE` o equivalente probado). Conflictos se responden con estado recuperable, no perdida silenciosa.

Coste medio ponderado operativo: 10 kg a 2 €/kg + 10 kg a 4 €/kg = 20 kg valorados en 60 €, media 3 €/kg. Consumir 5 kg baja 15 €, quedan 15 kg/45 €. Desperdiciar 2 kg baja 6 €, quedan 13 kg/39 €. No recalcular ese valor histórico con el último precio de catálogo.

Cuando el saldo se agota exactamente, retirar todo el valor residual para no dejar céntimos fantasma. No introducir ajustes contables fiscales. Un ajuste de inventario requiere motivo y valoración explícita para entradas no compradas.

Compras: pedir no equivale a recibir. Recepción parcial crea movimientos solo de las cantidades recibidas. Idempotencia obligatoria por operación; reintentar la misma recepción/producción no duplica stock. Claves únicas servidor, no confiar solo en desactivar un botón.

Anular una entrada ya consumida puede dejar saldo imposible: bloquear y exigir corrección operativa explícita; no forzar negativos para hacer pasar el test. Registrar eventos conservando trazabilidad.

Propuesta de compra normalizada: `max(0, necesidad − disponible)`, después empaquetado redondeado al alza según proveedor. Si faltan equivalencias entre dimensiones, producir una incidencia a revisar, no un número supuesto. Es una propuesta, no una orden enviada.

## Concurrencia y borrado

Receta/ingrediente tienen `version`. Editar exige expectedVersion: si alguien guardó antes, devolver conflicto 409 y conservar ambos cambios para revisión. Archivar un ingrediente referenciado no borra el pasado. Reemplazar requiere acción explícita y transacción.

Invariantes de actor, edición y rol en servidor para importaciones, descargas, lecturas de importes, endpoints y jobs, no solo botones de UI.


---

# 03 · Modelo de datos y estructura del repositorio

## Tablas sugeridas (migraciones incrementales)

| Bloque | Tablas | Invariantes principales |
|---|---|---|
| Acceso | Tablas oficiales de Better Auth; user_profile | Sesión protegida, rol separado, sin contraseñas propias |
| Instalación | kitchen_settings | Una instalación, moneda, base comparable de precios, edición servidor |
| Ingredientes | ingredient, purchase_format, ingredient_price_event | Dimensión estable; cantidad positiva; precio null distinto de cero |
| Recetas | recipe, recipe_line, category, recipe_category, media_asset | Versionado, referencia existente, orden, archivado |
| Profesional | recipe_yield, allergen, ingredient_allergen, service, service_recipe, internal_reservation | DAG sin ciclos, servicio con fuente de comensales única |
| Integral | supplier, supplier_product, purchase, purchase_line, receipt, receipt_line | Unidades comparables, recepción idempotente y parcial |
| Stock | stock_movement, stock_balance | Ledger autoritativo; balance derivado verificable; saldo no negativo |
| Operación | import_batch, import_mapping, audit_event, idempotency_record | Procedencia, permisos y resultados trazables |

No crear todas las tablas el primer día. Core en G1/G2, Profesional en G3, Integral en G4. El motor de licencias no es una tabla de pagos; la edición se configura por servidor.

Cada tabla nueva tiene migration SQL revisada, pruebas de upgrade y referencia de su contrato. Auth usa el esquema que genere la versión instalada de Better Auth, no una copia antigua inventada.

## Campos clave

`ingredient`: id UUID, name, normalized_search_name, dimension, active_cost_format_id, archived_at, version.
`purchase_format`: id, ingredient_id, label, amount_decimal, unit, price_cents nullable, price_known, updated_at, version. Restricción evita combinaciones null/known incompatibles.
`recipe`: id, title, normalized_search_title, base_servings, preparation_text, photo_id nullable, archived_at, version.
`recipe_line`: id, recipe_id, ingredient_id XOR child_recipe_id, amount_decimal, unit, quantity_basis, position. child_recipe_id solo Profesional.
`media_asset`: opaque id, private storage key, content hash, dimensions, byte length, MIME verificado, creator.
`stock_movement`: id, ingredient_id, quantity_delta_decimal, value_delta_decimal, event_kind, source_type/id, idempotency_key, actor_id, occurred_at, reason, reversal_of nullable.

Tipos monetarios y cantidad se basan en `02-DOMAIN-CONTRACTS.md`, no en comodidad de un ORM. SQL CHECK y servicios deben reforzarse mutuamente. Índices para FK, filtros por fecha, búsqueda normalizada, referencias de importación y claves únicas de idempotencia.

## Estructura objetivo

```text
cuaderno-cocina/
  AGENTS.md
  README.md
  .agents/skills/<skill>/SKILL.md
  .codex/config.toml
  .codex/agents/*.toml
  docs/
  tooling/
  examples/
  src/
    app.html
    hooks.server.ts
    lib/
      domain/
        quantities/ money/ costing/ recipes/ planning/ inventory/
      application/
        ingredients/ recipes/ services/ purchasing/ stock/ imports/
      server/
        auth/ db/schema/ db/repositories/ storage/ audit/ permissions/
      components/
        ui/ layout/ ingredients/ recipes/ planning/ inventory/
      validation/
      i18n/es.ts
      styles/tokens.css
    routes/
      (public)/acceso/
      (app)/+layout.server.ts
      (app)/recetas/
      (app)/ingredientes/
      (app)/planificacion/
      (app)/compras/
      (app)/inventario/
      (app)/ajustes/
      media/[id]/+server.ts
      exportar/+server.ts
      health/ready/+server.ts
      api/auth/[...all]/+server.ts
  drizzle/
  tests/
    unit/ integration/ e2e/ security/ fixtures/ performance/
  scripts/
    setup-local.ts seed-demo.ts backup.ts restore.ts import.ts export.ts
  deploy/
    Caddyfile.example cuaderno-cocina.service.example
  .github/workflows/ci.yml
  package.json
  pnpm-lock.yaml
  svelte.config.js
  vite.config.ts
  tsconfig.json
  playwright.config.ts
  vitest.config.ts
```

Las carpetas vacías no se crean para aparentar progreso. Se materializan al implementar cada módulo. Un repositorio y un package.json; no monorepo de tres apps, no paquetes de negocio publicados por separado.

## Datos fuera del código

Desarrollo: `var/` ignorado por Git. Producción: `/var/lib/cuaderno-cocina/<installation>/`, con DB, media y backups en directorios separados y permisos mínimos. Una nueva release no reemplaza esos directorios.

`artifacts/` contiene evidencia sintética, no datos del cliente. No guardar binarios de Node, SQLite o navegador en Git. Exportaciones del cliente y contraseñas se excluyen con defensas de configuración y revisión, no solo .gitignore.


---

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


---

# 05 · Orquestación de agentes

## Modelos y suposiciones visibles

Líder: `gpt-5.6-sol`, esfuerzo `high` si el cliente lo admite. Implementadores: `gpt-6-astra`, esfuerzo `medium`. Esta segunda asignación interpreta explícitamente el texto «GPT 6 Medium» como Astra; no se presenta Medium como un modelo distinto. Revisor independiente: GPT-5.6 Sol high, contexto nuevo.

El usuario puede cambiar la variante GPT-6 mediante `tooling/model-routing.json` y `tools/configure-agents.mjs`. La documentación oficial y la disponibilidad del cliente instalado prevalecen sobre etiquetas coloquiales. No usar alias `gpt-6-medium`, no inventar acceso y no cambiar a Luna o a otro proveedor en silencio.

## Preflight real

Antes de implementar: identificar versión de Codex, cliente, modelo de la sesión, razonamiento, forma de descubrimiento de skills y agentes, sandbox y permisos de red. Guardar `artifacts/preflight.json` sin tokens. Abrir una tarea inocua de exploración con el worker y verificar en metadatos/UI el modelo efectivo; que el agente escriba «soy X» no constituye verificación. Verificar también que la sesión líder no ha heredado un override global distinto.

La documentación consultada el 28/09/2026 admite agentes TOML independientes en `.codex/agents/` con `name`, `description`, `developer_instructions` y overrides de modelo. Los valores del archivo tienen precedencia en el enrutamiento. No copiar a ciegas una configuración antigua de `[agents.role].config_file` si el cliente actual usa otro esquema.

Si el cliente no dispone de multiagente o de los modelos, registrar el bloqueo. Puede continuar documentación y comprobaciones locales no dependientes, pero no declarar orquestación real ni sustituir el requisito de revisión independiente. El bloqueo de modelo requiere que el propietario seleccione una variante disponible.

## Roles

| Rol | Modelo | Responsabilidad | Permisos de escritura |
|---|---|---|---|
| líder (sesión principal) | 5.6 Sol | Contratos, paquetes, integración, decisiones y release | Árbol del proyecto; dueño de archivos comunes |
| cuaderno_domain | 6 Astra medium | Cálculos, unidades, subrecetas, planificación, stock | Dominio y sus tests asignados |
| cuaderno_web | 6 Astra medium | UI, rutas, formularios y responsive | Componentes/rutas asignadas |
| cuaderno_data_ops | 6 Astra medium | SQL, importación, imágenes, backup/deploy | Rutas explícitas del paquete; propone migraciones |
| cuaderno_qa | 6 Astra medium | E2E, accesibilidad, benchmarks y comprobación adversarial | Tests/evidencias, no producción salvo encargo separado |
| cuaderno_reviewer | 5.6 Sol high | Revisión independiente y bloqueos de salida | Solo lectura; el líder ejecuta comandos que escriban artefactos |

No ejecutar los cinco roles simultáneamente. Límite: dos implementadores y un revisor (tres subagentes abiertos). El líder no modifica archivos que tenga asignados a un worker. Los workers no crean subagentes.

## Paquete de trabajo mínimo

Antes de delegar, el líder usa `tooling/WORK_PACKET_TEMPLATE.md`: objetivo observable, contrato, dependencias, rutas que puede tocar, rutas prohibidas, pruebas RED/GREEN, casos límite, criterios de aceptación y entrega. Tarea corta por flujo vertical, no «construye todo el backend».

Cada worker entrega un resumen de archivos, pruebas ejecutadas con código de salida, evidencia del fallo esperado, resultado verde, riesgos y decisiones no resueltas. Una lista de tareas marcadas no sustituye pruebas reales.

## Evitar conflictos

Usar worktrees/ramas locales si el cliente los admite dentro de su sandbox. No compartir la DB de desarrollo entre workers: cada uno tiene DB temporal y puerto propios. El store del gestor de paquetes puede compartirse sin copiar node_modules entre sistemas operativos.

Si no hay worktrees, usar asignación exclusiva de rutas y ejecutar secuencialmente paquetes que se solapen. No simular aislamiento. Esquema/migrations, package.json, lockfile, config común y CSS global los integra el líder. Los workers proponen cambios acotados para esos archivos, no los reescriben en paralelo.

## Ciclo por paquete

1. Líder comprueba dependencias y lee contrato.
2. Worker escribe una prueba semántica y demuestra RED por fallo esperado.
3. Implementa mínimo, obtiene GREEN, refactoriza.
4. QA o líder ejecuta pruebas afectadas en árbol integrado.
5. Reviewer nuevo inspecciona contrato, diff, pruebas y evidencias; emite hallazgos con severidad y ruta.
6. Worker corrige; reviewer comprueba correcciones.
7. Líder integra, ejecuta verificación y actualiza estado/commit local.

Dos intentos de corrección sin progreso real: parar el bucle local, reproducir mínimo y devolver diagnóstico al líder; no gastar agentes repitiendo el mismo prompt. No convertir esta regla en abandono de todo el proyecto.

## Contexto, coste y persistencia

No todos los workers necesitan todo el plan. Darles archivos/contratos relevantes y nombres de tests. Skills usan carga progresiva. No usar modelos grandes para ordenar imports o copiar una línea que un script resuelve. Registrar fallos útiles; no versionar transcripciones privadas de modelos.

Mantener tareas separadas como NOT_STARTED, IN_PROGRESS, BLOCKED, VERIFIED. La fuente de tareas es `tooling/work-packets.json`; el progreso va en `docs/STATUS.md` con evidencia. Al compactar, escribir checkpoint del diff, commit, tests y siguiente paquete; no depende de memoria informal.

## Autoridad y límites

El prompt autoriza editar, instalar dependencias del proyecto y hacer commits locales. No autoriza facturar, publicar, extraer datos de otra cuenta, comprar hosting o cambiar producción. Las credenciales/clientes antiguos son bloqueos externos; no hacen falta para construir y verificar la app con datos sintéticos.


---

# 06 · TDD, calidad y formato

## TDD operativo

Cada regla comienza como test del comportamiento esperado. La prueba RED debe fallar por ausencia/error de esa regla, no solo por un import roto. Guardar comando y código de salida en evidencia del paquete. Implementación mínima → GREEN → refactor → volver a ejecutar. Un test escrito después del código se identifica honestamente como test de regresión, no evidencia retroactiva de TDD.

Los mocks sirven para límites externos, no sustituyen SQLite o el navegador en los flujos que se certifican. Tests de costes usan resultados fijos revisados, no llaman a la misma función de producción para calcular el esperado.

## Capas

**Unitarias:** parser decimal es-ES, unidades, precio cero/desconocido, escalado, redondeos, DAG, mermas, contribución, necesidades de compra, ledger y claves de idempotencia. Propiedades: escalado proporcional antes de redondeo; convertir y volver recupera cantidad; stock nunca negativo; export/import estable.

**Integración:** DB SQLite temporal REAL por test suite, migrations desde cero, upgrades, restricciones, permisos de servicio, versiones concurrentes, transacciones de stock, import rollback, recepción parcial y sesión expirada. No usar la BD del desarrollador.

**E2E:** cuenta local sintética, navegador real y servidor del build, no solo servidor dev. Login, alta ingrediente, receta, guardar, reabrir, modificar precio, comprobar costes, escalar, imprimir, buscar, export/import, roles y URLs prohibidas. Repetir las rutas principales por edición.

**Seguridad:** acceso sin sesión, CSRF/origin, endpoint protegido por edición y rol, recursos privados, subidas inválidas, CSV formula injection, zip traversal/bombas, rate limit, revocación de sesión y prohibición de registro público.

**Operación:** construir desde checkout limpio; iniciar con datos persistentes; backup consistente; restore en otra carpeta; verificar integridad y saldos; migración y rollback documentado.

## Comandos que debe crear T002

| Comando | Resultado |
|---|---|
| `pnpm format:check` | Prettier check, sin modificar en CI |
| `pnpm lint` | ESLint con TypeScript/Svelte, sin warnings ignorados a granel |
| `pnpm check` | svelte-check + TypeScript strict |
| `pnpm test:unit` | Vitest dominio |
| `pnpm test:integration` | DB real aislada |
| `pnpm test:coverage` | Cobertura real con umbrales |
| `pnpm build` | Build adapter-node |
| `pnpm verify` | Format, lint, check, unitarias, integración, cobertura y build |
| `pnpm test:e2e` | Smoke Chromium en build |
| `pnpm test:e2e:release` | Chromium/WebKit/Firefox y matriz responsive |
| `pnpm test:security` | Suite de permisos, datos/archivos y abuso |
| `pnpm test:restore` | Backup y restore aislados |
| `pnpm bench` | Dataset fijo y métricas reproducibles |
| `pnpm release:check` | Agrega comprobaciones de release y manifiesto |

Scripts multiplataforma Node/tsx; no `rm -rf`, `cp` o asignaciones de variables Bash como única implementación en package.json. No usar `--passWithNoTests`. Las suites vacías deben fallar antes de declarar un módulo terminado.

## Umbrales iniciales del proyecto

Dominio: mínimo 95 % de ramas y 98 % de líneas, excluyendo solo tipos/generados con justificación. Servicios críticos (auth, edición, import, stock): mínimo 90 % de ramas. Cobertura global no permite esconder un motor sin probar. No exigir 100 % a plantillas sin sentido; cada flujo visible tiene E2E.

Sin `any` silencioso, `@ts-ignore`, errores de hidratación, warnings Svelte de accesibilidad descartados por lote o `test.skip` para el alcance obligatorio. Una excepción estrecha requiere motivo y revisión.

## Formato

UTF-8, LF, dos espacios para TS/JSON/Svelte; ancho 100; Prettier para Svelte/Markdown; imports ordenados con un único mecanismo. Español en UI, documentación y mensajes orientados al usuario. Identificadores técnicos y nombres de librerías en inglés por consistencia de ecosistema. Comentarios explican el porqué de una regla, no narran cada línea.

Funciones pequeñas con contratos explícitos; no umbrales arbitrarios de líneas usados para multiplicar archivos. Errores de dominio discriminados, errores HTTP traducidos sin filtrar SQL/rutas internas.

## CI

Crear CI con permisos mínimos, Linux + Windows para unitarias/integración/build, E2E al menos en Linux con motores requeridos. Fijar acciones a revisiones verificadas, lockfile obligatorio, caché del gestor sin secretos, artefactos de fallos con retención limitada. No instalar navegadores en la imagen de producción.

Auditar dependencias y licencias; un fallo de red se reporta, no se convierte en auditoría aprobada. Vulnerabilidad crítica/alta aplicable sin mitigación bloquea release. Una alerta no aplicable necesita evaluación documentada, no `ignore all`.


---

# 07 · Plan ejecutable de principio a fin

La fuente estructurada de tareas es `tooling/work-packets.json`. El listado siguiente explica el orden y las puertas. No hay una autorización de despliegue/compra en estas tareas. Todos los cambios usan TDD, revisión y registro de evidencias.

## Fases

G0 verifica entorno y modelo. G1 construye cimientos. G2 deja Esencial funcional, con persistencia y transferencia de datos. G3 añade trabajo por servicio. G4 conecta almacén y compras. G5 endurece rendimiento/operación. G6 cierra con navegadores, auditoría y paquete de entrega.

El checkpoint de G2 es el primer producto utilizable, pero no elimina los controles operativos finales. Para ALL_TIERS continuar automáticamente tras G2. No volver a pedir aprobación para cada CRUD.

Las dependencias habilitan paralelismo limitado: dominio y shell visual pueden avanzar por archivos distintos; migrations y lockfile permanecen bajo control del líder. Pruebas y review son parte del paquete, no una fase opcional «para más adelante».

## T001 · G0 · Preflight, modelos, versiones y riesgos

**Depende de:** inicio. **Responsable sugerido:** leader.

Inventario de entorno, modelo efectivo, dependencias oficiales y SQLite parcheado. No fabricar resultados.

**Se acepta cuando:** artifacts/preflight.json; docs/DEPENDENCY_BASELINE.md

## T002 · G1 · Scaffold y herramientas de calidad

**Depende de:** T001. **Responsable sugerido:** leader.

SvelteKit estable, Node24, lockfile, TypeScript strict, ESLint/Prettier, Vitest/Playwright y CI mínima. No borrar el handoff.

**Se acepta cuando:** Instalación limpia; test semántico inicial; build y scripts multiplataforma.

## T003 · G1 · Tipos de dinero, unidades y parser español

**Depende de:** T002. **Responsable sugerido:** cuaderno_domain.

Contratos decimales, dimensiones, nulos/ceros, conversiones, round HALF_UP y overflow.

**Se acepta cuando:** Unitarias con oráculos fijos y propiedades; sin float monetario.

## T004 · G1 · Persistencia y migraciones core

**Depende de:** T002. **Responsable sugerido:** cuaderno_data_ops.

SQLite real, Drizzle, foreign keys, WAL, private dirs, esquema mínimo y migración desde vacío.

**Se acepta cuando:** Migraciones y restricciones pasan en Windows y Linux disponibles.

## T005 · G1 · Acceso privado, sesiones y setup propietario

**Depende de:** T004. **Responsable sugerido:** cuaderno_data_ops.

Better Auth oficial, sin registro público, recuperar acceso por operador, logout y sesión revocada.

**Se acepta cuando:** Auth integrada, límites de login y acceso anónimo rechazado.

## T006 · G1 · Sistema visual y shell responsive

**Depende de:** T002. **Responsable sugerido:** cuaderno_web.

Tokens, navegación, botones/inputs/combobox accesibles, estados y estructura móvil/iPad.

**Se acepta cuando:** Capturas sintéticas, teclado, foco y ausencia de overflow global.

## T007 · G1 · Capacidades y autorización servidor

**Depende de:** T005. **Responsable sugerido:** leader.

Resolver edición acumulativa y permisos; pruebas de URL directa, import y archivos.

**Se acepta cuando:** Esencial no puede ejecutar funciones de otros tiers por endpoint.

## T008 · G2 · Ingredientes y formatos de compra

**Depende de:** T003, T004, T005, T006, T007. **Responsable sugerido:** cuaderno_web.

CRUD, búsqueda, precio desconocido/gratis, archivado, version conflict y formato claro.

**Se acepta cuando:** Alta/editar/reabrir; actualizar precio sin perder referencias.

## T009 · G2 · Motor de escandallos y recálculo

**Depende de:** T008. **Responsable sugerido:** cuaderno_domain.

Servicio puro más consultas por lote; costes completos/parciales y ración, cambio de precio.

**Se acepta cuando:** Golden cases y coste observado desde DB, sin redondeo por línea.

## T010 · G2 · Recetas completas y escalado

**Depende de:** T009. **Responsable sugerido:** cuaderno_web.

Crear/editar/duplicar/archivar, cantidades, raciones, pasos básicos, simulación sin mutación.

**Se acepta cuando:** E2E vertical de ingrediente→receta→coste→persistencia.

## T011 · G2 · Fotos privadas optimizadas

**Depende de:** T010. **Responsable sugerido:** cuaderno_data_ops.

Subida segura, límites, variantes, EXIF fuera, almacenamiento atómico y acceso privado.

**Se acepta cuando:** MIME falso/imagen enorme/path inválido bloqueados, foto válida visible.

## T012 · G2 · Búsqueda, fichas impresas y responsive Esencial

**Depende de:** T011. **Responsable sugerido:** cuaderno_web.

Paginación/filtros, detalle y print A4; flujos táctiles y errores legibles.

**Se acepta cuando:** Receta de 30 líneas imprimible; móvil/tablet/escritorio funcionales.

## T013 · G2 · Import/export genérico y backup básico

**Depende de:** T010, T011. **Responsable sugerido:** cuaderno_data_ops.

JSON canónico, CSV validado, preview, idempotencia, export total y snapshot seguro con media.

**Se acepta cuando:** Roundtrip y restore aislado Esencial; no datos reales.

## T014 · G2 · Puerta de aceptación Esencial

**Depende de:** T012, T013. **Responsable sugerido:** cuaderno_qa.

Todos los escenarios básicos y permisos pasan; checkpoint funcional antes de ampliar.

**Se acepta cuando:** Revisión independiente y etiqueta interna ESSENTIAL_VERIFIED; no deploy comercial automático.

## T015 · G3 · Subrecetas y propagación por DAG

**Depende de:** T014. **Responsable sugerido:** cuaderno_domain.

Aristas, salida medible, costes transitivos, ciclos y profundidad, versiones y precio faltante.

**Se acepta cuando:** Rechaza A→B→A y propaga cambios correctos, sin N+1.

## T016 · G3 · Mermas, rendimientos y alérgenos declarados

**Depende de:** T015. **Responsable sugerido:** cuaderno_domain.

Separar merma de ingrediente y rendimiento de elaboración; registro manual sin certificación sanitaria.

**Se acepta cuando:** Ejemplo 80% una sola vez; agregación de alérgenos revisable.

## T017 · G3 · Menús, servicios y reservas internas

**Depende de:** T016. **Responsable sugerido:** cuaderno_web.

Semana/agenda, raciones por plato, comensales manuales O reservas, cancelación, capacidad y consolidación.

**Se acepta cuando:** No doble cómputo; DST y reservas canceladas; planificar no consume stock.

## T018 · G3 · Presupuestos y fichas de producción

**Depende de:** T017. **Responsable sugerido:** cuaderno_web.

Coste por servicio/persona, presupuesto sin venta, contribución opcional sobre base comparable y ficha avanzada.

**Se acepta cuando:** Sin falsa rentabilidad neta ni margen sobre precios incompletos.

## T019 · G3 · Puerta de aceptación Profesional

**Depende de:** T018. **Responsable sugerido:** cuaderno_qa.

E2E menú con subrecetas/merma/reservas y sus bloqueos por edición/rol.

**Se acepta cuando:** Revisión nueva; PRO_VERIFIED; Esencial sigue limpio y rápido.

## T020 · G4 · Proveedores y productos normalizados

**Depende de:** T019. **Responsable sugerido:** cuaderno_data_ops.

Fichas y referencias proveedor, formatos comparables, edición/archivado.

**Se acepta cuando:** Mismo ingrediente con varios proveedores sin inventar conversiones.

## T021 · G4 · Libro de movimientos y saldo de existencias

**Depende de:** T020. **Responsable sugerido:** cuaderno_domain.

Ledger inmutable, entrada/apertura/ajuste, saldo transaccional, versiones y anti-negativos.

**Se acepta cuando:** Carrera de consumo reproducida; no doble escritura ni saldo negativo.

## T022 · G4 · Compras y recepciones idempotentes

**Depende de:** T021. **Responsable sugerido:** cuaderno_data_ops.

Borrador/pedido/recepción parcial, líneas, precios, eventos y snapshot.

**Se acepta cuando:** Reintento de recepción no duplica stock; pedido sin recepción no incrementa saldo.

## T023 · G4 · Consumo por producción y desperdicios

**Depende de:** T022. **Responsable sugerido:** cuaderno_domain.

Confirmación explícita, explosión a ingredientes base, cantidades reales, motivos y compensaciones.

**Se acepta cuando:** Subrecetas no descuentan dos veces; desperdicio tiene coste y actor.

## T024 · G4 · Valoración ponderada y consistencia

**Depende de:** T023. **Responsable sugerido:** cuaderno_domain.

Media ponderada, salidas al coste vigente operativo, residuos a saldo cero y reconstrucción.

**Se acepta cuando:** Caso 20 kg/60 €→5 kg consumo→2 kg desperdicio=13 kg/39 €.

## T025 · G4 · Histórico e impacto de precios

**Depende de:** T022, T024. **Responsable sugerido:** cuaderno_web.

Historial de compras y eventos, cambio de coste actual de recetas; snapshots pasados intactos.

**Se acepta cuando:** Cambiar precio actual no reescribe compras ni producciones previas.

## T026 · G4 · Reposición, compra sugerida y equipo

**Depende de:** T025. **Responsable sugerido:** cuaderno_web.

Necesidad menos disponible, mínimos, redondeo de envase, permisos responsable/cocina/consulta.

**Se acepta cuando:** Propuestas explicadas; no pedidos enviados solos; API y media no filtran importes.

## T027 · G4 · Puerta de aceptación Integral

**Depende de:** T026. **Responsable sugerido:** cuaderno_qa.

Flujo completo servicio→necesidad→recepción→producción→pérdida→saldo/valor; regresión demás tiers.

**Se acepta cuando:** INTEGRAL_VERIFIED con revisión independiente y evidencias.

## T028 · G5 · Portabilidad completa y recuperación

**Depende de:** T027. **Responsable sugerido:** cuaderno_data_ops.

Extender formato export/import a todas las entidades, backup coherente y restore completo.

**Se acepta cuando:** Claves/refs/snapshots/media/stock restaurados en otro destino.

## T029 · G5 · Benchmark y reducción de recursos

**Depende de:** T028. **Responsable sugerido:** cuaderno_qa.

Seed grande fijo, p50/p95, RSS, disco/bundle/WAL, queries; mejorar cuellos encontrados.

**Se acepta cuando:** Informe reproducible sin atribuir a VPS lo medido solo en portátil.

## T030 · G5 · Instalación Windows y publicación Linux

**Depende de:** T029. **Responsable sugerido:** cuaderno_data_ops.

setup local seguro, servicio Linux/Caddy, persistencia fuera build, migraciones y rollback documentados.

**Se acepta cuando:** Checkout limpio→build→smoke; ningún servidor real modificado.

## T031 · G5 · Auditoría seguridad y dependencias

**Depende de:** T030. **Responsable sugerido:** cuaderno_reviewer.

Revisión independiente de auth, roles, edición, uploads, SQL, import y supply chain.

**Se acepta cuando:** Sin fallos críticos/altos aplicables abiertos; alertas justificadas.

## T032 · G6 · Revisión cross-browser y manuales

**Depende de:** T031. **Responsable sugerido:** cuaderno_qa.

Chromium/WebKit/Firefox, vistas, accesibilidad, manual usuario y lista iPad físico pendiente.

**Se acepta cuando:** Ninguna prueba no ejecutada declarada como PASS.

## T033 · G6 · Auditoría final sobre árbol integrado

**Depende de:** T032. **Responsable sugerido:** cuaderno_reviewer.

Comparar requerimientos con código y evidencias; rerun pedido al líder; comprobar recetas y ledger.

**Se acepta cuando:** Veredicto independiente y fixes revalidados.

## T034 · G6 · Release local y handoff final

**Depende de:** T033. **Responsable sugerido:** leader.

Empaquetar runtime/manifest, SHA256, guías y estado; resumir ejecutado y pendientes externos.

**Se acepta cuando:** LOCAL_VERIFIED y Linux real cuando probado; nunca inventar deploy/migración cliente.

## Entorno sin acceso externo

La ausencia de dominio/servidor, datos del programa antiguo o iPad físico no impide completar desarrollo local y pruebas sintéticas. Registrar lo pendiente por separado. Si falta un modelo, permisos de ejecución o una dependencia esencial no descargable, conservar checkpoint y precisar qué está bloqueado; no anunciar que las 34 tareas están terminadas.

## Entrega de cada puerta

Actualizar `docs/STATUS.md` con commit, comandos/exit, evidencia y revisor. Un README con capturas no sustituye funciones. El cliente tiene datos exportables y un flujo de recuperación, no solo una interfaz bonita.


---

# 08 · Seguridad y privacidad por defecto

## Autenticación y permisos

Better Auth y su integración oficial con SvelteKit; sesiones en cookies protegidas. No passwords/cookies en localStorage, no algoritmo casero de hash, no token compartido entre clientes. Alta pública deshabilitada. El primer propietario se crea mediante inicialización local/operador seguro.

Recuperación sin proveedor de correo: herramienta administrativa con token temporal de un solo uso, revoca sesiones y fuerza nueva contraseña. No token en logs o Git. Integración de correo es opcional posterior; no bloquear la app por no tener SMTP.

Cada acción/endpoint vuelve a comprobar sesión, rol y capacidad de edición. Middleware/layout facilita pero no sustituye permisos en servicios. Rechazar recurso ajeno o inaccesible de forma coherente. Roles de Integral: responsable gestiona todo; cocina consulta fichas/planificación y registra consumos/desperdicios permitidos; consulta solo lectura. Permiso de lectura de costes separado y comprobado antes de serializar datos.

## Sesión y HTTP

Secure/HttpOnly/SameSite según integración documentada; origen fijo tras Caddy; protección CSRF, headers coherentes, CSP compatible con Svelte y sin `unsafe-eval`. Pruebas de carga real para evitar romper la hidratación al añadir CSP. Errores de login genéricos; rate limit persistido de forma acotada o equivalente probado para no evadirlo reiniciando proceso.

Solo confiar en headers de proxy desde el proxy configurado. No dejar Node escuchando públicamente ni confiar en X-Forwarded-For de cualquier origen. Las consultas y recursos privados usan control de cache; no caché compartida de recetas, sesión o exportaciones.

## Archivos

Imágenes permitidas JPEG/PNG/WebP decodificadas de verdad, con límite de bytes (5 MiB inicial) y píxeles (24 MP inicial). Convertir, quitar metadatos EXIF/GPS, dimensiones acotadas y nombre/clave aleatoria o por hash. No permitir SVG/HTML arbitrario. HEIC no se promete sin soporte comprobado; error claro con alternativa JPEG.

Archivos fuera de `static/`, lectura autenticada por ID, prevenir path traversal/symlink, no confiar en extensión o MIME enviado. Escritura temporal y rename atómico. No servir ficheros originales peligrosos.

Importaciones con topes de filas/tamaño/profundidad JSON, sin ejecutar fórmulas/macros. Export CSV protege celdas que empiezan por =,+,-,@ cuando sean texto susceptible de fórmula. ZIP: impedir rutas absolutas/.., limitar tamaño descomprimido, número y ratio de archivos. No descargar imágenes de URLs arbitrarias del CSV (riesgo de SSRF).

## Datos del cliente

Desarrollo y CI usan únicamente fixtures sintéticas. No enviar exportaciones reales a modelos, servicios OCR o sistemas de analítica por defecto. La autorización de acceder a la aplicación antigua se obtiene antes de hacerlo; usar export/API documentada y solo datos cuyo acceso haya autorizado el cliente.

No deducir filiación religiosa, salud o perfiles de comensales del nombre/contacto de Elisabeth. Esta herramienta trata recetas de su trabajo, no datos de Ad Laudem. Observaciones dietéticas son notas de receta, no historias clínicas de personas.

Logs estructurados con request ID, tiempos y errores saneados. No imprimir ingredientes, recetas, cookies, hashes de contraseña, reservas nominativas o contenido de importación por defecto. Auditoría guarda el mínimo necesario (actor, operación, ID, versión, fecha); acceso solo responsable.

## Copias y secretos

Configuración privada fuera de Git, ejemplos sin secretos. Backups contienen datos sensibles: permisos mínimos y cifrado cuando salgan del servidor. Ni el ZIP de release ni artefactos de CI incluyen DB o media del cliente. No telemetría externa ni CDN obligatoria.

Documentar retención, contacto de soporte, ubicación y acceso al servidor antes de producción. No etiquetar la app como «cumple toda la normativa» porque pase tests técnicos; la configuración y acuerdos reales con el cliente importan.


---

# 09 · Migración del recetario y portabilidad

## Dos trabajos distintos

1. Implementar un importador/exportador general probado: parte de la calidad técnica del producto.
2. Extraer y transformar los datos del programa antiguo de Elisabeth: servicio específico, pendiente de conocer el sistema, formato, volumen y autorización.

No prometer recuperación de todos los datos, contraseñas o imágenes sin inspección. No hacer scraping de cuentas reales, romper controles de acceso o desarrollar OCR sin necesidad. Preguntar por nombre del programa, opción de exportar y un archivo pequeño representativo anonimizado cuando llegue ese momento.

## Formato canónico v1

JSON UTF-8 con `schemaVersion`, `currency`, `priceBasis`, ingredientes/formatos, recetas/líneas, categorías e instrucciones. Números decimales como strings. IDs externos conservados separados de IDs internos. Las referencias se resuelven por ID, no emparejando nombres automáticamente.

`examples/import/canonical-v1.json` es una muestra mínima ficticia para Esencial, no una copia de datos del cliente. El esquema definitivo se valida con Zod y tiene tests de upgrade entre versiones.

CSV por entidades: ingredientes, recetas y líneas, con `external_id`, separador/locale explícitos. Un formato desconocido se transforma mediante adaptador por fuente, fuera del motor de costes. Importar `.xlsx` no es requisito inicial ni obliga a instalar Office; una exportación CSV/JSON basta para el contrato base.

## Flujo seguro

Archivo → validación → normalización → vista previa → incidencias → confirmación humana → transacción/import por lote controlado → informe → comprobación.

Previsualización muestra cuántas recetas/ingredientes hay, campos ignorados, unidades sin equivalencia, precios desconocidos, referencias rotas y duplicados posibles. No crea recetas parciales silenciosamente ni rellena cantidades inventadas.

Tamaño inicial hasta 10 MiB de JSON/CSV por lote y 10.000 filas como techo de seguridad configurable; para datasets mayores usar lotes/CLI en entorno de importación, no incrementar sin medir el timeout de HTTP. La interfaz conserva informe descargable sin datos privados en logs.

Idempotencia por fuente, external_id y hash de contenido. Reimportar el mismo archivo es no-op; conflicto de cambio se presenta y necesita política explícita. Un batch inválido no deja escrituras parciales. No deduplicar ingredientes por coincidencia aproximada sin decisión del usuario.

## Comprobación posterior

Comparar recuentos, referencias, número de líneas, precios/unidades e imágenes; seleccionar una muestra de recetas para cotejo humano. La suma de costes solo compara datos con precios completos. Exportar de nuevo y validar roundtrip semántico; no exigir timestamps/IDs internos idénticos.

La copia previa se realiza antes de una importación real. Trabajar primero en instalación de prueba; no sobrescribir la única copia del origen. El cliente conserva siempre su exportación original sin modificar.

## Handoff de migración

Entregar plantilla de petición de muestra, reporte de diagnóstico, propuesta de mapeo y lista de datos que no pueden transferirse. Cuando falte el programa origen, el estado correcto es CLIENT_MIGRATION_PENDING, no fallo del motor genérico ni importación real completada.


---

# 10 · Rendimiento y almacenamiento medidos

## Objetivo, no publicidad

La queja de lentitud del programa anterior motiva medir la nueva app. No podemos afirmar ser X veces más rápidos sin datos comparables. Los siguientes son presupuestos iniciales de ingeniería; no resultados obtenidos ni garantías contractuales.

## Dataset y entorno

Seed fijo: 2.000 recetas, 5.000 ingredientes, 30.000 líneas; Profesional con DAG hasta profundidad 5; Integral con 100.000 movimientos y recepciones parciales. Separar escenario básico (sin ledger) del completo. Sin fotos en la primera medida; luego fotos optimizadas y medición de red.

Referencia de servidor para reproducir: 2 vCPU, 2 GiB RAM, SSD local; publicar CPU, SO, Node, SQLite, paquete/lock y commit reales. Si solo se prueba en el portátil, etiquetar LOCAL y no equivalerlo a VPS. Medir build de producción, después de calentamiento, al menos 100 operaciones por flujo y p50/p95/error rate.

## Presupuestos de salida

| Medida | Objetivo inicial |
|---|---:|
| Consulta/lista paginada en servidor, p95 | ≤250 ms |
| Búsqueda de ingredientes, p95 | ≤200 ms |
| Cálculo de receta de 30 líneas, p95 | ≤100 ms |
| Guardar receta o cambio de precio normal, p95 | ≤400 ms |
| JS de primera ruta, transferencia gzip | ≤170 KiB |
| CSS inicial gzip | ≤45 KiB |
| LCP en escenario móvil documentado | ≤2,5 s |
| CLS | ≤0,1 |
| Memoria RSS estable de app sin importación, fixture completo | ≤350 MiB |
| Build + dependencias runtime sin Node, media, DB o backups | ≤300 MiB |

No rebajar límites a posteriori para colorear un informe. Si uno no es viable, medir, explicar tradeoff y pedir revisión del líder con ADR. La métrica INP real depende del uso; tests de interacción sintéticos no se rotulan como datos de campo.

## Técnicas concretas

Paginación servidor, cargas de detalle perezosas, índices y EXPLAIN donde corresponda, evitar N+1 y transferir listas completas al navegador. Búsqueda normalizada, debounce alrededor de 200 ms, cancelación de respuestas obsoletas. Solo incorporar FTS5 si el patrón/medición lo necesita; no motor de búsqueda externo.

Recalcular costes con consultas por lote y memoización local del DAG. No recorridos completos de todas las recetas en cada pulsación. Proteger event loop de importaciones masivas y procesamiento de imágenes; trabajos acotados/worker thread si la medida demuestra bloqueo.

Separar guardar de subir imagen y ofrecer indicador de progreso. El cuerpo útil SSR debe aparecer sin esperar varias peticiones cliente.

## Imágenes y disco

Una foto opcional por receta al inicio; generar variante de ficha y miniatura, por ejemplo 1.280 px y 320 px. Objetivo de foto de ficha ≤350 KiB y miniatura ≤60 KiB, respetando calidad; medir percentiles, no prometer todos los originales al mismo peso.

No guardar fotos en base64 dentro de SQLite ni en HTML. Eliminar EXIF/GPS, no conservar el original enorme tras transformación validada salvo opción pactada. Deduplicar por hash cuando sea simple. Borrado físico diferido para no romper backups; recolección de huérfanos con dry-run y autorización de operación.

Ejemplo orientativo, no medición: 1.000 imágenes de 300 KiB suman unos 293 MiB, más miniaturas. Los backups multiplican el uso si se copian enteros; usar retención y deduplicación adecuadas.

Logs rotados (p. ej. 5×10 MiB), exportaciones temporales con caducidad, artefactos de E2E fuera de producción, guardar solo trazas/vídeo de fallos. Separar disco de desarrollo (dependencias + navegadores + caches, mayor) del runtime (menor). No prometer un desarrollo completo de pocos megabytes.

## Contención SQLite

Timeout acotado, transacciones cortas, un escritor; probar ráfaga de sesiones y reintentos. Mantener WAL con checkpoint sano; medir tamaño de -wal. La versión de SQLite debe contener los parches relevantes (incluido el arreglo de WAL-reset documentado en 2026); descartar releases retiradas y verificar driver real en G0.


---

# 11 · Windows, Linux, despliegue y copias

## Desarrollo

Windows 11 + Node 24 LTS + Git + gestor de paquetes congelado. Código independiente del sistema de archivos; construir rutas con API de Node. Native addons (SQLite/sharp) se instalan por plataforma: no copiar node_modules de Windows al VPS Linux. Probar Windows y Linux en CI.

Docker no es obligatorio. Se puede incluir un Dockerfile opcional más adelante si hay una necesidad concreta, pero no dos mecanismos de producción sin mantener ambos. La vía principal es servicio Linux con Caddy.

## Directorios de producción

```
/opt/cuaderno-cocina/releases/<id>/      build inmutable
/opt/cuaderno-cocina/current            enlace a release
/etc/cuaderno-cocina/app.env            configuración privada
/var/lib/cuaderno-cocina/site-1/db/
/var/lib/cuaderno-cocina/site-1/media/
/var/backups/cuaderno-cocina/site-1/
```

Usuario de servicio sin login, solo permisos necesarios; app en localhost tras proxy HTTPS. `ORIGIN` configurado con el dominio exacto, cookies seguras y proxy confiable. Migraciones como paso de publicación explícito, no un `push` de esquema destructivo al arrancar.

No escribir un dominio o IP real inventados. Los ejemplos de Caddy/systemd no se habilitan hasta completar los valores y confirmar destino. No tocar configuraciones de J&A u otros proyectos del propietario.

## Pipeline de release

Instalar lockfile → pruebas → build → auditar dependencias → backup previo → migrar copia de prueba → mantenimiento breve si necesario → migración real autorizada → cambiar release → readiness y smoke → cerrar mantenimiento. Si falla, mantener release previa y seguir runbook; el rollback de código no implica que una DB migrada sea reversible.

Migraciones destructivas evitadas mediante expand/contract. Antes de tocar datos reales, disponer de backup verificado y ventana acordada. No vender cero downtime con SQLite de una instancia.

## Backup consistente

No basta copiar `database.sqlite` mientras WAL está activo. Usar la API de backup SQLite del driver probado o snapshot equivalente documentado. Verificar integridad y que no falten transacciones confirmadas.

Media inmutable por hash, primero archivo escrito/renombrado y después referencia DB en transacción. Backup snapshot de la DB; enumerar los media referenciados por ESE snapshot; impedir eliminación física concurrente hasta acabar. Generar manifiesto con schemaVersion, commit, timestamp, hashes y assets. Si se elige mantenimiento para simplificar consistencia, bloquear todas las mutaciones empresariales y demostrarlo; no fingir que basta cerrar una pantalla.

Backups de imagen y DB coherentes; ningún snapshot se marca completo si falta un archivo referenciado. Comprobar SHA-256 y restaurar en carpeta aislada. No incluir cookies reutilizables en exportaciones funcionales; al restaurar un backup técnico, invalidar sesiones como paso de recuperación.

## Retención y copia externa

Propuesta operativa inicial: diario, siete diarios y cuatro semanales, con límites de espacio y alerta de fallo. Objetivo de recuperación de datos de hasta 24 h condicionado a ejecución real del scheduler; no es un SLA firmado. Una copia en el mismo VPS no protege frente a su pérdida: configurar destino externo cifrado con autorización/credenciales del propietario.

Si no hay destino externo todavía, terminar scripts y prueba local y marcar OFFSITE_BACKUP_PENDING. No afirmar protección completa en producción.

## Prueba de restauración obligatoria

1. Crear datos, receta, imagen, cambio de precio, recepción y desperdicio sintéticos.
2. Generar backup.
3. Restaurar a otra carpeta con app detenida para ese destino, no sobre la fuente.
4. Verificar integridad, FK, recuentos, recetas/costes, archivos y saldos.
5. Arrancar una segunda instancia en puerto libre y ejecutar smoke.
6. Registrar duración, hashes y resultados. Limpiar solo temporales creados por ese test.

Repetir antes de release y documentar cómo repetirlo periódicamente. Restaurar no tiene éxito porque exista un ZIP.

## Servicios mensuales y alcance

Las mensualidades 17/20/30 € no cambian la arquitectura ni autorizan soporte ilimitado. Los scripts facilitan hosting, copias y mantenimiento básico; cambios funcionales, carga manual y migración específica son trabajo adicional. No implementar un sistema de cobro de mantenimientos como parte de esta app.


---

# 12 · Definición de terminado y evidencia

## No basta con que arranque

- [ ] T001–T034 implementadas, integradas y verificadas conforme al alcance ALL_TIERS.
- [ ] Esencial utilizable de manera independiente con todas sus funciones reales.
- [ ] Profesional e Integral no exponen capacidades por URL cuando están desactivadas.
- [ ] Sin placeholders funcionales, TODOs bloqueantes, datos en memoria sustituyendo persistencia o mocks en flujos productivos.
- [ ] Datos sintéticos y app en español, sin atribuir datos de muestra al cliente.
- [ ] Precisión decimal, unidades, desconocidos, mermas, DAG, stock e idempotencia probados.
- [ ] Login/logout/recuperación, archivos privados, límites y permisos probados.
- [ ] Formato, lint, tipos, unitarias, integración, cobertura, build y E2E reales en verde.
- [ ] Pruebas Chromium/WebKit/Firefox y matrices de edición/rol/viewport.
- [ ] Benchmark con entorno/commit/dataset identificados, no cifras inventadas.
- [ ] Backup/restore en destino aislado con datos y media.
- [ ] Revisiones independientes sin hallazgos críticos/altos abiertos aplicables.
- [ ] Manual de usuario, guía de instalación y runbook de recuperación en español.
- [ ] Lockfile, procedencia/licencias, versiones y script de setup reproducibles.
- [ ] Release local con manifiesto y SHA-256, sin datos privados ni dependencias de desarrollo.

## Entregables de cierre

`docs/USER_GUIDE_ES.md`, `docs/INSTALL_WINDOWS_ES.md`, `docs/INSTALL_LINUX_ES.md`, `docs/OPERATIONS_ES.md`, `docs/RELEASE_REPORT.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/THIRD_PARTY_NOTICES.md` y evidencia sintética en `artifacts/release/<id>/`.

El reporte incluye comandos, códigos de salida, fecha, commit, modelos efectivos cuando se puedan verificar, versión Node/SQLite y casos de aceptación. No incluir secretos ni transcripciones privadas de razonamiento.

## Estados que deben distinguirse

- `LOCAL_VERIFIED`: pruebas locales y aplicación funcional demostradas.
- `LINUX_VERIFIED`: build/arranque/smoke y persistencia verificados en Linux/CI, no inferidos desde Windows.
- `IPAD_REAL_NOT_RUN`: WebKit pasó, pero todavía no se probó un iPad físico. Es una validación de campo pendiente explícita.
- `CLIENT_MIGRATION_PENDING`: importador genérico probado; origen y datos reales sin acceso.
- `PRODUCTION_DEPLOYMENT_PENDING`: runbook listo, no desplegado sin autorización.
- `OFFSITE_BACKUP_PENDING`: restore local aprobado, destino externo no configurado.

No se considera verificación técnica integral si falla Linux o un navegador requerido; corregir o declarar el bloqueo. Los pendientes externos anteriores no exigen inventar credenciales para completar el producto local.

## Prueba funcional de aceptación en cinco minutos

Propietario entra → crea ingrediente aceite 5 L/32 € → crea receta con 200 ml y 4 raciones → comprueba 1,28 €/0,32 € → cambia aceite a 40 € → comprueba 1,60 €/0,40 € → escala a 10 raciones y ve 500 ml sin modificar base → imprime → cierra/reabre sesión → vuelve a encontrar receta → exporta → restaura prueba aislada.

G3 y G4 añaden escenarios de producción y stock de `examples/contracts/golden-cases.json`. No usar la duración «cinco minutos» como promesa de tiempo de ejecución a clientes; es una sesión de demostración diseñada para ser breve.


---

# 13 · Límites comerciales y decisiones pendientes

La aplicación actual resuelve recetas, precios y cálculos. Los precios de 500/1.000/1.500 € son los últimos comunicados por el propietario, no una valoración de horas certificada por este paquete. La modalidad ALL_TIERS desarrolla un producto reutilizable; no significa que la clienta de Esencial tenga que financiar o recibir todas las funcionalidades.

Primero obtener Esencial vendible, después continuar fases superiores por la petición de desarrollo completo. En la instalación inicial, edición esencial y sin módulos extra visibles. No meter mecanismos de ventas, comisiones de referidos, cobros o fiscalidad en la app de cocina.

Antes de uso real, recopilar: quién es el titular, si vende platos o controla gasto interno, número de usuarios, dimensiones habituales, uso del iPad y versión, conectividad, recuento aproximado de recetas, nombre del sistema anterior, export disponible, necesidad de reserva interna, unidad de trabajo/cocina y dominio. Mientras falte, desarrollar con supuestos de 00-SCOPE y datos ficticios.

El importador general no garantiza una migración gratuita o automática de cualquier programa. No poner 100 € fijos a un extractor desconocido. Diagnóstico de muestra → estimación acotada → aprobación → migración reversible.

Si se quiere hospedar a nuevos clientes referidos, preferir instalaciones separadas de la misma versión con DB/media/secretos propios al principio. No clonar el código con diferencias manuales por cliente. Multiempresa compartida, facturación SaaS y multi-centro son proyectos futuros, no mejoras gratis implícitas.

Las librerías se reutilizan de manera legítima y con trazabilidad. No es necesario vender «todo desde cero» ni exponer a una clienta todos los detalles internos para explicar el valor; sí es necesario respetar las licencias y los avisos que correspondan. No eliminar atribuciones para ocultar procedencia.


---

# 14 · Fuentes primarias

Consultadas el **28/09/2026**. Son referencias de capacidades técnicas, no evidencia de una implementación ya construida. Al ejecutar el plan, comprobar versiones, parches y compatibilidad del entorno; no arrastrar flags obsoletos.

## S01 · Codex: modelos y selección

https://learn.chatgpt.com/docs/models

Uso en el plan: IDs, selección de modelo, esfuerzo y disponibilidad por cliente.

## S02 · GPT-5.6 Sol: ficha del modelo

https://developers.openai.com/api/docs/models/gpt-5.6-sol

Uso en el plan: Identificación oficial del modelo solicitado como líder; el acceso local se comprueba aparte.

## S03 · Codex: subagentes

https://learn.chatgpt.com/docs/agent-configuration/subagents

Uso en el plan: Agentes TOML independientes, precedencia, defaults y límites de concurrencia.

## S04 · Codex: creación y descubrimiento de skills

https://learn.chatgpt.com/docs/build-skills

Uso en el plan: SKILL.md con name/description, .agents/skills y carga progresiva.

## S05 · Codex: referencia de configuración

https://learn.chatgpt.com/docs/config-file/config-reference

Uso en el plan: Verificar campos admitidos por la versión instalada.

## S06 · Codex: sandbox Windows

https://learn.chatgpt.com/docs/windows/windows-sandbox

Uso en el plan: Flujo nativo PowerShell; no WSL obligatorio.

## S07 · Codex CLI

https://learn.chatgpt.com/docs/codex/cli

Uso en el plan: Instalación, acceso y ejecución local.

## S08 · Node.js: líneas de versiones

https://nodejs.org/en/about/previous-releases

Uso en el plan: Node 24 aparece como LTS a la fecha de consulta; 26 como Current.

## S09 · SvelteKit: adapter-node

https://svelte.dev/docs/kit/adapter-node

Uso en el plan: Build servidor y configuración ORIGIN/proxy.

## S10 · SvelteKit: form actions

https://svelte.dev/docs/kit/form-actions

Uso en el plan: Formularios servidor con mejora progresiva; distinguir funciones experimentales.

## S11 · Drizzle: SQLite

https://orm.drizzle.team/docs/sqlite/get-started-sqlite

Uso en el plan: Integración con SQLite; fijar APIs de la versión instalada.

## S12 · Better Auth: instalación

https://better-auth.com/docs/installation

Uso en el plan: Configuración oficial y adaptadores de datos.

## S13 · Better Auth: SvelteKit

https://better-auth.com/docs/integrations/svelte-kit

Uso en el plan: Integración de handlers/sesiones con el framework.

## S14 · SQLite: usos adecuados

https://www.sqlite.org/whentouse.html

Uso en el plan: Modelo de despliegue y límites frente a bases cliente-servidor.

## S15 · SQLite: WAL

https://sqlite.org/wal.html

Uso en el plan: Concurrencia, archivos WAL y restricciones de disco/red.

## S16 · SQLite: historial de versiones

https://sqlite.org/changes.html

Uso en el plan: Parches, arreglo WAL-reset de 2026 y releases retiradas; verificar runtime.

## S17 · better-sqlite3: API

https://github.com/WiseLibs/better-sqlite3/blob/master/docs/api.md

Uso en el plan: Transacciones y API backup; seguir versión fijada, no asumir un API propio.

## S18 · Tailwind: compatibilidad

https://tailwindcss.com/docs/compatibility

Uso en el plan: Requisitos de navegador; cotejar con iPad real.

## S19 · Playwright: emulación

https://playwright.dev/docs/emulation

Uso en el plan: Viewports, dispositivos y contexto de navegador; no sustituye prueba en hardware físico.

## S20 · pnpm: instalación

https://pnpm.io/installation

Uso en el plan: Instalación Windows mediante npm y compatibilidad; fijar después versión exacta.

## S21 · Git para Windows

https://git-scm.com/install/windows

Uso en el plan: Descarga oficial.

## Diferenciar hechos de decisiones

Los precios y requisitos provienen del WhatsApp aportado por el usuario, no de estas webs. El stack, límites de recursos, fases, tokens visuales y reglas de proceso son decisiones propuestas para este proyecto. Los benchmarks son objetivos pendientes de medir. No hay una promesa de compatibilidad, disponibilidad de modelos o rendimiento basada solamente en una URL.


---

# 15 · Dependencias, mantenimiento y reutilización

## Resolver una vez, reproducir siempre

T001 prepara `docs/DEPENDENCY_BASELINE.md`: paquete, versión exacta, canal estable, fuente oficial, compatibilidad Node24/Windows/Linux, licencia y alertas. Crear el proyecto con generador oficial en una carpeta temporal si evita sobrescribir este paquete; trasladar solo archivos necesarios revisados.

Conservar un único gestor/lockfile. Fijar dependencias directas a versiones exactas y versión de packageManager. Instalar en CI/producción con lockfile congelado. Nunca resolver `latest` cada vez que el servidor arranca.

Módulos nativos: better-sqlite3 y sharp deben tener binarios compatibles o una compilación reproducible documentada. Comprobar driver en Windows y Linux; no introducir Python/C++ obligatorios para el cliente sin demostrar que faltan binarios. SQLite embebido requiere revisión de versión/parches, incluido historial WAL 2026.

## Reutilización selectiva

Usar frameworks/librerías mantenidos y componentes que encajen. No descargar «packs de recetas» sin procedencia, no copiar pantallas completas de un competidor, no quitar encabezados/avisos. Registrar licencia exacta de cada componente y subdependencia relevante en THIRD_PARTY_NOTICES.

Un componente sin licencia clara no se incorpora. Si una licencia requiere obligaciones incompatibles con la entrega prevista, sustituirlo o elevar decisión explícita; no resolverlo ocultando el origen. Antes de publicar un repo, el propietario decide licencia del código propio después de revisar dependencias.

## Mantenimiento proporcionado

Separar actualizaciones de seguridad y parches compatibles de upgrades de major. PR local/CI, pruebas y backup antes de cambios. No actualizar framework, DB y auth simultáneamente sin necesidad. Registrar versión de esquema y release para soporte.

No añadir SDK de IA, WebSockets, Redis, cola, motor de búsqueda, librería enorme de hojas de cálculo o framework de microservicios por una posibilidad futura. Cada dependencia nueva explica problema actual, alternativa nativa, tamaño, mantenimiento y test que la justifica.
