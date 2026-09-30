# T004 — donantes fijados, sin copiar carpetas

SHAs comprobados: Mealie `0552eaa4` `v3.28.0`, KitchenOwl `09aaf5fbd234` `v0.7.10`, Grocy `7d15c46bbdc3` `v4.7.1`. No se levantó ninguno.

| Hueco | Dónde | Decisión |
|---|---|---|
| Importadores | Mealie `mealie/services/migrations/` (`PaprikaMigrator` y compañía, base `_migration_base.migrate`) y test `tests/unit_tests/services_tests/test_recipe_import_workflow.py` | Adaptar más adelante un lector pequeño. No FastAPI. |
| Listas | KitchenOwl `backend/app/controller/shoppinglist/shoppinglist_controller.py` y `backend/tests/api/test_api_shoppinglist.py` | Inspiración de UX. La lista sigue siendo `ShoppingList` de Tandoor. |
| Coste y stock | Grocy `services/RecipesService.php` (`GetRecipesPosResolved`, `ConsumeRecipe`) y `services/StockService.php` (`AddProduct`, `ConsumeProduct`) | No portar PHP. El coste de Cuaderno es Decimal propio sobre Food. El stock Integral, cuando se haga, escribe `InventoryEntry`/`InventoryLog`. |

No hay código de donante en `cuaderno/`.

## Auditoría ampliada del pin, 2026-09-30

Lectura independiente del agente purchase_workflow_sol (GPT-6.1 Sol). Repositorios en `../references/{mealie,kitchenowl,grocy}`, solo lectura; ningún donante arrancado ni suite ejecutada en esta auditoría. SHAs completos en `tooling/cuaderno/sources.lock.json` y verificados con `git rev-parse`/`git describe --tags --exact-match`.

| Área | Tandoor7e1c427a | Donante: símbolo y test localizado | Adaptación mínima y riesgo |
|---|---|---|---|
| Importación | native: `cookbook/integration/integration.py::Integration.do_import/do_export`, RecipeImport; `test_api_import_log.py`/`other/test_open_data_importer.py` | Mealie `mealie/services/migrations/paprika.py::PaprikaMigrator`; `tests/unit_tests/services_tests/test_paprika_migration.py`, `test_recipe_import_workflow.py`, `tests/integration_tests/recipe_migration_tests/test_recipe_migrations.py` | Reutilizar Integration y portar solo casos/lector faltante demostrado. No FastAPI/SQLAlchemy. |
| Lista | native ShoppingList*; `test_api_shopping_list_entryv2.py`, `test_api_shopping_list_recipe.py` | KitchenOwl `backend/app/controller/shoppinglist/shoppinglist_controller.py::getAllShoppingListItems`, `History.create_added/create_dropped`; `backend/tests/api/test_api_shoppinglist.py` add/get/remove | Adaptar UX de adición/historial a modelos y Vue Tandoor. No Flask ni sincronización IDs por nombre. |
| Coste | partial: PropertyType.PRICE/Property/FoodProperty Decimal, sin motor por envase/versiones | Grocy `services/RecipesService.php::GetRecipesPosResolved` y `StockService.php` precios actual/medio/histórico; test automatizado no localizado | Semántica/oráculos, no código float/PHP para dinero. |
| Compras | partial: Supermarket* y listas, sin pedido/estado | Grocy `services/StockService.php::AddProduct/AddProductToShoppingList`; test no localizado | Identidad/lista nativa más documento mínimo, no copiar servicio PHP. |
| Recepción | absent como documento; solo InventoryEntry/InventoryLog | Grocy AddProduct conserva precio/fecha/localización/transactionId; test no localizado | Extender recepción protegida y procedencia sobre ledger único. |
| Idempotencia | absent clave retry con unique/lock | Grocy AddProduct/ConsumeRecipe usa uniqid interno; test no localizado | transactionId no es retry-idempotency. Implementar unique Space+operation y bloquear antes de comprobar saldo. |
| Desperdicio | partial: REMOVE genérico sin causa/valoración | Grocy `StockService.php::ConsumeProduct(... bool $spoiled ...)`; test no localizado | Causa/snapshot Decimal; spoiled booleano no basta para contrato profesional. |
| Backup | partial export/import recetas, no snapshot PostgreSQL+media | Mealie `mealie/services/backups_v2/backup_v2.py::BackupV2.backup/restore`; `tests/unit_tests/services_tests/backup_v2_tests/test_backup_v2.py` y `tests/integration_tests/admin_tests/test_admin_backup.py`. Flujo/test Grocy no localizado: unverified | Adaptar manifest/verificación y casos restore, no formato SQLAlchemy/ZIP donante. |

Rutas de tests nativos sin directorio son de `cookbook/tests/api/`. «No localizado» describe esta búsqueda, no demuestra que un repositorio carezca de toda prueba. Licencias preservadas en refs: Mealie/KitchenOwl AGPL-3.0; Grocy LICENSE.md MIT. Dependencias incompatibles leídas en manifests fijados: Mealie Python3.14/FastAPI/Pydantic/SQLAlchemy; KitchenOwl Python≥3.14/Flask/SQLAlchemy; Grocy PHP8.5/Slim4. No se instalan ni introducen estos runtimes. La premisa contractual externa permanece resuelta, sin inferir cambios de licencia de dependencias.

Decisión por unidad: reuse-native primero, extend-native para huecos demostrados; spec-port de comportamientos pequeños cuando proceda. No carpetas copiadas ni tests de donante declarados como ejecutados. REUSE_LEDGER contiene las adaptaciones del producto y sus pruebas propias; esta matriz no afirma que cada candidato se haya portado. Revisión independiente ampliada aprobada2026-09-30: [T003-T004-review](T003-T004-review.md).
