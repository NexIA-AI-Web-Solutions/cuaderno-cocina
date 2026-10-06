# Cuaderno end-to-end acceptance suite

This package is intentionally independent from the frontend package. It locks its
runner and type checker and never writes credentials or authenticated browser state
to tracked paths.

The fixture command must create one space for every edition (`esencial`,
`profesional`, `integral`) and three users in each space:

* `demo-<edition>-consulta` (guest)
* `demo-<edition>-cocina` (user)
* `demo-<edition>-responsable` (admin)

Each space must contain a recipe, a shopping list with an unchecked entry, a package
and current price, an inventory entry, and (for Integral) an ordered purchase order
whose remaining quantity is at least 1. Professional and Integral spaces must also
contain a service plan. Fixture records used by this suite have names or labels that
start with `CUADERNO-E2E` (overridable with `CUADERNO_E2E_FIXTURE_PREFIX`).

Set `CUADERNO_DEMO_PASSWORD` only in the process environment and run `npm test`.
Missing authentication states are created before the tests. Setup is serial and
pauses for 61 seconds after every four attempts to respect the production
five-logins-per-minute/IP limit. Later runs reuse the states. The generated `.auth`
directory is ignored.

`BASE_URL` defaults to `http://127.0.0.1:18081`. The suite fails when auth state,
fixture records, edition capabilities, role ACLs, or browser error budgets are
missing; it does not silently skip those checks.

Concurrent waves must set exclusive `CUADERNO_E2E_OUTPUT_DIR` and
`CUADERNO_E2E_HTML_REPORT` directories. When common setup already created all nine
regular `.auth` state files, global setup validates and reuses them without another
login.

Authentication states live under `.auth/<target-hash>/`. Reuse requires matching
origin (including protocol and port), application path, demo identity, and the
expected session/CSRF cookie names, domain, path, Secure, HttpOnly and expiry.
Empty or stale state files trigger the normal serial setup; `--reuse` fails without
logging in. Root and prefixed candidate states never share a directory.

For the isolated HTTPS prefix candidate, set these variables before auth setup and
the full suite:

```sh
export BASE_URL=https://127.0.0.1:18443/cuaderno-cocina/
export CUADERNO_E2E_PREFIX=1
export CUADERNO_E2E_SELF_SIGNED=1
node prepare-auth.mjs
npm run typecheck
npm test
```

`CUADERNO_E2E_SELF_SIGNED=1` is limited to the isolated loopback test proxy. Prefix
tests assert base/assets/API/deep reloads, manifest/icon/shortcut URLs, exact worker
scope, public-only caches and preservation of a foreign cache, cookie limits,
language changes/logout, valid/invalid CSRF, and synthetic private image uploads,
share capabilities and print routing. Consulta must receive an explicit 403 on
creation; Cocina and Responsable create and delete their own temporary recipes.
The Chromium matrix and the existing Firefox/WebKit projects all include these
tests when the prefix flag is enabled. Root runs exclude the prefix file through
project configuration; no test skips, error budgets, retries or timeouts change.
Logout uses a fresh context without saved authentication, once per edition/role
at width 1440. These additional login submissions share a persisted 16-second
minimum spacing in the serial harness, keeping them below the existing five per
minute limit. Other widths still verify CSRF, language, foreign cookies and caches.
The shared fixture session is checked again after the isolated logout.

The full edition, role, and viewport matrix runs on Chromium. A focused Firefox
mobile project and WebKit tablet project additionally exercise keyboard focus,
landmark rendering, overflow, and print CSS. Install all three pinned browsers with
`npx playwright install chromium firefox webkit` before a release acceptance run.

After the candidate preview and fixture are ready, prepare all nine sessions once:

```text
node prepare-auth.mjs --base-url http://127.0.0.1:18081
```

Agents must then use `node prepare-auth.mjs --reuse` as a no-login preflight and run
one edition with an exclusive output directory. The explicit project sets are:

```text
# Esencial
$env:CUADERNO_E2E_OUTPUT_DIR='test-results/esencial-agent'; $env:CUADERNO_E2E_HTML_REPORT='playwright-report/esencial-agent'; node prepare-auth.mjs --reuse
npx playwright test --project=esencial-consulta-390 --project=esencial-consulta-768 --project=esencial-consulta-1440 --project=esencial-cocina-390 --project=esencial-cocina-768 --project=esencial-cocina-1440 --project=esencial-responsable-390 --project=esencial-responsable-768 --project=esencial-responsable-1440
# Profesional
$env:CUADERNO_E2E_OUTPUT_DIR='test-results/profesional-agent'; $env:CUADERNO_E2E_HTML_REPORT='playwright-report/profesional-agent'; node prepare-auth.mjs --reuse
npx playwright test --project=profesional-consulta-390 --project=profesional-consulta-768 --project=profesional-consulta-1440 --project=profesional-cocina-390 --project=profesional-cocina-768 --project=profesional-cocina-1440 --project=profesional-responsable-390 --project=profesional-responsable-768 --project=profesional-responsable-1440
# Integral
$env:CUADERNO_E2E_OUTPUT_DIR='test-results/integral-agent'; $env:CUADERNO_E2E_HTML_REPORT='playwright-report/integral-agent'; node prepare-auth.mjs --reuse
npx playwright test --project=integral-consulta-390 --project=integral-consulta-768 --project=integral-consulta-1440 --project=integral-cocina-390 --project=integral-cocina-768 --project=integral-cocina-1440 --project=integral-responsable-390 --project=integral-responsable-768 --project=integral-responsable-1440
```
