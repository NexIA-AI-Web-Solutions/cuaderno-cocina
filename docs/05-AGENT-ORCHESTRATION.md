# 05 · Orquestación de agentes

## Modelos y suposiciones visibles

Líder: `gpt-5.6-sol`, esfuerzo `high` si el cliente lo admite. Implementadores: `gpt-6-astra`, esfuerzo `medium`. Esta segunda asignación interpreta explícitamente el texto «GPT 6 Medium» como Astra; no se presenta Medium como un modelo distinto. Revisor independiente: GPT-5.6 Sol high, contexto nuevo.

El usuario puede cambiar la variante GPT-6 mediante `tooling/model-routing.json` y `tools/configure-agents.mjs`. La documentación oficial y la disponibilidad del cliente instalado prevalecen sobre etiquetas coloquiales. No usar alias `gpt-6-medium`, no inventar acceso y no cambiar a Luna o a otro proveedor en silencio.

## Preflight real

Antes de implementar: identificar versión de Codex, cliente, modelo de la sesión, razonamiento, forma de descubrimiento de skills y agentes, sandbox y permisos de red. Guardar `artifacts/preflight.json` sin tokens. Abrir una tarea inocua de exploración con el worker y verificar en metadatos/UI el modelo efectivo; que el agente escriba «soy X» no constituye verificación. Verificar también que la sesión líder no ha heredado un override global distinto.

La documentación consultada el 28/09/2026 admite agentes TOML independientes en `.codex/agents/` con `name`, `description`, `developer_instructions` y overrides de modelo. Los valores del archivo tienen precedencia en el enrutamiento. No copiar a ciegas una configuración antigua de `[agents.role].config_file` si el cliente actual usa otro esquema.

Si el cliente no dispone de multiagente o de los modelos, registrar el bloqueo. Puede continuar documentación y comprobaciones locales no dependientes, pero no declarar orquestación real ni sustituir el requisito de revisión independiente. El bloqueo de modelo requiere que el propietario seleccione una variante disponible.

## Roles

| Rol | Modelo | Responsabilidad | Permisos de escritura |
|---|---|---|---|
| líder (sesión principal) | 5.6 Sol | Contratos, paquetes, integración, decisiones y release | Árbol del proyecto; dueño de archivos comunes |
| cuaderno_domain | 6 Astra medium | Cálculos, unidades, subrecetas, planificación, stock | Dominio y sus tests asignados |
| cuaderno_web | 6 Astra medium | UI, rutas, formularios y responsive | Componentes/rutas asignadas |
| cuaderno_data_ops | 6 Astra medium | SQL, importación, imágenes, backup/deploy | Rutas explícitas del paquete; propone migraciones |
| cuaderno_qa | 6 Astra medium | E2E, accesibilidad, benchmarks y comprobación adversarial | Tests/evidencias, no producción salvo encargo separado |
| cuaderno_reviewer | 5.6 Sol high | Revisión independiente y bloqueos de salida | Solo lectura; el líder ejecuta comandos que escriban artefactos |

No ejecutar los cinco roles simultáneamente. Límite: dos implementadores y un revisor (tres subagentes abiertos). El líder no modifica archivos que tenga asignados a un worker. Los workers no crean subagentes.

## Paquete de trabajo mínimo

Antes de delegar, el líder usa `tooling/WORK_PACKET_TEMPLATE.md`: objetivo observable, contrato, dependencias, rutas que puede tocar, rutas prohibidas, pruebas RED/GREEN, casos límite, criterios de aceptación y entrega. Tarea corta por flujo vertical, no «construye todo el backend».

Cada worker entrega un resumen de archivos, pruebas ejecutadas con código de salida, evidencia del fallo esperado, resultado verde, riesgos y decisiones no resueltas. Una lista de tareas marcadas no sustituye pruebas reales.

## Evitar conflictos

Usar worktrees/ramas locales si el cliente los admite dentro de su sandbox. No compartir la DB de desarrollo entre workers: cada uno tiene DB temporal y puerto propios. El store del gestor de paquetes puede compartirse sin copiar node_modules entre sistemas operativos.

Si no hay worktrees, usar asignación exclusiva de rutas y ejecutar secuencialmente paquetes que se solapen. No simular aislamiento. Esquema/migrations, package.json, lockfile, config común y CSS global los integra el líder. Los workers proponen cambios acotados para esos archivos, no los reescriben en paralelo.

## Ciclo por paquete

1. Líder comprueba dependencias y lee contrato.
2. Worker escribe una prueba semántica y demuestra RED por fallo esperado.
3. Implementa mínimo, obtiene GREEN, refactoriza.
4. QA o líder ejecuta pruebas afectadas en árbol integrado.
5. Reviewer nuevo inspecciona contrato, diff, pruebas y evidencias; emite hallazgos con severidad y ruta.
6. Worker corrige; reviewer comprueba correcciones.
7. Líder integra, ejecuta verificación y actualiza estado/commit local.

Dos intentos de corrección sin progreso real: parar el bucle local, reproducir mínimo y devolver diagnóstico al líder; no gastar agentes repitiendo el mismo prompt. No convertir esta regla en abandono de todo el proyecto.

## Contexto, coste y persistencia

No todos los workers necesitan todo el plan. Darles archivos/contratos relevantes y nombres de tests. Skills usan carga progresiva. No usar modelos grandes para ordenar imports o copiar una línea que un script resuelve. Registrar fallos útiles; no versionar transcripciones privadas de modelos.

Mantener tareas separadas como NOT_STARTED, IN_PROGRESS, BLOCKED, VERIFIED. La fuente de tareas es `tooling/work-packets.json`; el progreso va en `docs/STATUS.md` con evidencia. Al compactar, escribir checkpoint del diff, commit, tests y siguiente paquete; no depende de memoria informal.

## Autoridad y límites

El prompt autoriza editar, instalar dependencias del proyecto y hacer commits locales. No autoriza facturar, publicar, extraer datos de otra cuenta, comprar hosting o cambiar producción. Las credenciales/clientes antiguos son bloqueos externos; no hacen falta para construir y verificar la app con datos sintéticos.
