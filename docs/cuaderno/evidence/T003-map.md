# T003 — mapa nativo leído en el pin

Lectura de `cookbook/models.py`, `cookbook/urls.py`, `cookbook/serializer.py` y `vue3/src/apps/tandoor/main.ts` en `7e1c427a`. No se ejecutó la batería upstream.

| Capacidad | Símbolo | Mutación | Decisión |
|---|---|---|---|
| Space | `cookbook.models.Space` | API `space` | Reutilizar. Perfil de edición en `cuaderno.SpaceProfile`, no otro espacio. |
| Food / Unit | `Food`, `Unit`, `UnitConversion` | API `food`, `unit`, `unit-conversion`. `Food.merge_into` reasigna ingredientes y lista. | Reutilizar. El formato de compra es tabla nueva ligada a Food/Unit. |
| Recipe / Step / Ingredient | `Recipe.servings`, `Ingredient.amount` Decimal | API `recipe` anidada | Reutilizar. El coste no escribe la receta. |
| Properties | `PropertyType.PRICE/ALLERGEN` | API `property-type` | Parcial: existe la categoría, no hay motor de escandallo. No usar la propiedad como precio de envase. |
| Menús | `MealPlan`, `MealType` | `/mealplan` | Reutilizar más adelante. No hay comensales de servicio. |
| Listas | `ShoppingList`, `ShoppingListEntry` | `/shopping` | Reutilizar. La cantidad es necesidad, no stock. |
| Inventario | `InventoryEntry.amount`, `InventoryLog` escrito en `InventoryEntrySerializer.create/update` | API `inventory-entry`; el log es de solo lectura | Extender en Integral. El update marca `remove` aunque la cantidad suba. Sin clave de idempotencia ni bloqueo. |

Hueco de tests nativos: no hay `test_*inventory*` en `cookbook/tests`.
