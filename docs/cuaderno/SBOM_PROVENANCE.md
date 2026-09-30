# Procedencia e inventario de componentes

Estado local del 2026-09-30: inventarios Python runtime, frontend instalado host y stage Linux de build validados contra el esquema oficial CycloneDX1.6. No hay todavía cierre JavaScript empacado ni escaneo OS/imagen válido: los intentos Windows fallaron. Se conservan la premisa contractual y avisos/licencias upstream; no se incorpora texto contractual privado.

| Componente | Pin | Uso |
|---|---|---|
| TandoorRecipes/recipes |2.6.15 / `7e1c427a0e17858ddc41bd198c79ccad77d3bd69` | Base ejecutable Django/DRF, Vue/Vuetify, modelos e historia |
| mealie-recipes/mealie |v3.28.0 / `0552eaa4a80031b8572849cca0ed95d07f1be001` | Referencia de importadores; no runtime ni carpetas portadas |
| TomBursch/kitchenowl |v0.7.10 / `09aaf5fbd2343fcc10b12e906c63c3764dd38919` | Referencia de listas/UX; no runtime |
| grocy/grocy |v4.7.1 / `7d15c46bbdc35d4958cae99209ba170667dc1d64` | Referencia semántica coste/stock; sin PHP portado ni runtime |
| PostgreSQL |16.15 baseline, postgres:16-alpine | Persistencia aislada local; registrar digest del artefacto final |

Fuentes: `../manifest/sources.lock.json`, `tooling/cuaderno/bootstrap-report.json`, manifests/lockfiles, LICENSE/avisos. El bootstrap es histórico: su app_executed:false no describe el preview actual. SHA/tag/ancestry deTandoor ydonantesHEAD reobservados20:16UTC coincidentes. Cambios propios y parches: REUSE_LEDGER/UPSTREAM_PATCHES e historia Git.

## Python runtime

Vigentea3c: imagen/fuente f191+worktreee8999 completas en STATUS, build205924Z PASS1321.767s. Constraints153 comprobadas en build y runtime211202Z/conjunto2009d15b; pipcheck211213Z y PyJWT2.15/security4PASS211029Z. Audit211047Z exit1:153Python/63Alpine/unresolved0, únicamente OAuthlibadvisory por versión. Backport53f308e800db1005c58fe17e7310ad695a62947363f725de8259f387fa841114 reobservado en `oauthlib/oauth2/rfc6749/grant_types/authorization_code.py`. SBOM211058Z PASS153/canónico `ac5f19c7a16a3d550e38312add2d9e0e16bead9b78360510ef0c553717e014ef`. No aprobaciónOS/avisos por validar JSON.

Histórico933: imagen `sha256:9330b8cc446d9ef2924f4153b042fc578497aefad7443ad799baf2006554ae06`, build185612Z PASS1266.065s/sourcebb6a+worktree024c8. PyJWT2.15/security4PASS185753Z. Audit185939Z exit1:153Python/63Alpine/unresolved0 y solo OAuthlibversión. SBOM191311Z canónico `fc0b18c29aa57cc3961709fb37b8b4548062c18c758a7a66ad7d09df9f74207d`. Ed4audit175100Z tenía además PyJWT2.14 advisory; SBOM175336Z canónico8acab859844e91eeb5e9d5dffad9fa8a260c49d3454b32cc65b4047c1c80fc55. No atribuir ambos avisos a933/a3c.

Rebuild933 cambió tres transitivas además de PyJWT: charset-normalizer3.5.1→3.5.2,filelock4.0.6→4.0.7,w3lib2.4.1→2.5.0. Cierre153versiones CPython3.13/Alpineamd64 implementado3ea8bf323/reviewfresh y empacado en a3c: unit7PASS195519/SBOM153PASS195521/controlnegativodrift193614, build205924 y runtime211202 PASS153. Los pins NO son hashes de archives ni congelación OS/bytes; requisitos mantienen raíces y extras nativos.

Corrección factual: stagefrontend/Node/node_modules no copiados, pero la dependencia Python nativa `nodejs-wheel-binaries==24.19.0` contiene `venv/lib/python3.13/site-packages/nodejs_wheel/bin/node`, observado en933 y registrado enSBOMPython. La afirmación histórica «Node ausente» era demasiado amplia.

Imagen histórica auditada `sha256:59172af037dad2c4cc5762ecd5df24396de23b6bb05b78e5ac3d11d9d0edad9f`; su source ref histórico se conserva en evidencia. `070438Z-runtime-audit-84c067b1`:153 componentes Python con purl/licencias declaradas y lista separada de63 paquetes Alpine. Cero consultas PyPI irresueltas; exit1 por OAuthlib3.3.1/GHSA-xpv3-w29h-x7cv. Se conserva el aviso por versión pese al backport exacto (ADR0004); no se renombra la dependencia para ocultarlo. Hash del archivo corregido comprobado en591, además de c07 anterior: `53f308e800db1005c58fe17e7310ad695a62947363f725de8259f387fa841114`. Auditor copiado explícitamente a/tmp después del build, no incluido en la imagen.

Validación estructural del objeto153: `070555Z-runtime-sbom-validate-b158f91f` PASS. SHA256 canónico `7a2b442c347c0b25ba774a80c3e1d56115278ed99f12a0ca6c6432c96c1c589a`. Esta validación no aprueba el hallazgo de seguridad ni cubre paquetes OS.

## Frontend instalado

`frontend_inventory.mjs` recorre el árbol real instalado `vue3/node_modules`, incluidos paquetes scoped/anidados y dependencias build/dev; rechaza symlinks fuera del root, manifests/nombres inválidos. Registra purl, licencia declarada y SHA256 de package.json, no del contenido completo del paquete ni una interpretación jurídica de su licencia.

