# Herramientas del kit y límites

## Bootstrap (raíz del ZIP, antes de app/)
`python tools/bootstrap.py --dry-run` muestra los cuatro pins sin red y sin modificar carpetas. `python tools/bootstrap.py` hace los clones. Requiere Git y Python 3.11 o superior. Conserva historia de Tandoor (clon parcial, no shallow), crea `cuaderno/main`, deshabilita push upstream y deja los donantes separados. No instala dependencias ni ejecuta código de los donantes.
No sobrescribe app/references existentes. Si hay un fallo, solo retira el staging/outputs creados por esa ejecución. No edita ningún repositorio anterior. Un lock evita dos bootstraps simultáneos. Ante un lock tras apagado, comprobar que no hay proceso antes de retirarlo manualmente.
Si una descarga falla, corregir conexión y reintentar desde el kit; no cambiar de base ni de SHA. Si app/ ya existe, continuar allí, nunca regenerar encima. No combinar overlays de planes anteriores.

## Tasks (dentro de app/)
`python scripts/cuaderno/tasks.py --ready` lista tareas listas por dependencias. No lanza agentes ni hace trabajo en background. `python scripts/cuaderno/tasks.py` valida el grafo. Un DONE exige evidencia y `review_evidence`; validar contenido de estas evidencias es responsabilidad del líder, no del script.

## Checks (dentro de app/)
`python scripts/cuaderno/check.py --list` muestra el registry. Inicialmente todo está PENDIENTE. `python scripts/cuaderno/check.py unit` devuelve error 2 hasta que G0 configure un comando real. No se ofrece un éxito ficticio.
Cada entrada exige argv lista, cwd interno, purpose, verified=true y verified_at_commit. Solo marcar verified después de ejecutar el comando relevante del checkout y conservar evidencia; se puede configurar inicialmente un comando que da rojo por un requisito aún no implementado, siempre distinguiendo verificación del comando de aceptación funcional.
El runner ejecuta sin shell, registra stdout, duración, commit y exit code en `.cuaderno-runs/`. Es un registro de salida, no una prueba independiente de que los tests tengan suficiente calidad. El líder inspecciona el contenido. No introducir un comando trivial como `echo OK`.
Para checks con mutaciones de entorno aislado: usar `CUADERNO_ENV=test` y `--allow-isolated-mutations`; además cada comando de test debe validar DB/ruta únicos. Una variable no demuestra aislamiento. Nunca ejecutar contra producción.
El runner redacta valores sensibles presentes en el entorno por nombre, pero no garantiza detectar secretos arbitrarios. No usar datos reales en tests ni publicar logs sin inspección. Añadir `.cuaderno-runs/` y secretos a `.gitignore` y `.dockerignore`.

## Modelos (dentro de app/)
`python scripts/cuaderno/models.py --worker-model gpt-6-sol` cambia implementación/scout/QA; conserva líder y revisor. La configuración efectiva explícita de `model-routing.json` prevalece sobre referencias históricas de los .md. Modificar asignaciones no compra acceso ni valida el modelo; comprobar con el cliente y reabrir sesión si procede.

## Qué no incluyen estos scripts
No implementan recetas, no crean un SaaS de agentes, no envían peticiones directas a modelos, no acceden a cuentas ni al VPS. No son una alternativa a la orquestación nativa de Codex.
