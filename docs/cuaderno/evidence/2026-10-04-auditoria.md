# Evidencia de auditoría — 4 de octubre de 2026

Informe asociado: [AUDITORIA_2026-10-04.md](../AUDITORIA_2026-10-04.md).

## Identidad y límites

- Base: `83d0d6d6a362b2d46001dbc9d0a749d011414cd4`, rama `cuaderno/main`, limpia al inicio.
- Sistema: Windows/PowerShell. Python host `3.14.2`; Node host `25.8.1`.
- Frontend instalado: `vue-tsc 3.3.5`, TypeScript `5.9.3`. `vue-tsc --version` muestra la versión del compilador TypeScript, no la versión del paquete vue-tsc.
- Revisión de backend, frontend y operación mediante tres agentes acotados, sin delegación recursiva; modelo solicitado y aceptado en las tres llamadas: `gpt-6.1-sol`. No se deduce de ello el modelo efectivo del integrador.
- No se inició Docker, PostgreSQL, preview ni navegador. Las pruebas de tooling usan mocks/límites simulados y temporales; los tests de bootstrap usan repositorios sintéticos temporales.
- No se ejecutaron builds, restore, migraciones reales, despliegue ni escritura sobre datos de aplicación. No se instalaron las dependencias Django en el host.
- Esta evidencia resume salidas observadas durante la sesión. No se presenta como log íntegro exportado por `check.py` ni se añade un PASS artificial a `.cuaderno-runs`.

## Comprobaciones nuevas

### E01 — Estado y pins

`git -C app status --short` estaba vacío. Los tres clones donantes también estaban limpios; sus HEAD coinciden con `manifest/sources.lock.json`. Comparación de los manifests raíz/overlay/app: mismo contenido, hash Git de blob `aa640247c967fab7fab6a149583e2faa0bf23d89`.

`git -C app diff --numstat 7e1c427a0e17858ddc41bd198c79ccad77d3bd69 HEAD`: 363 archivos cambiados. La cuenta incluye nuevos archivos del producto y documentación; no significa 363 modificaciones al núcleo upstream. Entre las áreas: 117 Cuaderno, 69 Vue, 48 scripts, 58 docs y 20 cookbook.

`tasks.py` y `check.py --list`, desde app, terminaron con exit 0. Conteo directo del registry: 38 tareas, estados 3 DONE / 11 REVIEW / 19 IN_PROGRESS / 3 BLOCKED / 2 TODO. 155 comandos; `e2e`, `security`, `release` sin argv configurado.

### E02 — Suite del kit

Desde la carpeta raíz:

```powershell
python -B -m unittest discover -s tests -v
```

Resultado: **exit 1, 42 tests en 52,467 s, 41 correctos y 1 error**. Error en `test_all_json_parses`, `tests/test_kit.py:245`, `JSONDecodeError: Expecting value: line 1 column 1`.

Diagnóstico posterior, sin cambiar archivos: la búsqueda global alcanza 1.778 `.json`; 80 son rechazados por JSON estricto, incluyendo archivos JSONC de devcontainer/VSCode, configuraciones de dependencias y artefactos. Primer archivo rechazado en el orden observado: `references/mealie/.devcontainer/devcontainer.json`. Esto explica el fallo de alcance; no implica corrupción de 80 archivos. El diagnóstico no imprime contenido de datos ni secretos.

### E03 — Dominio puro

Desde `app/`:

```powershell
python -B -m unittest cuaderno.tests.test_domain_costing cuaderno.tests.test_production cuaderno.tests.test_margin cuaderno.tests.test_stock_contract -v
```

Resultado: **exit 0, 27/27 PASS**, 0,014 s reportados por unittest. Cubre contratos puros de precio/coste, producción, merma/margen y stock; no acredita persistencia, concurrencia PostgreSQL ni compatibilidad del runtime Python 3.13.

### E04 — Reproducción de precisión y entradas inválidas

Código ejecutado desde app, sin Django ni escrituras:

```python
from decimal import Decimal, getcontext
from cuaderno.domain.production import consolidate
from cuaderno.domain.stock import packs_to_buy

quantity = "1234567890123456.1234567890123456"
result = consolidate([("oil", quantity)])["oil"]
print(getcontext().prec, result, result == Decimal(quantity))
print(packs_to_buy("9999999999999999.0000000000000001", "0", "1"))

for payload in [[{}], [{"component": "oil", "quantity": "invalid"}]]:
    try:
        consolidate([(x["component"], x["quantity"]) for x in payload])
    except Exception as exc:
        print(type(exc).__name__)
```

Salida relevante:

```text
28 1234567890123456.123456789012 False
(Decimal('9999999999999999'), Decimal('9999999999999999'))
KeyError
DomainError
```

El número de envases matemáticamente necesario en el ejemplo de frontera es 10.000.000.000.000.000, porque la cantidad requerida supera el entero anterior por una fracción positiva. El helper pierde esa fracción. **Su exposición es distinta:** `packs_to_buy` aparece en una clase de reposición heredada no conectada al router; no se atribuye el defecto a la reposición canónica. `consolidate` sí está invocado por la ficha de producción activa.

