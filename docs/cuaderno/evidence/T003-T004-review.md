# T003/T004 — revisión independiente

30 de septiembre de2026. Revisor `integrity_review_sol`, agente GPT‑6.1 Sol reutilizado; no autor de los mapas. Integrador raíz aplica correcciones. Se revisaron el pin nativo, los clones fijados y los diffs de T003-map/T004-donors. No se ejecutaron suites de donantes ni se atribuye esta auditoría al runtime.

T003 aprobado tras corregir: privada del mismo Space devuelve403/crossSpace404; crear Space permite guest/user/admin, actualizar exige owner+admin; DELETE API405 incluso owner, `safe_delete` es capacidad del modelo; inventario tiene caracterización indirecta en `test_recipe_search_makenow.py`. MealPlan ya tiene servings: se extiende estado/snapshot, no se duplica.

T004 aprobado tras verificar rutas de pruebas, SHAs/tags, manifests y licencias. Backup Mealie: `tests/unit_tests/services_tests/backup_v2_tests/test_backup_v2.py` y protección traversal en `tests/integration_tests/admin_tests/test_admin_backup.py`. Se conserva Grocy backup como unverified. Capacidad documental no implica adopción de carpetas ni ejecución de otros runtimes.

Dependencia T001 DONE, evidencia propia en los dos mapas: T003/T004 pueden marcarse DONE. Esta aprobación no cierra T002/T005 ni G0/G7. El ensayo `070137Z-migrations-c39da16a` fue revisado y aprobado para el cambio acotado upgrade_smoke: pin/postgreSQL/DjangoClient+upgrade, no socketHTTP/Vue/browser/capturas.
