# Reservation/service integration architecture review

Read-only review of existing source on 2026-10-10. No production operations, changes or tests executed. Proposed reservation implementation was not present at inspection time.

## Correctness concerns to resolve

1. **Replenishment truncates before domain filtering.** `cuaderno/services/service_plans.py:40` accessible_service_plans materializes latest 100 candidates even when as_list=False. `cuaderno/services/purchasing.py:352` then filters CONFIRMED/household. Once more than 100 services exist, an older still-confirmed reservation dish is silently excluded. An aggregate query needs the full eligible set with recipe graph ACL preserved; list pagination should remain separate.
2. **Two generic production routes.** `cuaderno/api/operations.py` has ServicePlanView detail actions confirm/cancel/produce/reverse and ProductionSheetView(service_plan, action=produce). Both must reject reservation-linked services so callers cannot change ServicePlan without changing reservation state/revision. Reads may remain authorized. Consider all versions, including inactive links, to preserve history.
3. **Native calendar projection remains writable.** MealPlanViewSet.update/destroy in cookbook/views/api.py can change a reservation-generated MealPlan independently. MealPlanCourseView.put can change course independently. Freeze or explicitly guard these projections. Template overwrite already rejects rows linked to any ServicePlan.
4. **Reversal is terminal.** reverse_service_plan preserves original production snapshot, compensates all original stock movements, and sets state CANCELLED. Cancellation of in_kitchen should use that contract directly; no restored CONFIRMED intermediate state is expected.
5. **Idempotency keys are per service.** ServicePlan.produced_key is unique within Space; reverse also rejects a key SHA shared by another ServicePlan. A reservation-wide action key must derive unique child keys by reservation/version/service/dish. Repeated same action must not create duplicate links, native meals or consumption.
6. **Do not double replenishment demand.** Existing replenishment sums CONFIRMED ServicePlan frozen needs. Once produced, reservation services become PRODUCED and demand is excluded because stock was already consumed. Do not separately add reservation recipe needs or re-add in_kitchen services. Inactive versions must be cancelled before replacing active ones, atomically.
7. **Household and recipe graph ACL are independent.** An admin has household oversight but cannot override private recipe visibility. Reservation source selection, confirmation, summary and reads must preserve all-dish/subrecipe visibility and household scoping. Do not disclose a hidden dish via frozen menu summary.
8. **Summary join multiplicity.** Multiple ReservationService links per reservation can multiply covers. Group by reservation first or otherwise sum each reservation.covers once, not once per dish.
9. **Day-summary versus replenishment scope.** Existing replenishment has no date selector; absent explicit service_plans it includes all confirmed services. Explicit IDs max_length=100. Reservation UI must describe this scope honestly and handle >100 dish services without silent truncation.
10. **Whole reservation atomicity.** Confirmation, edit replacement, all-dish production and all-dish reversal require one outer transaction and consistent Space-first locks. A failure on the final child must roll back every prior child/ledger row, reservation state and revision audit.

## Minimum meaningful regression coverage

- >100 total services with oldest still-confirmed reservation service retained in replenishment; other household/private graphs excluded.
- Multi-dish menu sharing one ingredient: sum quantities once per dish; cover summary once per reservation; edits remove old version demand and add new demand exactly once.
- Integral all-dish production with insufficient stock on final dish: state, stock, movements and audit unchanged for every child.
- Profesional production creates no stock movements; cancellation/reversal preserves history without stock compensation.
- Same revision concurrent confirm/edit/cancel/produce: one committed transition, loser conflict; stale requests have zero writes.
- Action retries and derived child keys produce no duplicate MealPlan, ServicePlan, ReservationService or StockMovement.
- Both generic service action routes reject linked services; native MealPlan update/delete and course modification rejected or explicitly reconciled.
- Confirmed edit requires reason and Responsable; Cocina can confirm/produce/serve but cannot change menu/cancel. Consulta read-only mutation guards; Esencial extension denied.
- Cancel requested creates no services; cancel confirmed cancels active services; cancel in_kitchen reverses full production; served is terminal.
- Invalid/removed source recipe, unit or stock entry yields complete rollback rather than partial reservation update.