### E05 — Frontend

Desde `app/vue3/`:

```powershell
node --test src/cuaderno/*.test.mjs
npx vue-tsc --noEmit -p tsconfig.app.json
```

Primera orden: **126 tests, 125 PASS, 1 FAIL, 0 skip/todo**, aproximadamente 23,4 s. Único fallo: `markdownSecurity.test.mjs:113`; el helper `render_instructions` intenta conectar a Docker y el pipe del engine Linux no está disponible. No se intentó arrancarlo.

Segunda orden: **exit 1, 629 diagnósticos**, de los cuales tres empiezan por `src/cuaderno`:

```text
src/cuaderno/allergenUi.ts(89,57): TS2532 Object is possibly 'undefined'.
src/cuaderno/productionWasteUi.ts(60,26): TS18048 'integer' is possibly 'undefined'.
src/cuaderno/productionWasteUi.ts(70,31): TS18048 'integer' is possibly 'undefined'.
```

Los otros 626 diagnósticos están fuera de Cuaderno. El baseline histórico y este resultado solo son comparables rigurosamente si se fijan las mismas versiones instaladas y tsconfig. Las versiones locales verificadas figuran arriba; no se ejecutó un nuevo baseline del pin.

### E06 — Tooling operativo

El revisor ejecutó las suites con sus layouts admitidos, sin iniciar contenedores:

| Suite Python de `scripts/cuaderno/` | Tests correctos |
|---|---:|
| `test_delivery.py` | 10 |
| `test_delivery_rollback.py` | 14 |
| `test_image_audit.py` | 11 |
| `test_docker_test.py` | 7 |
| `test_python_lock.py` | 7 |
| `test_upgrade_smoke.py` | 4 |
| **Total** | **53** |

`test_delivery` falló inicialmente al cargarse como módulo `scripts.cuaderno.test_delivery`: `ModuleNotFoundError` por import absoluto de `delivery_backup`. Ejecutado desde `scripts/cuaderno`, los diez tests pasaron. Se documentan ambos resultados; el segundo no oculta el defecto de discovery.

Pruebas Node de `scripts/cuaderno/test_frontend_inventory.mjs`: **11/11 PASS**. Cubren inventario/procedencia con fixtures, no prueban integración Vite/Workbox ni hashes de un build de release real.

### E07 — Chequeo Django no disponible

El intento del revisor de ejecutar `python manage.py makemigrations --check --dry-run --settings=recipes.test_settings` no pudo cargar Django en el Python del host. No se considera error de migraciones del proyecto ni se reemplaza PostgreSQL por SQLite para obtener un resultado verde.

## Evidencia histórica inspeccionada

Los siguientes reportes existen localmente bajo `.cuaderno-runs/` y se leyeron durante esta auditoría. Son ignorados por Git; los identificadores ayudan a localizarlos en esta máquina y los resúmenes versionados están en STATUS/evidencia anterior.

| Reporte | Hecho contrastado | Límite |
|---|---|---|
| `20260930T203010Z-performance-profile-35cb6393` | Exit 1; cinco aserciones fallidas, métricas de A06 | No medición nueva. |
| `20260930T115316Z-integration-35f34d1b` | Exit 0; 341 tests, 613,865 s de tests/668,393 s runner | Fuente previa a cambios posteriores. |
| `20260930T083231Z-typecheck-8df18f93` | Exit 2, diagnósticos TypeScript | No sustituye E05 actual. |
| `20260930T211047Z-runtime-audit-5f274d52` | Exit 1; reporte de dependencias/avisos Python | No scan completo OS/imagen ni avisos actualizados hoy. |
| `20260930T211543Z-image-audit-a734fd58` | Exit 1 | No scan válido. |
| `20260930T211202Z-runtime-python-lock-fd5073e9` | Exit 0; 153 distribuciones; declara `byte_reproducibility_claimed=false`, `os_packages_locked=false` | Versiones, no bytes ni OS. |
| `20260930T213552Z-restore-2172450d` | Exit 0 y resultados internos aprobados | Bundle histórico retirado; tiempo del runner distinto del tiempo interno de restore. |
| `20260930T214236Z-rollback-current-6c30d463` | Exit 0, 112,189 s del runner | Ensayo aislado; no activación productiva. |

`data/cuaderno/backups/` existe pero contiene cero entradas. El ZIP raíz se inspeccionó sin extraer: 75 entradas, kit/overlay, sin `app/`. No se eliminaron artefactos ni se recuperaron elementos de la Papelera.

## Reproducción posterior

Los comandos E02–E05 describen lo que se ejecutó, no prometen éxito en todos los entornos. Para aceptar el producto hay que usar también los comandos operativos del registry con sus precondiciones, el runtime compatible, PostgreSQL aislado y la imagen de candidato exacta. Respetar el estado detenido y el manual al reanudar; no ejecutar los comandos históricos de rollback suponiendo que sus bundles siguen disponibles.

No se archivaron secretos, recetas, dumps ni contenido de cuentas. Los cambios de esta auditoría son Markdown y enlaces de entrada, verificables con `git diff` en `app/`; la documentación de la raíz queda fuera de ese repositorio.
