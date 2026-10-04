# Runtime security APK provenance

These packages reproduce Alpine 3.23 recipes at aports commit
`e63efda2ffc3f7389eda3adbf5f569961d9b0d7a`, retaining the complete BusyBox
configuration and all 44 distribution patches in their original order.

BusyBox 1.37.0-r31 adds the reviewed upstream mailing-list v2 fix for
CVE-2025-60876 (SHA-256 `3c8c5b48f53ceb2641bb60c5c43b2a623e72246f2b7c0a87c1367136f455a936`).
zlib 1.3.2-r1 adds maintainer commits `df84af25`, `7235b0a5`, `813dac5d`, and
`d81c2d7e`, which together fix CVE-2026-85091 and its correctness follow-ups.
The complete source archives, recipes, patches, configurations, and licenses
are exported beside the APKs under `corresponding-source/`.

`SOURCE_DATE_EPOCH` is the pinned aports commit time. The checked-in RSA key is
a public, disposable reproducibility key and conveys no production trust;
runtime installation uses the separately hash-bound APKs with `--allow-untrusted`.
