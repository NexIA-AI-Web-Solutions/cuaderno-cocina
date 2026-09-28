# Mapa concreto de reutilización

Repositorios fijados en `tooling/cuaderno/sources.lock.json`. En el workspace, `app/` es el producto; `references/{mealie,kitchenowl,grocy}` son solo lectura conceptual y no entran en imagen ni distribución del producto.

| Área | Primero comprobar en Tandoor | Donante / pieza a estudiar | Resultado en Cuaderno |
|---|---|---|---|
| Interfaz de recetas | `vue3/`, tarjetas, editor, detalle, navegación | Tandoor como autoridad visual | Conservar estructura, ampliar con pestaña Costes y modo simple. |
| Recetario/catálogos | `cookbook/models.py`: Food, Unit, Ingredient, Recipe, Step | No otro ORM | IDs y entidades nativos. |
| Importación | `cookbook/integration/` si existe en pin; localizar registro real | Mealie: migradores, importadores y tests de formatos | Adaptadores Python pequeños para huecos demostrados; sin FastAPI/SQLAlchemy paralelo. |
| Parser web | `requirements.txt` ya declara recipe-scrapers | Mealie y KitchenOwl usan parsers; contrastar casos | Usar la dependencia existente y su contrato; no tres parsers distintos para mismo formato. |
| Libros/filtros | RecipeBook, Keyword y búsqueda nativa | Mealie: organización y UX de filtros | Refinar pantallas nativas; no segundo índice/recetario. |
| Menús | MealPlan/MealType | Mealie: flujos semanales y agrupación | Extender reservas internas y producción, no calendario nuevo. |
| Lista compartida | ShoppingList/ShoppingListEntry/Recipe | KitchenOwl: adición rápida, agrupación, conflictos y experiencia táctil | Componentes Vue/Vuetify y API Django; sin widgets Flutter ni servidor Flask. |
| Costes | FoodProperty/Property/PropertyType, conversión de unidades: auditar exactitud | Grocy: recetas resueltas, faltas de precio, factores/unidades | Motor Decimal propio únicamente donde falte, ligado a Food; catálogo manual desacoplado de stock. |
| Inventario | InventoryEntry, InventoryLocation, InventoryLog | Grocy: movimientos, compra/consumo/desperdicio, mínimos, lotes | Servicios transaccionales nativos con trazabilidad; no copiar SQLite/PHP al backend. |
| Compras | ShoppingList y lo que exista de precios/tiendas | Grocy: reposición y fulfillment | Proveedores/recepciones profesionales vinculados a Food. |
| Backup | Capacidades nativas y permisos de exportación | Mealie: experiencia de export/restore y tests | Herramienta de recuperación coherente con PostgreSQL+media. |

## Fuentes concretas ya inspeccionadas
Tandoor: README, Dockerfile, requirements.txt, vue3/package.json y rangos de cookbook/models.py (Space 261+, Unit/Food 730+, MealPlan/Shopping 1200+, Inventory 1330+). Comprobar líneas en checkout antes de citarlas: números son orientativos.
Grocy: `services/RecipesService.php`, `migrations/0247.sql`, `config-dist.php`, `composer.json`, `package.json` en v4.7.1 ya revisados en conversación. No inferir que una migración histórica sea por sí sola el esquema final; aplicar cadena y consultar esquema efectivo.
Mealie/KitchenOwl: releases y documentación/README verificadas; NO se han inspeccionado todas sus implementaciones. En G0 localizar archivos exactos y tests y registrar símbolos antes de portar. Las rutas de donantes NO descubiertas no deben inventarse.

## Protocolo por función
1. Escribir comportamiento objetivo, ejemplo y criterio observable.
2. Ejecutar Tandoor sin modificar y registrar `native / partial / absent / unverified`.
3. Buscar implementación en referencia fijada; registrar repo, SHA, archivo, símbolos, dependencias, licencia/contrato aplicable y pruebas.
4. Elegir `configure`, `reuse-native`, `extend-native`, `adapt-source`, `spec-port`, `defer`.
5. Extraer una unidad pequeña y sus casos de prueba. Portar significa adaptar al modelo de Tandoor, no copiar una carpeta completa.
6. Probar caso normal, errores, permisos, concurrencia y coste de mantenimiento.
7. Anotar cambios frente al donante en `REUSE_LEDGER.md`. La ausencia de código copiable no autoriza reescribir una app entera.

## Regla contra “integración por acumulación”
No añadir Nuxt/FastAPI, Flutter/Flask ni PHP/Slim al runtime. Misma tecnología (Vue) no implica componentes intercambiables: revisar versión, store, router, i18n, API y dependencias. Un widget portado debe parecer y comportarse como Tandoor.
Prohibido sincronizar IDs por nombre de alimento. Nunca conectar directamente a la BD de los donantes.
Si una integración API con Grocy resultara imprescindible, abrir ADR con alternativas, ownership de datos y fallo parcial; no activarla en este plan sin decisión explícita del propietario.
