# Fuentes verificadas y alcance de la revisión

Revisión de documentación y código remoto: 28 de septiembre de 2026. No se ejecutaron estas apps durante la preparación del paquete. En G0 deben verificarse los SHAs clonados y probar los recorridos reales.

## Tandoor
- Release: https://github.com/TandoorRecipes/recipes/releases/tag/2.6.15
- Ref: https://api.github.com/repos/TandoorRecipes/recipes/git/ref/tags/2.6.15
- Stack frontend: https://github.com/TandoorRecipes/recipes/blob/2.6.15/vue3/package.json
- Stack backend: https://github.com/TandoorRecipes/recipes/blob/2.6.15/requirements.txt
- Runtime: https://github.com/TandoorRecipes/recipes/blob/2.6.15/Dockerfile
- Entidades: https://github.com/TandoorRecipes/recipes/blob/2.6.15/cookbook/models.py
- Desarrollo: https://docs.tandoor.dev/contribute/installation/
- Docker/PostgreSQL: https://docs.tandoor.dev/install/docker/
- Import/export: https://docs.tandoor.dev/features/import_export/

Hallazgos: Vue3/Vuetify3, Django/DRF; Food/Unit/Recipe nativos; vínculo Food.recipe; MealPlan/MealType; ShoppingList y Entry; InventoryEntry/Location/Log. No se ha demostrado aún que el catálogo de precios/manual y los costes profesionales completos existan o cumplan nuestros contratos: auditar Property/FoodProperty y motor real.

## Mealie
- https://github.com/mealie-recipes/mealie/releases/tag/v3.28.0
- https://api.github.com/repos/mealie-recipes/mealie/git/ref/tags/v3.28.0
- https://mealie.io/
Fuentes útiles para importación, organización, menús y listas. Cualquier código a portar requiere inspección de archivo/tests en el pin; no basta con la web.

## KitchenOwl
- https://github.com/TomBursch/kitchenowl/releases/tag/v0.7.10
- https://api.github.com/repos/TomBursch/kitchenowl/git/ref/tags/v0.7.10
- https://github.com/TomBursch/kitchenowl/blob/v0.7.10/README.md
- https://docs.kitchenowl.org/latest/
README confirma Flutter/Flask, lista compartida, actualización en tiempo real y offline parcial. Estas características son referencia, no garantías del producto derivado. No portar Flutter. Si aparece backend como submódulo/repo aparte, resolver su commit fijado antes de inspeccionar; no clonar una rama latest sin registro.

## Grocy
- https://github.com/grocy/grocy/releases/tag/v4.7.1
- https://github.com/grocy/grocy/blob/v4.7.1/services/RecipesService.php
- https://github.com/grocy/grocy/blob/v4.7.1/migrations/0247.sql
- https://grocy.info/
Referencia para coste, reposición, movimientos y necesidades; no ejecutar PHP ni copiar SQL SQLite literalmente a PostgreSQL.

## Codex
- https://developers.openai.com/codex/multi-agent/ (redirige a documentación actual de subagentes)
- https://developers.openai.com/codex/skills/
- https://developers.openai.com/codex/models/
Formato consultado: archivos `.codex/agents/*.toml` con name/description/developer_instructions; defaults `[agents]`, límite max_concurrent_threads_per_session, skills `.agents/skills/*/SKILL.md`. Disponibilidad efectiva depende del cliente/cuenta.

Los ejemplos de comandos en documentación pueden ir por delante/detrás del tag: para reproducir, el checkout y su CI mandan; documentar diferencias y no fingir ejecución.
