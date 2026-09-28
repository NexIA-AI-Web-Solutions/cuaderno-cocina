# Orquestación nativa de Codex

## Modelos y transparencia
Líder: GPT-5.6 Sol con high, solicitado por el usuario. Implementación: GPT-6 Astra medium, manteniendo la interpretación previa de “GPT 6 Medium”. Modelo/esfuerzo no son un mismo identificador. Cambiable a GPT-6 Sol medium con el script de modelos, sin reescribir roles.
`.codex/config.toml` y archivos standalone `.codex/agents/*.toml` usan estructura de documentación consultada el 28/9/2026. Comprobar versión del cliente, `/model`, disponibilidad real y carga de agentes/skills antes de confiar en ella. Una configuración local no concede acceso.
No inventar selección ni afirmar que trabajó un modelo que no se ejecutó. Si no disponible, registrar bloqueo específico y usar la sesión disponible solo para trabajo independiente autorizado; no sustitución silenciosa. Si subagentes no soportados, ejecutar mismos packets secuencialmente y declarar modo sin paralelismo real.

## Roles
- Líder (sesión principal): prioridades, scope, ADR, contratos, planificación y merges. No delega responsabilidad de aceptar los tests.
- `cocina_scout`: explora base/donantes; devuelve mapa con SHA/rutas/símbolos y diferencias, sin cambios.
- `cocina_backend`: dominio Decimal, DRF, persistencia y módulos profesionales.
- `cocina_frontend`: Vue/Vuetify, UI española y accesibilidad; conserva Tandoor.
- `cocina_dataops`: importadores, backup, build/Compose y trazabilidad de datos.
- `cocina_qa`: tests de contratos, integración, navegador y rendimiento; no rebajar aceptación.
- `cocina_reviewer`: revisión fresca, independiente del autor, con hallazgos reproducibles.

## Política de concurrencia
Máximo 3 threads hijos abiertos y dos escritores simultáneos. El tercer hilo normalmente lee/revisa. No sub-subagentes. Durante G0 pueden ser 3 exploradores con rangos disjuntos; recopilar antes de diseñar extensiones.
Los workers NO ejecutan `git checkout/switch`, merges o actualizan branches en working tree compartido. Para archivos comunes: líder único escritor. Worktrees se crean por líder en `.worktrees/` ignorado, con rama y dependencias comunes integradas; no guardar datos reales en ellos. Cada worker usa DB temporal distinta si ejecuta integración.

## Contrato de packet
Usar `templates/cuaderno/TASK_PACKET.md`: id, objetivo observable, base commit, allowed paths, readonly paths, requisitos, test rojo, expected green, límites, evidencia de donor y condición de salida. No pasar los 30 docs a cada worker: seleccionar mínimos relevantes.
Worker devuelve resumen <=500 palabras, archivos/cambios, comandos con exit codes, evidencias y riesgos. Líder revisa diff, rerun e integra. Revisor no es el mismo hilo que implementó.

## Ruta crítica
G0 explorar/arrancar/char tests → G1 Esencial → G2 importar+UX+gate → G3 Profesional → G4 Integral → G5 hardening → G6 release local → G7 verificación final y handoff. Las fases finales no retrasan mostrar Esencial al propietario como preview local marcado.
Ningún agente integra compra/stock antes de congelar semántica de cantidades y precios. Frontend puede usar fixtures solo temporalmente; un gate nunca se aprueba con mock permanente.

## Archivos compartidos
`cookbook/models.py`, modelos/migraciones nuevas, requirements/lockfiles, settings/URLs, router/menu/vue3/package.json y source-lock: dueño líder/integrador. Trabajadores proponen patch o usan worktree asignado, sin colisión.
`docs/cuaderno/STATUS.md`, tasks.json y release checklist: líder actualiza. Reports separados por task y agent; no múltiples procesos append al mismo JSON.

## Estado y recuperación
Registrar TODO/IN_PROGRESS/BLOCKED/REVIEW/DONE; dependencias solo satisfechas con DONE revisado. Checkpoint por tarea con commit, comandos y siguiente acción concreta. Si termina cuota/contexto, escribir RESUME sin decir “terminado”. El prompt de reanudación verifica `git status` y no borra trabajo ajeno.
No loops infinitos de “revisar plan”: una ronda de reconocimiento y ADR para elegir extensión; luego implementación. Problema desconocido con coste alto se subdivide, no se convierte en permiso para reescribir todo.
