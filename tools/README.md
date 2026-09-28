# Herramientas del handoff

- `check-handoff.mjs`: valida archivos, precios, fases, dependencias y configuración local.
- `handoff.test.mjs`: comprueba oráculos numéricos sintéticos y consistencia del plan, sin dependencias.
- `configure-agents.mjs`: regenera archivos TOML desde las dos configuraciones JSON. No ejecuta agentes ni verifica acceso a modelos.
- `preflight.mjs`: inventario de Node/Git/pnpm/Codex; no instala nada ni envía datos a la red. Su salida va a artifacts/, fuera de Git.

Se ejecutan con Node, sin Python, Office, Docker o GPU. Los scripts de la app se implementarán en `scripts/`, separados de estas herramientas.
