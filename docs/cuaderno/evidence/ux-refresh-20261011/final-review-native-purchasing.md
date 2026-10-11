# Native purchasing17 independent review

Verdict: PASS after default-autocomplete draft-retention correction. No remaining blocking regression identified in native shopping entry, add recipe to shopping, shopping export, recipe export polling, step/recipe editor accessibility or recipe time card changes.

## Blocking finding corrected

The first implementation preserved hidden ingredientInput but cleared the default visible autocomplete search before save resolved. Actual local Chromium reproduced this: type0,5 L REVIEW-DRAFT, Enter, parser200 and entryPOST503, visible autocomplete blank. The repaired source keeps clearing behind confirmed success and exposes failedDraft as editable Alimento pendiente plus Reintentar alimento.

Latest rebuilt assets actual Chromium390x844 local synthetic Esencial Responsable: intercepted entryPOST503 now displays original0,5 L REVIEW-DRAFT in Alimento pendiente; retry button is enabled. Editing it to0,25 L REVIEW-RETRY and retrying another intercepted503 preserves the edited value. No data write reached backend.

## Other verification

- Independent nativePurchasingUx tests:6 passed,0 failed,0 skipped. Covers positive fractions, duplicate-submit protection, busy recovery, CSV quoting, Blob hash/newline preservation and URL cleanup, export polling failures/timer cleanup, waiting-only time totals.
- Source review: correct native ShoppingStore success return checked; related recipe loading catches failure/finally and blocks incomplete submit; positive finite servings guarded; checkbox click stops parent double toggle; polling generation/unmount guards; keyboard roles and action names present; nullable/nonfinite time values excluded.
- Actual Chromium390x844 live Integral session with browser-only preview, read-only /edit/Recipe/37: Editar instrucciones del paso1 receives keyboard focus and Enter opens instruction editor. No recipe save performed.
- IntegrationPresentation test harness lifecycle injection reviewed: adds missing onBeforeUnmount dependency and checks registration while retaining prior format/type assertions. Appropriate test adaptation; no weakened assertion.

## Evidence

- native-audit/review-native-purchasing-tests.log
- native-audit/review-native-shopping.cjs/json
- native-audit/native-shopping-failed-autocomplete.png, native-shopping-fixed-autocomplete-retry.png
- native-audit/review-native-editor.cjs/json, review-native-mobile-instructions-keyboard.png

## Limits

Successful persistence and all-width presentation are separately owned by implementation agent. This independent pass targeted the reproduced failure path, keyboard behavior and state/timing correctness. Full suite/build are root-owned gates. The local Esencial account has no recipe list entries, so native editor keyboard verification used the existing Integral read-only context.

Final follow-up source review: AddToShoppingDialog input minimum changed from0.01 to0 while positive finite servings guard remains. Zero therefore stays invalid rather than being silently converted into a different valid quantity; negative input clamps to invalid0. Combined19 native tests pass,0 skipped. This corrects validation behavior without adding a counted improvement.

Actual final Chromium390 read-only recipe37 Add-to-shopping dialog keyboard check: Ctrl+A, Backspace,0,Tab leaves formatted0,00; positive-rations error visible and Add button disabled. No submit performed. Evidence native-audit/review-native-zero.cjs/json and native-servings-zero-remains-invalid.png. Playwright fill on this Vuetify numeric control concatenated with prior value; verification uses real replacement keystrokes.
