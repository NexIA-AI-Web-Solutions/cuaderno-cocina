# Formatting, estructura y mantenimiento

## Base existente
Tandoor dispone de configuración Python y Prettier. Antes de añadir herramientas: leer `.prettierrc`, `.flake8`, `pyproject.toml`, `pytest.ini`, lockfile frontend y CI. Heredar estilo de archivo tocado; no reordenar todo el repo para imponer preferencias.

## Código nuevo
Python: typing en límites de dominio/servicios, funciones pequeñas, errores explícitos, Decimal desde texto, no excepciones amplias silenciadas. Consistencia con formatter nativo; Ruff/mypy solo si añaden valor medible y se acotan a `cuaderno/`, sin meter tres formatters en conflicto.
Vue/TS: composición coherente con upstream, props/emits tipados, datos fuera de componentes de presentación, componentes pequeños, no `any` o casts masivos. Reutilizar store/router/i18n nativos. CSS scoped y tokens existentes. Contratos API generados cuando ya existe generator; no editar código generado a mano.
Pruebas junto a feature o en carpeta nativa correspondiente. Una nomenclatura consistente, imports ordenados por configuración del proyecto, newline LF/UTF-8. UI español, identificadores técnicos conforme a convenciones heredadas.

## Git y dependencia
Commits focalizados: `test:`, `feat(costing):`, `fix(import):`, `docs:`, etc. No mezclas de formateo + feature + actualización mayor. No modificar archivos de referencias.
Un único gestor por lenguaje heredado; respetar `vue3` lockfile real. No usar npm+pnpm+yarn a la vez. El root yarn.lock no prueba por sí solo qué lockfile gobierna vue3: comprobar CI.
Pin de dependencias directas relevantes, lockfile versionado y SBOM antes de entrega. Ni instalación global indiscriminada ni `latest` en imagen de producción.

## Cambios a upstream
Apuntar archivo, motivo, test y alternativa en UPSTREAM_PATCHES. Migraciones nuevas, no editar/squash de antiguas. Al actualizar upstream: rama de ensayo, backup, merge/cherry-pick revisado, pruebas completas y restauración. No auto-update de Docker sin compatibilidad.

## Deuda admisible
Problema preexistente: registrar prueba/impacto, alcance y decisión. No convertir “hay un warning antiguo” en excusa para ocultar un nuevo fallo. No reescrituras extensivas sin beneficio y aprobación de arquitectura del líder.