Host Windows:451 componentes, `042756Z-frontend-inventory-b0e277b2`. Ocho pruebas unitarias PASS051056Z (incluido CLI/layout Docker) y validación `044208Z-frontend-sbom-validate-4f4cb37c` PASS451. SHA256 canónico `464a0fa957c92284cb464b87cf2e8690a7b0bf3407f905ccee1bf49a4497903b`. El yarn audit histórico cubrió515 dependencias lógicas de build/dev con cero avisos: no es la misma cardinalidad que el árbol físico host ni demuestra módulos del bundle.

El build063934Z ejecutó el generador después de compilar con el árbol instalado real de Linux/amd64:453 componentes, no451. Solo su JSON se copia al runtime591 en `/opt/recipes/SBOM.frontend.cdx.json`; El generador y node_modules del stage están ausentes; el matiz del binario Node nativo de Python se explica arriba. Validación `064245Z-image-frontend-sbom-cc41423f` PASS453. SHA256 del archivo `b0097683f8526a35dd1fc7cf658a4f524b84b941a2eac3da77862e562d7758e9`; canónico `359a23f409cd3d43362cb9fce654bbcb83259a5ebe0bc5d88b374e661ed0ca39`. Incluye build/dev; NO es el cierre de módulos JS efectivamente incluidos en los bundles. Ese cierre sigue pendiente. El mismo inventario453/canónico359a se revalidó ened4 con180828Z y en933 con191332Z-image-frontend-sbom-b7bd3d9c PASS453; esto no transforma el árbol instalado en cierreJS.

## Esquemas y límites

`validate_sbom.py`: esquema oficial [CycloneDX1.6](https://raw.githubusercontent.com/CycloneDX/specification/8a27bfd1be5be0dcb2c208a34d2f4fa0b6d75bd7/schema/bom-1.6.schema.json), commit fijado `8a27bfd1be5be0dcb2c208a34d2f4fa0b6d75bd7` (tag1.6.1). Solo tres URLs HTTPS exactas, sin redirects ni resolución de refs externos; timeout y tamaño acotados. JSON estricto rechaza NaN/Infinity/-Infinity. Ocho pruebas unitarias PASS, además de los dos inventarios reales validados. jsonschema4.26.0 ya instalado en el entorno de validación; no dependencia runtime nueva.

SHA256 de esquemas descargados:

- bom-1.6: `efc54d749e32a6e16abd19394b80b4c67d846e12c782e04505130375f94ea541`.
- spdx: `c41917196639055e9f9670811bac23ef777732144f3ff5a2f39686f61580dbe6`.
- jsf-0.82: `8bae002c25e723db7ee1f26afde680ae1a2b1a8f6b4b4b0fd65dc3becb090aae`.

Validar estructura no prueba ausencia de vulnerabilidades, contenido íntegro de paquetes, cierre JavaScript, licencias efectivas del bundle ni cumplimiento contractual de cada dependencia. Escaneo OS/imagen y revisión final siguen pendientes; sin publicación.

## Escaneo OS/imagen en preparación

Grype0.119.0 instalado SOLO en data/cuaderno/tooling desde [release oficial immutable](https://github.com/anchore/grype/releases/tag/v0.119.0). ZipSHA1db5c23b8ba0038a04acebed9c17945e1ade68d9f83e2fe1c101e4fb1feb9a48 y exeSHA5fa9104fb0630b9cd8049b12cb7b29713ce58fcaf586a26b3ad93d418982a52c comprobados. DBschema6.1.9/built2026-09-30T06:32:47Z/digestxxh64:8803575133ab5141/SHA04d141a255a18805a25dae81566dd3696c551be38bfe17929fd1008b338228d4. Wrapperbf4 + fixes7106(fullGit40)/cfff(DBstatusshape CLIreal), ROOTunit11PASS211252Z/reviewfresh. Se rehash tool/DB/archive y revalida imagen/binding final; ningúnignored finding se da por limpio.

Intentos reales:210844Z FAILDBstatuspreflight (corregido);211543Z FAILscanner. GrypeWindows crea nombres de caché con `sha256:` que Windows rechaza; diagnóstico CLI confirma el fallo al catalogar capas. Se conserva el archivo exacto de imagen269268480bytes en `data/cuaderno/scans/ccb83f86-f85e-48b1-9758-75826e9168d2`; grype.json vacío NO es informe válido ni cero vulnerabilidades. No mount del socket Docker ni de otros proyectos.

Linux0.119 preparado desde el mismo release, archiveSHA3fa2dc4b924621ab65404cf08d0b8438d896d80ab949c9d5a4ca283c36004c9b coincidente con checksums oficiales; binarioSHAe02ba25615668c6bae03473e3c6493b6dfffc2e4e419f65f9bd62555ac10cd0e. **No se ha ejecutado todavía el scanLinux**. Debe aislarse sin red/socket, usar el archive/DB fijados y conservar todos los hallazgos; no G7 por instalación.

## Tooling de módulos frontend preparado, no integrado

Commita447e1db1 añade `frontend_build_provenance.mjs` reutilizando el índice realpath de `frontend_inventory.mjs`. Observa módulos/chunks principales y SW por separado y hashea archivos finales; normaliza rutas, distingue virtual/unresolved/external y rechaza escapes/junctions. P1rootoutDirswap/P2testvacuocerrados con RED212417→ROOT11GREEN212643/freshreview. **Sin wiring Vite/Docker ni build real:** el test simula los bytes finales, no acredita orden Workbox efectivo ni cierre npm exacto. Inventario frontend453 revalidado211115Z en a3c, todavía cacheado del stageed4.
