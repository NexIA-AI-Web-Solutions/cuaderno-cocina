# 01 · Arquitectura y decisiones técnicas

## Stack elegido

| Capa | Elección | Razón de diseño |
|---|---|---|
| Runtime | Node.js 24 LTS, parche mantenido | Una sola plataforma Windows/Linux y menos runtimes |
| App | SvelteKit + Svelte, versiones estables compatibles | Servidor y UI en un repositorio; renderizado servidor y formularios con mejora progresiva |
| Lenguaje | TypeScript `strict` | Contratos compartidos, errores antes del despliegue |
| Estilo | Tailwind CSS estable, tokens propios y componentes pequeños | CSS compilado; no kit de administración gigantesco |
| UI compleja | Primitivas accesibles mantenidas solo cuando necesarias | No reinventar foco/teclado de un diálogo o combobox |
| Datos | SQLite, `better-sqlite3` mantenido, Drizzle | Archivo local, migraciones auditables, sin servicio de BD separado |
| Acceso | Better Auth con adaptador Drizzle/SQLite | Sesiones/contraseñas de una librería mantenida; sin autenticación artesanal |
| Validación | Zod | Límites y contratos en cada entrada servidor |
| Costes | decimal.js | Precisión decimal; sin floats monetarios |
| Imágenes | sharp, si la versión tiene binarios compatibles | Redimensionar y re-codificar; no conservar fotos gigantes por defecto |
| Pruebas | Vitest, Playwright, axe | Dominio, integración, navegadores y accesibilidad |
| Publicación | adapter-node + Caddy + servicio Linux | Un proceso de app; TLS/proxy separados; sin depender de proveedor cloud |

No se incluyen versiones menores inventadas. En T001 se consultan fuentes oficiales/registro, se eligen releases no preliminares compatibles, se auditan y se fija todo con versión exacta y lockfile. Comprobar también el SQLite realmente embebido con `select sqlite_version()`; no basta instalar un paquete npm reciente.

## Por qué no elegir una arquitectura grande

No React + API Python + Redis + PostgreSQL + workers + almacenamiento remoto + IA. El problema inicial es edición de recetas y aritmética. La decisión de un monolito modular busca reducir piezas que actualizar, datos que respaldar y errores de integración. No es una afirmación de que otro framework sea lento.

Tampoco se clona un gestor gastronómico completo antes de verificar el encaje. Se reutilizan dependencias y patrones con procedencia registrada. Un fork completo obligaría a cargar su funcionalidad, licencias, actualizaciones y modelo de datos.

## Flujo

```text
Navegador / icono de inicio
       HTTPS
Caddy —> SvelteKit (Node, 127.0.0.1)
                | acciones/load con auth + validación
                v
       servicios de aplicación
          |             |
     dominio puro   repositorios SQL
                         |
                 SQLite + archivos privados
                         |
              backup coherente y verificable
```

Usar `load` del servidor y form actions; no remotes experimentales ni fetches en cascada innecesarios. La UI puede simular cálculos con el mismo dominio puro, pero el servidor recalcula y valida todo lo guardado.

## Separación

`domain/` no conoce framework ni DB. `application/` coordina casos de uso y transacciones. `server/db/` contiene esquema y consultas concretas. `routes/` adapta HTTP a casos de uso. `components/` muestra datos y recoge intención.

Interfaces de repositorio solo donde aporten un límite real: costes, persistencia y almacenamiento de imágenes. No crear veinte capas por cada CRUD.

## SQLite y crecimiento

Un proceso de app, disco local persistente, WAL, foreign keys, transacciones cortas y timeout acotado. SQLite no se comparte por SMB/NFS/OneDrive, no va en un filesystem efímero y no se replica copiando un archivo vivo. Las operaciones importación/backup se serializan con las escrituras cuando lo exija el runbook.

WAL permite concurrencia de lectores y escritor, no varios escritores simultáneos. Evitar `await` o llamadas de red dentro de transacciones de better-sqlite3. Trabajos pesados: scripts de administración o worker threads puntuales, no bloquear el event loop durante miles de filas o compresión.

Reconsiderar PostgreSQL si se necesitan varios servidores de app con escritura, alta concurrencia de cambios o multiempresa compartida. La portabilidad se facilita con servicios y exportación versionada; migrar a PostgreSQL requiere una migración probada, no se promete cambiar un string y listo.

Si ya se hubiese acordado PostgreSQL expresamente con la clienta, conservar ese acuerdo y registrar una revisión arquitectónica antes de cambiarlo. En la conversación aquí solo se propuso previamente como recomendación, no consta su aceptación.

## Runtime sin herramientas de desarrollo

Producción contiene el build y las dependencias de ejecución, no pnpm store, tests, vídeos, Chromium, fuentes de ejemplo o SDK de Codex. No imprimir PDFs ejecutando un navegador pesado en cada servidor: fichas HTML con CSS de impresión, que el navegador del usuario puede guardar como PDF.

Manifest y acceso desde pantalla de inicio son comodidad opcional. Esta versión requiere conexión para guardar; no lleva service worker que almacene recetas, sesiones o stock en caché privada. No venderlo como app offline.
