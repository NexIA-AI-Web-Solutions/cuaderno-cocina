# ADR 0008 — Visibilidad nativa en referencias operativas

Estado: implementación2e27bd8ab revisada e integrada en alcance focal; regresión206/206 y91/91 pasan. Builded4 PASS173240Z incluye estos cambios; seguridad global y gates permanecen abiertos.

## Contexto

Tandoor conserva Recipe.private/shared, Food.recipe, Step.step_recipe, árboles Food, Spaces y ShareLink. Restringir únicamente la receta raíz dejaba referencias privadas accesibles mediante formatos, compras, stock y serializers nativos. Una decisión de acceso anterior a un bloqueo tampoco protege una escritura frente a una revocación concurrente.

## Decisión

- Reutilizar la ACL canónica de Recipe. Un administrador de Space no obtiene acceso implícito a recetas privadas ajenas.
- Filtrar Food en SQL, incluyendo ancestros inaccesibles: el nombre compuesto y parent nativos pueden revelar la rama. Extender esta misma selección a formatos, mínimos, compras y stock; no crear otro catálogo.
- En el detalle nativo, autorizar primero la raíz y recorrer las aristas reales con managers sin filtrado implícito. Un vínculo incoherente a otro Space o a un hijo privado falla con 404, sin nombres/IDs extranjeros. Un ShareLink autoriza solo su raíz; no concede acceso a hijos privados. Los ciclos visibles siguen siendo editables: esta comprobación no sustituye la validación de cálculo.
- En listas de Ingredient/Step, excluir filas/grafos inaccesibles antes del conteo y paginación. Un registro incoherente no invalida una página completa. Los detalles de esos registros siguen respondiendo 404.
- Aplicar filtros Food antes del límite nativo y después de resolver rutas de árbol. Conservar búsquedas, aleatoriedad y los otros modelos de TreeMixin.
- En escrituras afectadas, bloquear Space primero y revalidar objetos/referencias dentro de la transacción antes de modificar persistencia o invocar el proveedor externo. Revisar también replay idempotente, merge y cascadas de herencia.
- El reset de herencia conserva la función nativa, pero no borra relaciones de otros Spaces ni modifica ramas privadas inaccesibles.

## Evidencias y límites

Contratos reales PostgreSQL: test_food_visibility, test_visibility_locking y test_native_recipe_visibility. Los ensayos observan bloqueos PostgreSQL; únicamente el proveedor externo es una frontera simulada en el test que verifica que no se invoque. No se simula ACL ni persistencia.

El reviewer independiente autorizó corregir dos fixtures upstream que trasladaban Recipe/Step/Ingredient sin sus Food/Unit exclusivos. Se trasladan únicamente esas referencias, conservando expectativas 10/2 y controles privados. No se relaja el contrato de Space.

Resultados concretos en evidence/2026-09-30-continuacion.md y .cuaderno-runs: native122 PASS160713Z, privacy206 PASS170621Z, ratio91 PASS164752Z y ampliación40 PASS170945Z. Costing conserva resultados genéricos incompletos/conversión para FK hoja incoherente; la confirmación de producción valida esas referencias antes de omitir headers. Recetas enlazadas permanecen sujetas a visibilidad en ambos casos. La aprobación focal no equivale a cierre global de seguridad, rendimiento o G7. Previewed4 incluye esta implementación;591 se conserva como versión anterior.
