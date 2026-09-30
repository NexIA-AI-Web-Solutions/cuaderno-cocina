# Procedencia e inventario de componentes

Estado local del 2026-09-30: inventarios Python runtime, frontend instalado host y stage Linux de build validados contra el esquema oficial CycloneDX1.6. No se ha inventariado el cierre JavaScript empacado ni escaneado el SO/imagen. Se conserva la premisa contractual comunicada por el propietario y los avisos/licencias upstream; no se incorpora texto contractual privado.

| Componente | Pin | Uso |
|---|---|---|
| TandoorRecipes/recipes |2.6.15 / `7e1c427a0e17858ddc41bd198c79ccad77d3bd69` | Base ejecutable Django/DRF, Vue/Vuetify, modelos e historia |
| mealie-recipes/mealie |v3.28.0 / `0552eaa4a80031b8572849cca0ed95d07f1be001` | Referencia de importadores; no runtime ni carpetas portadas |
| TomBursch/kitchenowl |v0.7.10 / `09aaf5fbd2343fcc10b12e906c63c3764dd38919` | Referencia de listas/UX; no runtime |
| grocy/grocy |v4.7.1 / `7d15c46bbdc35d4958cae99209ba170667dc1d64` | Referencia semántica coste/stock; sin PHP portado ni runtime |
| PostgreSQL |16.15 baseline, postgres:16-alpine | Persistencia aislada local; registrar digest del artefacto final |

Fuentes: `tooling/cuaderno/sources.lock.json`, `bootstrap-report.json`, manifests/lockfiles, LICENSE/avisos. El bootstrap es histórico: su app_executed:false no describe el preview actual. Cambios propios y parches: REUSE_LEDGER/UPSTREAM_PATCHES e historia Git.

## Python runtime

Imagen efectiva auditada `sha256:59172af037dad2c4cc5762ecd5df24396de23b6bb05b78e5ac3d11d9d0edad9f`; source ref completo en STATUS. `070438Z-runtime-audit-84c067b1`:153 componentes Python con purl/licencias declaradas y lista separada de63 paquetes Alpine. Cero consultas PyPI irresueltas; exit1 por OAuthlib3.3.1/GHSA-xpv3-w29h-x7cv. Se conserva el aviso por versión pese al backport exacto (ADR0004); no se renombra la dependencia para ocultarlo. Hash del archivo corregido comprobado en591, además de c07 anterior: `53f308e800db1005c58fe17e7310ad695a62947363f725de8259f387fa841114`. Auditor copiado explícitamente a/tmp después del build, no incluido en la imagen.

Validación estructural del objeto153: `070555Z-runtime-sbom-validate-b158f91f` PASS. SHA256 canónico `7a2b442c347c0b25ba774a80c3e1d56115278ed99f12a0ca6c6432c96c1c589a`. Esta validación no aprueba el hallazgo de seguridad ni cubre paquetes OS.

## Frontend instalado

`frontend_inventory.mjs` recorre el árbol real instalado `vue3/node_modules`, incluidos paquetes scoped/anidados y dependencias build/dev; rechaza symlinks fuera del root, manifests/nombres inválidos. Registra purl, licencia declarada y SHA256 de package.json, no del contenido completo del paquete ni una interpretación jurídica de su licencia.

Host Windows:451 componentes, `042756Z-frontend-inventory-b0e277b2`. Ocho pruebas unitarias PASS051056Z (incluido CLI/layout Docker) y validación `044208Z-frontend-sbom-validate-4f4cb37c` PASS451. SHA256 canónico `464a0fa957c92284cb464b87cf2e8690a7b0bf3407f905ccee1bf49a4497903b`. El yarn audit histórico cubrió515 dependencias lógicas de build/dev con cero avisos: no es la misma cardinalidad que el árbol físico host ni demuestra módulos del bundle.

El build063934Z ejecutó el generador después de compilar con el árbol instalado real de Linux/amd64:453 componentes, no451. Solo su JSON se copia al runtime591 en `/opt/recipes/SBOM.frontend.cdx.json`; Node, generador y node_modules están ausentes, comprobado en runtime. Validación `064245Z-image-frontend-sbom-cc41423f` PASS453. SHA256 del archivo `b0097683f8526a35dd1fc7cf658a4f524b84b941a2eac3da77862e562d7758e9`; canónico `359a23f409cd3d43362cb9fce654bbcb83259a5ebe0bc5d88b374e661ed0ca39`. Incluye build/dev; NO es el cierre de módulos JS efectivamente incluidos en los bundles. Ese cierre sigue pendiente.

## Esquemas y límites

`validate_sbom.py`: esquema oficial [CycloneDX1.6](https://raw.githubusercontent.com/CycloneDX/specification/8a27bfd1be5be0dcb2c208a34d2f4fa0b6d75bd7/schema/bom-1.6.schema.json), commit fijado `8a27bfd1be5be0dcb2c208a34d2f4fa0b6d75bd7` (tag1.6.1). Solo tres URLs HTTPS exactas, sin redirects ni resolución de refs externos; timeout y tamaño acotados. JSON estricto rechaza NaN/Infinity/-Infinity. Ocho pruebas unitarias PASS, además de los dos inventarios reales validados. jsonschema4.26.0 ya instalado en el entorno de validación; no dependencia runtime nueva.

SHA256 de esquemas descargados:

- bom-1.6: `efc54d749e32a6e16abd19394b80b4c67d846e12c782e04505130375f94ea541`.
- spdx: `c41917196639055e9f9670811bac23ef777732144f3ff5a2f39686f61580dbe6`.
- jsf-0.82: `8bae002c25e723db7ee1f26afde680ae1a2b1a8f6b4b4b0fd65dc3becb090aae`.

Validar estructura no prueba ausencia de vulnerabilidades, contenido íntegro de paquetes, cierre JavaScript, licencias efectivas del bundle ni cumplimiento contractual de cada dependencia. Escaneo OS/imagen y revisión final siguen pendientes; sin publicación.
