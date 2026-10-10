# Reservation fixes re-review V3

2026-10-10. Read-only final source inspection, no source edits, deployment, production operations or new test execution by this reviewer. Concurrent writers may still change source. Actual Essential browser evidence is separate in [browser report](../browser-esencial/report.md).

All four V1 blockers and the V2 residual capability edge are addressed in inspected source:

| Finding | Current source evidence |
|---|---|
| Obsolete native MealPlan projections after confirmed edit/cancel | cookbook/views/api.py:1674 and cuaderno/services/planning.py:47 exclude inactive reservation-linked service projections. Historical rows remain stored; operative calendar and professional planning use active projections. |
| Row operations exposed outside assigned household | cuaderno/services/reservations.py:29 can_operate checks operational household belongs to the current space, operator permission, valid reservation household, then same-household scope or Responsable override. reservation_payload:120 derives all mutation capabilities from that result. API list-level capability uses the same helper at cuaderno/api/reservations.py:136. |
| No-household Responsable/Cocina offered unusable mutations | Same helper returns false before Responsable override when operational household is missing. vue3/src/cuaderno/pages/ReservasPage.vue:171 requires server list can_operate for creation, and line 9 explains required household assignment. Existing row capabilities also fail closed. |
| Seconds inconsistent with history/projection minute precision | cuaderno/api/reservations.py:21 TimeField accepts only %H:%M. vue3/src/cuaderno/reservationsUi.ts:133 validates only HH:mm. |
| Duplicate summary group keys for differing frozen menus | vue3/src/cuaderno/reservationsUi.ts:106 includes menu_fingerprint in summaryGroupKey; vue3/src/cuaderno/pages/ReservasPage.vue:20 uses it for summary cards. |

No remaining blocker identified in this narrow fixes review. This is source evidence, not independent runtime validation of all stock/state/history invariants; implementation tests and the other real-browser lanes remain required evidence.

`git diff --check` still reports four trailing-whitespace lines in generated OpenAPI files: ReplenishmentQueryRequest.ts:29/35, ServiceActionResultSchema.ts:29, ServicePlanSchema.ts:29. Reported to root; not modified by reviewer.
