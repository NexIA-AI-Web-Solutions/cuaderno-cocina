# Packet T002 — arrancar Tandoor sin modificaciones

- Objetivo observable: construir y arrancar el checkout `f77a459f` con su
  `Dockerfile` (Python 3.13) y PostgreSQL 16 aislado, demostrar health,
  login local y una receta nativa persistida.
- Base commit / gate: `f77a459f`, G0.
- Dependencias DONE verificadas: T001.
- Allowed write paths: `docs/cuaderno/evidence/T002-baseline.md` solamente.
  Docker puede crear recursos locales con prefijo exacto `cuaderno-g0-t002`.
- Read-only paths: todo el checkout, en especial `Dockerfile`, `boot.sh`,
  `.env.template`, `docs/install/docker/plain/docker-compose.yml`,
  `docs/cuaderno/12-DEPLOYMENT-BACKUP.md` y `17-TOOLING.md`.
- Archivos compartidos reservados al líder: settings, lockfiles,
  `.gitignore`, `commands.json`, `tasks.json`, `STATUS.md` y todo código.
- Contrato: no usar Python 3.14 host ni imagen pública genérica de Tandoor;
  construir el pin. PostgreSQL real. Bind web solo a `127.0.0.1:18080`.
- Caracterización: conservar código intacto; registrar imagen/digests,
  versiones, comandos/exit codes y estado de migraciones.
- Prueba: crear datos DEMO sintéticos solo locales; comprobar login y receta
  por interfaz/API nativa, reabrirla tras persistir y verificar DB PostgreSQL.
- Límites: no donantes, producción, datos reales, push o deploy; no borrar
  volúmenes ajenos. No usar `docker compose down -v` ni limpieza global.
- Entrega: escribir evidencia reproducible, nombres de recursos aún activos,
  credenciales DEMO locales, fallos/riesgos y comandos candidatos para el
  registry. Resumen final <=500 palabras. No delegar.

