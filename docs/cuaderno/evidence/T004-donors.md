# T004 — donantes fijados, sin copiar carpetas

SHAs comprobados: Mealie `0552eaa4` `v3.28.0`, KitchenOwl `09aaf5fbd234` `v0.7.10`, Grocy `7d15c46bbdc3` `v4.7.1`. No se levantó ninguno.

| Hueco | Dónde | Decisión |
|---|---|---|
| Importadores | Mealie `mealie/services/migrations/` (`PaprikaMigrator` y compañía, base `_migration_base.migrate`) y test `tests/unit_tests/services_tests/test_recipe_import_workflow.py` | Adaptar más adelante un lector pequeño. No FastAPI. |
| Listas | KitchenOwl `backend/app/controller/shoppinglist/shoppinglist_controller.py` y `backend/tests/api/test_api_shoppinglist.py` | Inspiración de UX. La lista sigue siendo `ShoppingList` de Tandoor. |
| Coste y stock | Grocy `services/RecipesService.php` (`GetRecipesPosResolved`, `ConsumeRecipe`) y `services/StockService.php` (`AddProduct`, `ConsumeProduct`) | No portar PHP. El coste de Cuaderno es Decimal propio sobre Food. El stock Integral, cuando se haga, escribe `InventoryEntry`/`InventoryLog`. |

No hay código de donante en `cuaderno/`.
