# Fresh reservation implementation diff review V1

Read-only source review, 2026-10-10. No source edits or deployment. Inspected current uncommitted files while implementation writers were active. Findings apply to the inspected version and require recheck after fixes. `git diff --check` passed. No executable integration tests run by this reviewer.

## Blockers

### P1: obsolete reservation meals remain active in native calendar

`cuaderno/services/reservations.py:134-142` retires services by cancel/reverse and active=False, but leaves every ServicePlan.meal_plan in MealPlan unchanged. `:202-203` creates fresh meals after confirmed covers/date/time/menu changes, so calendar retains both old and new commitments. `:237-238` cancellation likewise leaves cancelled meals visible. Native projection guards added in cookbook/views/api.py and service_plans.py then prohibit normal editing/deletion of these historical meals.

Expected: preserve historical service/audit rows while removing or excluding obsolete/cancelled native calendar projections from operative calendar/shopping flows. Regression: confirm 20 covers; edit to15/date2; calendar contains only current15/date2; cancel; no operative reservation meal remains. History and original snapshots/compensations remain intact.

### P2: row permission flags advertise actions denied by household authorization

`cuaderno/services/reservations.py:107-112` can_edit depends on role/state only; `:159-164` separately rejects non-admin operations in another household. Cross-household Cocina reads are intentionally supported and tested, so these rows reach UI with can_edit=true. `vue3/src/cuaderno/pages/ReservasPage.vue:121` generates confirm/start/serve from global canOperate, not a row-specific operation capability. UI therefore invites an action that predictably returns403.

Expected: flags reflect role AND row household (and assigned household); transitions use an explicit per-row operation capability. Responsable may retain oversight according to backend rule. Regression: other-household Cocina sees history/summary but no edit/confirm/start/serve controls; own-household Cocina sees authorized actions.

### P2: seconds accepted but omitted from history/reseed identity

`cuaderno/api/reservations.py:21` accepts HH:MM:SS. `cuaderno/services/reservations.py:99` serializes audit time to minutes; `:199-200` compares times only to minutes for reseeding. Confirm13:30:30; PATCH13:30:45 saves CustomerReservation.service_time to:45 yet does not retire/reseed MealPlan, which remains:30. Before/after history both show13:30. Frontend also slices time to five characters.

Expected: reject sub-minute precision consistently, or preserve exact accepted time in audit/payload/comparison. Regression: seconds-only confirmed edits either fail with clear validation and no writes or update projection/history coherently.

### P2: summary cards reuse Vue keys across frozen menu versions

Backend `cuaderno/services/reservations.py:248` groups template/day/meal/fingerprint independently, so two frozen versions of the same template/day/meal can coexist. `vue3/src/cuaderno/pages/ReservasPage.vue:19` uses `menuKey(group)`; `vue3/src/cuaderno/reservationsUi.ts:103` omits fingerprint. Both cards therefore have identical keys, causing duplicate-key warnings and potentially stale/reused card DOM during updates.

Expected: summary key includes menu_fingerprint; selector key can continue identifying template/day/meal. Regression: two versions render distinct cards and update correct totals without duplicate Vue keys.

## Correctness improvements present

- Outer transaction + Space lock covers all child confirmation/production/reversal, preserving atomic rollback when later dish fails.
- Confirmation permits Cocina and Responsable; menu changes/cancel restricted to Responsable by server checks.
- Terminal served/cancelled states and optimistic revision checks present; immediate committed intention replay handled without new writes.
- Child production/reversal keys incorporate reservation/version/service IDs, avoiding global service-key collision.
- Replenishment now applies state/household/date filters before graph-ACL inspection, uses2000 aggregate bound and explicit overflow error rather than silent100 truncation. Existing capped lists remain separate.
- Both generic service action and alternate ProductionSheet production routes reject reservation-linked services. Native MealPlan update/delete and course updates have guards.
- Summary counts covers once per reservation and adds pending ingredient needs only for confirmed services, excluding already produced reservations to avoid duplicate demand.

## Additional useful checks

- Test partial contact-only edits preserve frozen service IDs/costs (existing test present).
- Add real concurrent same-revision transitions on PostgreSQL; stale sequential test is not concurrency evidence.
- Validate summary/list >2000 error clearly reaches UI; current frontend error helper ignores field-keyed backend detail and generally substitutes generic message.
- Record the intended visibility of inactive historical services in generic production list; preservation alone should not imply still-operative native calendar meals.
