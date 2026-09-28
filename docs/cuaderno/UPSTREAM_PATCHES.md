# Parches al núcleo Tandoor

| ID | Archivo/símbolo | Motivo | Alternativa descartada | Test regresión | Riesgo al actualizar | Commit |
|---|---|---|---|---|---|---|
| P001 | `recipes/settings.py` `INSTALLED_APPS` | Registrar `cuaderno` | Plugin loader frágil (`dir()[1]`) | Arranque y migración `cuaderno.0001` | Conflicto de lista al mezclar upstream | pendiente |
| P002 | `recipes/urls.py` include `cuaderno.urls` antes del catch-all | API `/api/cuaderno/` | Montar rutas dentro de `cookbook/urls.py` | `GET /api/cuaderno/recipes/1/cost/` | El catch-all de Vue se comería la ruta si el orden cambia | pendiente |
| P003 | `RecipeView.vue`, `main.ts`, `useNavigation.ts` | Panel de coste y entrada Costes sin quitar menús nativos | App Vue aparte | Pendiente de rebuild del manifiesto | El componente nuevo debe existir al compilar | pendiente |
