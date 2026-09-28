---
name: cuaderno-orchestrate
description: "Coordinar el proyecto completo, repartir paquetes y decidir puertas de aceptación; no usar para un cambio trivial de formato."
---

# cuaderno-orchestrate

1. Leer AGENTS.md, docs/00-SCOPE.md, docs/05-AGENT-ORCHESTRATION.md y tooling/work-packets.json.
2. Verificar modelos efectivos y cliente antes de delegar. No confiar en autodescripciones de un agente.
3. Elegir el primer paquete cuyas dependencias están verificadas; fijar rutas, contrato, RED/GREEN y entrega.
4. Máximo dos escritores con archivos distintos y un revisor. El líder controla lockfile/migrations/config común.
5. Integrar solo con tests reales y revisión independiente; resolver hallazgos, no esconderlos.
6. Actualizar STATUS/BLOCKERS/DECISIONS y continuar hasta T034; checkpoints ante límites, sin simular terminado.

## Entrega

Resumen de cambios o hallazgos, archivos concretos, comandos ejecutados, códigos de salida, evidencia y límites. Las instrucciones de esta skill no conceden permisos extra ni sustituyen las capacidades reales del cliente.
