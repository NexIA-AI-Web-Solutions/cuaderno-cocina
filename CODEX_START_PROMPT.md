Lee AGENTS.md y ejecuta este encargo, no entregues otro plan.

El producto es Cuaderno Cocina, un derivado REAL de Tandoor. El propietario prefiere expresamente su interfaz y tiene permisos en contratos separados; esta premisa está resuelta para este trabajo. No volver a proponer Grocy como base ni SvelteKit/greenfield. No levantar Mealie, KitchenOwl y Grocy en producción: sus clones fijados son fuentes para adaptaciones selectivas y tests.

Objetivo: construir y verificar las tres ediciones en español, empezando por Esencial 500 € + 17 €/mes, después Profesional 1000 + 20 e Integral 1500 + 30. Precios son metadata comercial. Mantener UI Tandoor reconocible y responsive en móvil/iPad/escritorio, cálculos exactos, rapidez y mantenimiento sencillo. No borrar funcionalidades nativas útiles para inventar diferencias entre planes.

1. Verifica git status, source-lock, Bootstrap report y modelo/cliente efectivo. Sesión líder GPT-5.6 Sol high; implementadores GPT-6 Astra medium (interpretación declarada de GPT 6 Medium), reviewer GPT-5.6 Sol high en contexto independiente. Usa configuración .codex/agents y skills locales; no finjas acceso ni delegación. Si falta un modelo, registra y no sustituyas silenciosamente.
2. Lee en orden docs/cuaderno/00-DECISION, 01-SCOPE, 02-REUSE-MAP, 03-ARCHITECTURE, 04-DOMAIN-CONTRACTS, 13-ORCHESTRATION y 14-ROADMAP-AND-GATES. Carga otros docs por tarea.
3. Arranca Tandoor sin modificaciones en entorno aislado compatible con el pin. Inspecciona pipeline Vue y PostgreSQL. Guarda baseline de tests/capturas. Verifica modelos Food/Unit/Recipe/Space, properties, menús/listas e inventario antes de construir equivalentes.
4. Delega exploración separada de base y donantes. No adoptes carpetas enteras: concreta diferencias, símbolos, tests y adaptación. Reutilizar > extender > portar pieza > desarrollar carencia.
5. Ejecuta T001–T038. Máximo 3 hijos y dos escritores disjuntos. Un solo integrador para core/models/migraciones/lockfiles/settings/router. Revisión independiente de cada cambio funcional y de gates.
6. TDD y pruebas reales: dinero Decimal, no precio desconocido=0, stock idempotente/concurrente, permisos privados/Spaces, imports seguros y restore completo. Usa los contratos de tests/cuaderno, no devuelvas sus datos como aplicación.
7. Llena tooling/cuaderno/commands.json con comandos VERIFICADOS del checkout. Usa scripts/cuaderno/check.py para registrar runs y fallos. Implementa código/persistencia/UI, no solo documentación, stubs o prototipo. G2 debe dar preview Esencial local utilizable; continúa con siguientes gates.
8. Mantén STATUS/BLOCKERS/ADR/REUSE_LEDGER/UPSTREAM_PATCHES/evidencias. Ante un bloqueo real, explica alcance exacto y avanza tareas independientes; no preguntes detalles ya resueltos ni pares por decisiones menores. Falta de export del programa antiguo bloquea solo su extractor; no limita el importador genérico.
9. Entrega G7 con build local probado, instrucciones exactas, datos sintéticos, manuales españoles, comprobación de backups/restore y resultado real de tests. No declarar iPad físico, migración cliente o despliegue VPS como hechos si no se hicieron.

Autorización: clonar referencias fijadas, leer, editar este proyecto, instalar dependencias locales/aisladas y ejecutar tests; commits focalizados locales. NO push, PR, publicación, despliegue externo, compra, envío a cliente, acceso a datos reales o modificación de otros proyectos. No borrar .git, trabajar sobre bases reales ni limpiar volúmenes ajenos. No usar --yolo.

Si termina contexto/cuota, deja un checkpoint reanudable con comandos y archivos pendientes, no una falsa finalización. Empieza por G0 ahora y continúa hasta completar lo ejecutable de principio a fin.
