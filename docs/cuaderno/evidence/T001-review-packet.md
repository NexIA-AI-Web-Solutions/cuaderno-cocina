# Packet T001 — revisar validación de fuentes y bootstrap

- Objetivo observable: confirmar que T001 acredita pins, checkout, cliente y
  estado real del bootstrap sin atribuciones falsas ni reabrir permisos.
- Base commit / gate: `7e1c427a0e17858ddc41bd198c79ccad77d3bd69`, G0.
- Dependencias DONE verificadas: ninguna.
- Allowed write paths: ninguno; revisión de solo lectura.
- Read-only paths / referencias:
  `tooling/cuaderno/{sources.lock.json,bootstrap-report.json,model-routing.json,tasks.json}`,
  `.codex/config.toml`, `.codex/agents/*.toml`,
  `docs/cuaderno/{STATUS.md,BLOCKERS.md,evidence/T001-validation.md}` y los
  Git de `../references/{mealie,kitchenowl,grocy}`.
- Archivos compartidos reservados al líder: todos.
- Contrato / fixture / requisito: aceptación T001 en `tasks.json` y reglas de
  `AGENTS.md`; el propietario ha indicado que modelo/esfuerzo no bloquean.
- Comportamiento nativo observado: el pin aún no se ha arrancado.
- Donante + SHA + ruta: verificar únicamente coincidencia de locks y Git.
- Prueba esperada: reproducir comandos de solo lectura citados en la evidencia.
- Límites: no editar, instalar, arrancar servicios, hacer commit, push o deploy.
- Entrega: verdict de cumplimiento y hallazgos reproducibles; no implementar.
