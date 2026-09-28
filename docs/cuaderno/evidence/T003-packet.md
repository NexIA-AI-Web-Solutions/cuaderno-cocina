# Packet T003 — auditar Tandoor y puntos de extensión

- Objetivo observable: mapa verificable de Space, Recipe, Step, Ingredient,
  Food, Unit, Property/FoodProperty, MealPlan/MealType, ShoppingList y
  InventoryEntry/Location/Log, incluidas APIs, mutaciones y pruebas nativas.
- Base commit / gate: `f77a459f`, G0.
- Dependencias DONE verificadas: T001.
- Allowed write paths: ninguno; exploración de solo lectura.
- Read-only paths: `cookbook/`, `recipes/`, `vue3/`, tests y
  `docs/cuaderno/{02-REUSE-MAP.md,03-ARCHITECTURE.md,04-DOMAIN-CONTRACTS.md}`.
- Archivos compartidos reservados al líder: todo el checkout.
- Contrato: demostrar símbolos/rutas reales y clasificar cada capacidad
  `native/partial/absent/unverified`; identificar scoping Space, permissions,
  merge/delete, conversions, menús/listas e inventario antes de proponer.
- Prueba: citar tests de caracterización existentes y huecos concretos para
  pruebas nuevas; no afirmar ejecución.
- Límites: no editar, no ejecutar donantes, no diseñar ORM alternativo, no
  delegar.
- Entrega <=500 palabras: tabla compacta con ruta:símbolo, comportamiento,
  mutación/API/test y decisión reuse/extend; riesgos y comandos leídos.

