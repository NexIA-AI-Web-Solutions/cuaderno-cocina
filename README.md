# Cuaderno Cocina · paquete de desarrollo para Codex

Aplicación privada de recetas, costes, planificación y existencias. Interfaz y documentación en español.

**Este ZIP es un paquete de especificaciones, agentes, skills, casos de prueba y herramientas de arranque. No es una aplicación terminada.** Codex debe implementar y demostrar el producto siguiendo las puertas de aceptación.

## Empieza aquí

1. Extrae el ZIP directamente en `$HOME\Proyectos\cuaderno-cocina`.
2. Lee `START_HERE_ES.md`.
3. Abre esa carpeta con Codex y pega `CODEX_START_PROMPT.md` en una sesión con capacidad de editar y ejecutar, no solo de planificar.
4. El líder recorre `docs/07-IMPLEMENTATION-PLAN.md` y `tooling/work-packets.json` hasta la entrega local completa.

## Decisiones cerradas

- Un repositorio, una app SvelteKit, TypeScript, SQLite, interfaz adaptable y servidor Node 24 LTS.
- Desarrollar los tres niveles de forma incremental. La instalación para Elisabeth empieza en **Esencial**.
- Última oferta realmente enviada: **500 € + 17 €/mes**, **1.000 € + 20 €/mes**, **1.500 € + 30 €/mes**. No reutilizar los 2.000 € de borradores anteriores.
- Líder: GPT-5.6 Sol. Interpretación explícita de «GPT 6 Medium»: **GPT-6 Astra con razonamiento medium**, configurable.
- No se instala una IA en la aplicación ni se necesitan tokens para calcular recetas.
- No se accede al programa antiguo ni se despliega en un servidor real sin acceso y autorización.

## Contenido

`AGENTS.md` es el mapa; `docs/` contiene contratos y decisiones; `.agents/skills/` contiene ocho skills locales; `.codex/agents/` contiene cinco roles especializados; `tooling/` contiene configuración y tareas; `examples/` contiene datos sintéticos; `tools/` contiene comprobaciones del paquete.

`PLAN_COMPLETO.md` reúne los documentos técnicos para leerlos seguidos. La autoridad durante la implementación son los documentos separados en `docs/`; no editar ambos a mano.

## Comprobación del paquete, sin dependencias

```powershell
node tools/check-handoff.mjs
node --test tools/handoff.test.mjs
```

Estos comandos comprueban el material de partida. **No prueban que la aplicación esté implementada.** Los comandos `pnpm dev`, `pnpm verify` y demás se crean en las primeras tareas de Codex.

Paquete elaborado: 28 de septiembre de 2026. Las versiones exactas y las capacidades reales de Codex se verifican y congelan en G0, no se inventan aquí.
