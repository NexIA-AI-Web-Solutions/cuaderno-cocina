# Production storage precision review

2026-10-10. Read-only review of newly visible `_locked_allocations` fix and ProductionStoragePrecisionTests; no source changes or production operations, no independent Django test execution.

Policy is appropriate: preserve frozen theoretical needs at working precision, convert partial allocation to the inventory entry unit, then ceil positive consumption to Decimal(32,16) storage quantum. Reversal uses original movement.quantity, so the compensating movement restores exactly what was consumed. Full-lot allocations retain already persisted quantities. Over-consumption from rounding is strictly less than one 1e-16 quantum in the final entry unit per partial allocation.

Visible implementation service_plans.py:351-353 uses localcontext64 and ROUND_CEILING. New integration test exercises yield0.9, full frozen precision, representable consumption, unchanged frozen need, idempotent replay, exact reversal and movement count. This is meaningful regression coverage.

Residual identified and sent to root: `remaining -= used_required` still uses default28 precision. A deterministic Decimal-only check shows need1.0000000000000000000000000000000000000001 minus a full first lot0.0000000000000001 becomes0.9999999999999999000000000000 at28 digits and ceils to0.9999999999999999, whereas64-digit subtraction retains the tiny tail and ceils to1.0000000000000000. Use64-digit subtraction too to preserve the promised no-underconsumption policy. This check uses synthetic arithmetic only.

Useful cases: mixed lot units (full g lot then partial kg lot), recurring food-specific conversion, last lot exactly equal to the need, positive requirement below one storage quantum, insufficient stock rollback, replay and exact reversal of both lots. A partial allocation below a storage-grid balance should ceil no higher than that balance; conversion rounding near the boundary should be explicitly checked if different conversion paths are involved. Avoid recomputing reversal from theoretical needs.

## Final re-review: resolved

Current inspected `service_plans.py:357-359` now wraps remaining subtraction in localcontext64. The earlier residual no longer applies. The quantization remains in the entry unit with ROUND_CEILING; frozen needs are unchanged and reversal continues to use each original stored movement quantity.

Three real-recipe regression cases are now present in ProductionStoragePrecisionTests: ordinary0.9 recurring yield with replay/reversal; full1000g lot followed by partialkg lot with both balances exactly restored; yield0.9999999999999999, net1kg, first1e-16kg lot, where the remaining tail beyond28 digits requires second consumption1.0000000000000001kg. The last case directly catches the lost-tail issue rather than mirroring the implementation.

Reviewed execution evidence [recurring-yield-green-final.log](../recurring-yield-green-final.log): 87 focused stock/service/ledger/reservation tests, OK; root reports the three new precision cases are included and passed. The log is aggregate rather than verbose per-case evidence. These tests were executed by root, not independently rerun by this reviewer. The full backend suite and repeated Integral browser flow were still in progress at this re-review.

**No remaining blocker identified in this narrow storage-precision review.** The general suggested edge cases above remain useful future coverage rather than demonstrated additional failures.
