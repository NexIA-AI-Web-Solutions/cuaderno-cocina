# Reservation fixes re-review V2

2026-10-10, read-only source review after V1 fixes. No tests run by this reviewer and no deployment/source edits. Writers were still active; conclusions apply to observed bytes at review time.

| V1 finding | Re-review |
|---|---|
| Obsolete native MealPlans | Addressed in source: native MealPlanViewSet.get_queryset and professional visible_plans exclude serviceplan__reservation_link__active=False. Historical meal/service rows remain intact while operative calendar/export excludes inactive projection. Root also guards shopping projection paths. Runtime regression evidence belongs to implementation tests, not this source review. |
| Cross-household Cocina capabilities | Addressed for normal assigned Cocina: row can_operate combines role and household scope; frontend actions requires row.can_operate. One remaining edge below. |
| Seconds lose audit/projection coherence | Addressed in API: TimeField accepts only%H:%M; new test rejects seconds-only confirmed edit. Frontend helper still accepts seconds in its regex, a validation consistency issue rather than persisted corruption. |
| Summary fingerprint duplicate Vue keys | Addressed in source: summaryGroupKey includes menu_fingerprint and summary v-for uses it. Selector menuKey retains template/day/meal identity. |

## Remaining permission-presentation edge

`cuaderno/services/reservations.py:109-114`: Responsable bypasses the row household match in operate and gets can_edit/can_cancel=true. `require_household()` still requires an assigned operational household even for Responsable. A Responsable with no assigned household can therefore see offered edit/confirm/start/serve/cancel operations that backend refuses with validation. The list-level global can_operate and frontend Nueva reserva similarly omit assigned-household capability.

Expected: preserve Responsable oversight across households when they have an operational household; no-household UI should explain assignment is required and suppress mutation controls. This is capability presentation consistency; server mutation guard still rejects the action.

## Consolidated audit artifact

Original production browser audit consolidated separately at `/home/kripta/cuaderno-informes-20261009/INFORME_PRUEBAS_NAVEGADOR_20261010.md`; all relative evidence links checked. It does not certify or describe these new reservation changes as deployed.
