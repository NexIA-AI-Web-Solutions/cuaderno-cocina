# Arranque en Windows 11

## Nombre y carpeta

- Nombre visible: **Cuaderno Cocina** (nombre de trabajo, no comprobación de marca o dominio).
- Repositorio sugerido: `cuaderno-cocina`, privado inicialmente.
- Descripción: `Aplicación web ligera en español para recetas, escandallos, planificación de cocina y control de existencias.`
- Carpeta: `$HOME\Proyectos\cuaderno-cocina`. No necesitas WSL, una GPU o Docker para desarrollar.

## Herramientas

Instala Git para Windows, Node.js **24 LTS** con un parche mantenido y Codex. PowerShell 7 es recomendable. No reinstales herramientas que ya funcionen; comprueba sus versiones. Enlaces oficiales en `docs/14-SOURCES.md`.

Si ya tienes la app de Codex/ChatGPT Codex con acceso a los modelos, abre ahí la carpeta. La CLI es una alternativa, no una segunda suscripción obligatoria. El flujo de suscripción y el de API son distintos: este proyecto no configura una API key ni autoriza gasto de API.

Para instalar la CLI desde npm, cuando no esté instalada:

```powershell
npm install -g @openai/codex
codex --version
```

Para el gestor de dependencias, usa el instalador recomendado por pnpm en Windows:

```powershell
npx get-pnpm
pnpm --version
```

El líder registrará el resultado, comprobará compatibilidad y fijará la versión exacta en `packageManager`. No actualices dependencias durante cada arranque. No añadas exclusiones al antivirus para acelerar instalaciones.

## Extraer

Guarda `cuaderno-cocina-codex-kit.zip` en Descargas. En PowerShell:

```powershell
$Project = Join-Path $HOME 'Proyectos\cuaderno-cocina'
$Zip = Join-Path $HOME 'Downloads\cuaderno-cocina-codex-kit.zip'
New-Item -ItemType Directory -Force -Path $Project | Out-Null
if ((Get-ChildItem -Force $Project | Measure-Object).Count -gt 0) {
    throw 'La carpeta no está vacía. Usa una nueva para no sobrescribir un proyecto.'
}
Expand-Archive -LiteralPath $Zip -DestinationPath $Project
Set-Location $Project
node tools/check-handoff.mjs
node --test tools/handoff.test.mjs
```

En algunos equipos Descargas está redirigida. En ese caso extrae con el Explorador, sin añadir una carpeta interior extra. Debes ver `AGENTS.md` directamente en la raíz.

## Abrir Codex

1. Abre la carpeta del proyecto; revisa y confía en sus instrucciones locales cuando el cliente lo solicite.
2. Selecciona **GPT-5.6 Sol** para el líder, con esfuerzo **high** si aparece disponible.
3. Pega íntegro `CODEX_START_PROMPT.md`. Usa modo de trabajo/edición, no una sesión que únicamente produzca un plan.
4. Los workers se configuraron como `gpt-6-astra`, `medium`. Se interpreta así «GPT 6 Medium»; no se presupone que cualquier nombre del selector sea un ID de API.
5. El preflight comprobará los IDs, el esquema de agentes y los permisos realmente admitidos. Un modelo no disponible es un bloqueo explícito, no motivo para sustituirlo en silencio.

Alternativa CLI:

```powershell
Set-Location (Join-Path $HOME 'Proyectos\cuaderno-cocina')
codex -m gpt-5.6-sol
```

Dentro de la sesión, revisa `/model` y pega el prompt. La sintaxis final depende de la versión instalada; `codex --help` y la documentación oficial prevalecen. No utilices `--yolo`.

## Cambiar solo la interpretación de GPT 6

La asignación está centralizada en `tooling/model-routing.json`. Para elegir otra variante verificada, por ejemplo GPT-6 Sol en medium:

```powershell
node tools/configure-agents.mjs --worker-model gpt-6-sol
```

Esto cambia los archivos locales de configuración; no compra acceso ni demuestra disponibilidad. Reinicia la sesión si no se refleja el cambio.

## Cuando la app esté implementada

El líder debe haber creado y probado esta interfaz de comandos:

```powershell
pnpm install --frozen-lockfile
pnpm setup:local
pnpm dev
```

`setup:local` solo inicializa datos locales vacíos, con credenciales aleatorias o introducidas de forma interactiva. Nunca sobrescribe una base existente. La consola indica la URL local. `pnpm demo:seed` es opcional y exige una base de demostración vacía; no existe una contraseña demo activa en producción.

La revisión final exige además:

```powershell
pnpm verify
pnpm exec playwright install chromium webkit firefox
pnpm test:e2e:release
pnpm test:restore
pnpm bench
pnpm release:check
```

Codex no debe decir que terminó porque escribió estos comandos: debe ejecutarlos y guardar sus resultados. Las pruebas de navegadores descargan binarios de desarrollo que no se suben al VPS.

## Sesiones largas

Una pausa de contexto o un límite de la herramienta no es una entrega. Abre una nueva sesión en la misma carpeta y pega `CODEX_RESUME_PROMPT.md`. No existe garantía de completar cualquier proyecto en un único turno; sí un protocolo para continuar sin perder trabajo ni inventar resultados.
