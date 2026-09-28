# T001 — validación de fuentes, bootstrap y routing

Fecha: 2026-09-28 (Europe/Madrid).

## Resultado observado

- Producto ejecutable: checkout de Tandoor `2.6.15` en
  `7e1c427a0e17858ddc41bd198c79ccad77d3bd69`, rama `cuaderno/main`.
- Remoto: `upstream` obtiene de `TandoorRecipes/recipes`; el push está
  deshabilitado con `DISABLED_DO_NOT_PUSH`.
- Mealie: `v3.28.0`,
  `0552eaa4a80031b8572849cca0ed95d07f1be001`.
- KitchenOwl: `v0.7.10`,
  `09aaf5fbd2343fcc10b12e906c63c3764dd38919`.
- Grocy: `v4.7.1`,
  `7d15c46bbdc35d4958cae99209ba170667dc1d64`.
- Los cuatro valores coinciden con `tooling/cuaderno/sources.lock.json` y
  con `tooling/cuaderno/bootstrap-report.json`.
- El reporte de bootstrap conserva correctamente `app_executed: false` y
  `dependencies_installed: false`: G0 todavía debe reproducir el pin.
- Cliente local: `codex-cli 0.158.0`.
- Routing solicitado: líder `gpt-5.6-sol/high`, implementación
  `gpt-6-astra/medium`, revisor `gpt-5.6-sol/high`; coincide entre
  `.codex/config.toml`, `.codex/agents/*.toml` y
  `tooling/cuaderno/model-routing.json`.
- La lista real de roles del cliente ofrece `cocina_*`. Por instrucción
  expresa del propietario, modelo y esfuerzo no son condición de avance;
  `effective_models_verified` permanece `false` como metadata honesta.
- Entorno disponible: Docker cliente `29.4.3`, servidor `29.4.2`, Compose
  `v5.1.3`. El Python host es `3.14.2`, incompatible con el pin declarado;
  T002 debe usar el contenedor Python 3.13, no instalar sobre el host.

## Comandos ejecutados

Todos finalizaron con código 0 salvo `git check-ignore .worktrees`, que
finalizó 1 porque la ruta aún no existe/no está ignorada; no se creó ningún
worktree.

```text
git status --short --branch
git rev-parse HEAD
git describe --tags --exact-match HEAD
git branch --show-current
git remote -v
git -C ../references/<donante> rev-parse HEAD
git -C ../references/<donante> describe --tags --exact-match HEAD
codex --version
docker version --format {{.Client.Version}}|{{.Server.Version}}
docker compose version
python scripts/cuaderno/tasks.py --ready
python scripts/cuaderno/check.py --list
```

## Límites y siguiente paso

No se ha arrancado aún Tandoor ni se han instalado dependencias. El
checkout actual es la rama de integración del producto y contiene el kit
sin versionar; moverlo ahora a un worktree nuevo excluiría esos archivos.
El líder conserva este checkout y asignará a hijos solo lectura o paths
disjuntos hasta que exista un baseline versionado.

## Revisión independiente

`cocina_reviewer` reprodujo las comprobaciones de solo lectura y emitió
veredicto **CUMPLE**. Confirmó adicionalmente
`git describe --tags --exact-match HEAD` con exit 0 y salida `2.6.15`.
No ejecutó tests ni arrancó servicios. El único hallazgo bajo era que ese
comando no figuraba en la primera versión de esta lista; queda corregido.
