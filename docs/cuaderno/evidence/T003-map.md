# T003 — mapa nativo leído en el pin

Lectura de `cookbook/models.py`, `cookbook/urls.py`, `cookbook/serializer.py` y `vue3/src/apps/tandoor/main.ts` en `7e1c427a`. No se ejecutó la batería upstream.

| Capacidad | Símbolo | Mutación | Decisión |
|---|---|---|---|
| Space | `cookbook.models.Space` | API `space` | Reutilizar. Perfil de edición en `cuaderno.SpaceProfile`, no otro espacio. |
| Food / Unit | `Food`, `Unit`, `UnitConversion` | API `food`, `unit`, `unit-conversion`. `Food.merge_into` reasigna ingredientes y lista. | Reutilizar. El formato de compra es tabla nueva ligada a Food/Unit. |
| Recipe / Step / Ingredient | `Recipe.servings`, `Ingredient.amount` Decimal | API `recipe` anidada | Reutilizar. El coste no escribe la receta. |
| Properties | `PropertyType.PRICE/ALLERGEN` | API `property-type` | Parcial: existe la categoría, no hay motor de escandallo. No usar la propiedad como precio de envase. |
| Menús | `MealPlan.servings`, `MealType` | `/api/meal-plan/`, `/api/meal-type/` | Reutilizar comensales/calendario; extender estado y snapshot profesional, no inventar calendario. |
| Listas | `ShoppingList`, `ShoppingListEntry` | `/shopping` | Reutilizar. La cantidad es necesidad, no stock. |
| Inventario | `InventoryEntry.amount`, `InventoryLog` escrito en `InventoryEntrySerializer.create/update` | API `inventory-entry`; el log es de solo lectura | Extender en Integral. El update marca `remove` aunque la cantidad suba. Sin clave de idempotencia ni bloqueo. |

## Auditoría ampliada del pin, 2026-09-30

Lectura independiente del agente service_workflow_sol (GPT-6.1 Sol), sin ejecutar tests en esta auditoría. SHA completo: `7e1c427a0e17858ddc41bd198c79ccad77d3bd69`. Las rutas siguientes son del pin, no equivalencias inventadas de otros productos.

| Entidad/capacidad | Clasificación y símbolos | API, permiso/mutación y pruebas existentes |
|---|---|---|
| Space | native: `cookbook.models.Space`, `safe_delete` | `SpaceSerializer/SpaceViewSet`, `/api/space/`; guest/user/admin pueden crear; solo owner+admin actualiza. DELETE API no habilitado:405 incluso owner; safe_delete es capacidad del modelo con borrado explícito de dependencias, no de ese endpoint. `cookbook/tests/api/test_api_space.py::test_add` caracteriza POST201. |
| Household/UserSpace | native: `Household`, `UserSpace.household` | `HouseholdViewSet`, `/api/household/`; escritura owner de Space; cobertura indirecta en `test_api_meal_plan.py`/`test_api_food.py`, no suite propia. |
| Recipe | native: `Recipe.servings/private/created_by` | `RecipeSerializer/RecipeViewSet`, `/api/recipe/`; `CustomRecipePermission`: privado de otro autor en el mismo Space devuelve403; objeto fuera del queryset/cross-Space404. `test_api_recipe.py`. |
| Step/Ingredient | native: M2M y `Ingredient.amount` Decimal32,16 | `StepViewSet/IngredientViewSet`, `/api/step/` y `/api/ingredient/`; querysets heredan privacidad de Recipe. `test_api_step.py`/`test_api_ingredient.py`: CRUD, Space, privado y delete. |
| Food | native: árbol, properties, `Food.recipe`, `merge_into` | `FoodSerializer/FoodViewSet`, `/api/food/`; guest lectura/user escritura. Merge directo reasigna Ingredient/ShoppingListEntry; MergeMixin elimina propiedades/conversiones, no concilia extensiones futuras. `test_api_food.py`. |
| Unit | native: `Unit.merge_into` | `/api/unit/`, user/Space; reasigna ingredientes/listas/preferencias. Merge HTTP borra conversiones. `test_api_unit.py`: permisos/Space/delete/merge. |
| UnitConversion | native: `UnitConversion`, `cookbook/helper/unit_conversion_helper.py` | `UnitConversionSerializer/ViewSet`, `/api/unit-conversion/`; Space/user, food-specific y BFS multisal­to. `test_api_unit_conversion.py`, `other/test_unit_conversion.py`. No asumir exactitud de float para dinero. |
| PropertyType/Property/FoodProperty | partial para escandallo: categorías PRICE/ALLERGEN y relación through | `/api/property-type/`, `/api/property/`, tests `test_api_property*.py`. FoodProperty no endpoint propio ni precio de envase; no prueba dedicada de through. Ausencia de alérgeno no certifica ausencia real. |
| MealPlan/MealType | native calendario, partial servicio profesional | `/api/meal-plan/`, `/api/meal-type/`; Space/hogar/token/owner. `test_api_meal_plan.py`, `test_api_meal_type.py`. Sin estado producido ni ficha congelada en pin. |
| ShoppingList/Entry | native listas, no saldo | `/api/shopping-list/`, `/api/shopping-list-entry/`; Space/hogar. `test_api_shopping_list_entryv2.py`, `test_api_shopping_list_recipe.py`. |
| InventoryEntry/Location/Log | partial: saldo, localización, lote/caducidad y log | `/api/inventory-*`, user/Space; log read-only. `InventoryEntrySerializer.create/update` escribe logs; update etiqueta cualquier cambio de cantidad como REMOVE, sin locks/idempotencia. No suite API dedicada; `other/test_recipe_search_makenow.py` sí caracteriza saldo y aislamiento Household. |

Los tests sin prefijo de directorio en la tabla están en `cookbook/tests/api/`. El hueco por nombre `test_*inventory*` no equivale a ausencia total de caracterización: el test de búsqueda señalado utiliza InventoryEntry. Los huecos absent demostrados del pin son motor de escandallo por envase, servicio profesional congelado y ledger atómico con clave retry contractual. Configurar/reutilizar las entidades anteriores; extender servicios y protecciones, no duplicar catálogos/listas/calendario/almacén. Revisión independiente del mapa ampliado aprobada2026-09-30: [T003-T004-review](T003-T004-review.md); no se declaran los tests de la tabla ejecutados por esta lectura.
