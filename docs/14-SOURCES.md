# 14 · Fuentes primarias

Consultadas el **28/09/2026**. Son referencias de capacidades técnicas, no evidencia de una implementación ya construida. Al ejecutar el plan, comprobar versiones, parches y compatibilidad del entorno; no arrastrar flags obsoletos.

## S01 · Codex: modelos y selección

https://learn.chatgpt.com/docs/models

Uso en el plan: IDs, selección de modelo, esfuerzo y disponibilidad por cliente.

## S02 · GPT-5.6 Sol: ficha del modelo

https://developers.openai.com/api/docs/models/gpt-5.6-sol

Uso en el plan: Identificación oficial del modelo solicitado como líder; el acceso local se comprueba aparte.

## S03 · Codex: subagentes

https://learn.chatgpt.com/docs/agent-configuration/subagents

Uso en el plan: Agentes TOML independientes, precedencia, defaults y límites de concurrencia.

## S04 · Codex: creación y descubrimiento de skills

https://learn.chatgpt.com/docs/build-skills

Uso en el plan: SKILL.md con name/description, .agents/skills y carga progresiva.

## S05 · Codex: referencia de configuración

https://learn.chatgpt.com/docs/config-file/config-reference

Uso en el plan: Verificar campos admitidos por la versión instalada.

## S06 · Codex: sandbox Windows

https://learn.chatgpt.com/docs/windows/windows-sandbox

Uso en el plan: Flujo nativo PowerShell; no WSL obligatorio.

## S07 · Codex CLI

https://learn.chatgpt.com/docs/codex/cli

Uso en el plan: Instalación, acceso y ejecución local.

## S08 · Node.js: líneas de versiones

https://nodejs.org/en/about/previous-releases

Uso en el plan: Node 24 aparece como LTS a la fecha de consulta; 26 como Current.

## S09 · SvelteKit: adapter-node

https://svelte.dev/docs/kit/adapter-node

Uso en el plan: Build servidor y configuración ORIGIN/proxy.

## S10 · SvelteKit: form actions

https://svelte.dev/docs/kit/form-actions

Uso en el plan: Formularios servidor con mejora progresiva; distinguir funciones experimentales.

## S11 · Drizzle: SQLite

https://orm.drizzle.team/docs/sqlite/get-started-sqlite

Uso en el plan: Integración con SQLite; fijar APIs de la versión instalada.

## S12 · Better Auth: instalación

https://better-auth.com/docs/installation

Uso en el plan: Configuración oficial y adaptadores de datos.

## S13 · Better Auth: SvelteKit

https://better-auth.com/docs/integrations/svelte-kit

Uso en el plan: Integración de handlers/sesiones con el framework.

## S14 · SQLite: usos adecuados

https://www.sqlite.org/whentouse.html

Uso en el plan: Modelo de despliegue y límites frente a bases cliente-servidor.

## S15 · SQLite: WAL

https://sqlite.org/wal.html

Uso en el plan: Concurrencia, archivos WAL y restricciones de disco/red.

## S16 · SQLite: historial de versiones

https://sqlite.org/changes.html

Uso en el plan: Parches, arreglo WAL-reset de 2026 y releases retiradas; verificar runtime.

## S17 · better-sqlite3: API

https://github.com/WiseLibs/better-sqlite3/blob/master/docs/api.md

Uso en el plan: Transacciones y API backup; seguir versión fijada, no asumir un API propio.

## S18 · Tailwind: compatibilidad

https://tailwindcss.com/docs/compatibility

Uso en el plan: Requisitos de navegador; cotejar con iPad real.

## S19 · Playwright: emulación

https://playwright.dev/docs/emulation

Uso en el plan: Viewports, dispositivos y contexto de navegador; no sustituye prueba en hardware físico.

## S20 · pnpm: instalación

https://pnpm.io/installation

Uso en el plan: Instalación Windows mediante npm y compatibilidad; fijar después versión exacta.

## S21 · Git para Windows

https://git-scm.com/install/windows

Uso en el plan: Descarga oficial.

## Diferenciar hechos de decisiones

Los precios y requisitos provienen del WhatsApp aportado por el usuario, no de estas webs. El stack, límites de recursos, fases, tokens visuales y reglas de proceso son decisiones propuestas para este proyecto. Los benchmarks son objetivos pendientes de medir. No hay una promesa de compatibilidad, disponibilidad de modelos o rendimiento basada solamente en una URL.
