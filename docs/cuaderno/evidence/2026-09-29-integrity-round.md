# Correcciones de integridad y preview local

Checkout `279ba8ad8` más worktree; no push ni publicación. Los resultados no certifican cambios posteriores.

Rectificación 30/9: los PASS TypeScript de esta ronda no recorrían la aplicación; se reemplazó el comando por `-p tsconfig.app.json`, RED global con deuda upstream caracterizada. Ver STATUS y evidencia de continuación.

## TDD real

- Inventario RED: `20260929T195019Z-inventory-integrity-5f24e738.json`, cuatro fallos y un error por snapshot ausente. Reproducidos consumo nativo inexistente, clave de create cero reutilizable, densidad global indebida, historia mutable y lectura entre Households.
- Intercambio RED: `20260929T194755Z-exchange-portable-42f16cd7.json`, cinco pruebas/cuatro fallos por pérdida de enlaces/rendimiento y aceptación de ciclo/hijo privado.
- Endurecimiento de intercambio RED: `20260929T200158Z-exchange-portable-f6c3e341.json`, nombres duplicados y mapping no entero.
- GREEN integrado: `20260929T200819Z-integration-58d80fb9.json`, 52 pruebas, PostgreSQL real, 183.187 s de tests; incluye carreras de dos consumos y replay simultáneo.
- Adjuntos/servicio/borrado RED: `20260929T201311Z-native-media-services-76daa133.json`, compartir adjunto devolvía 404, servicio aceptaba receta privada ajena y borrar historial provocaba ProtectedError/500.
- GREEN integrado posterior: `20260929T201908Z-integration-a8bb6a4b.json`, 55 pruebas, 223.935 s; valida las tres correcciones anteriores, no los cambios posteriores de servicios.
- Historial nativo previo al ledger RED: `20260929T202227Z-legacy-stock-history-4235869c.json`, borrado devolvía 204 y eliminaba logs heredados. GREEN: `20260929T203033Z-legacy-stock-history-042ec4f9.json`, 1/1.
- Servicios persistentes RED: `20260929T202534Z-service-workflow-70ffb738.json`, 10 pruebas, 5 fallos y 4 errores. Fecha, estado, Household y consumo aún no implementados; también se corrige un fixture sin scope y asserts que recibían el catchall HTML. GREEN pendiente.

Todos los identificadores anteriores corresponden a ficheros JSON y logs reales de `.cuaderno-runs/`, ignorados por Git. No se rebajaron expectativas ni se omitieron tests fallidos.

## Build y comprobaciones

- `20260929T201451Z-format-7e1d532c.json`: lint Cuaderno exit 0.
- `20260929T201645Z-unit-a2fff9b0.json`: 27 pruebas de dominio, exit 0.
- `20260929T201656Z-typecheck-6191bc01.json`: Vue typecheck exit 0.
- `20260929T201822Z-local-up-135c0b6c.json`: build Docker del checkout, Vue/PWA y arranque readiness exit 0.
- Imagen local `cuaderno-cocina:local`: digest `sha256:4a3e0c7a5aaa0cf65c0f27f437a6a7f26c70514912b772797e8979762b757ca6`. No imagen final de proyecto completo.

## Revisión independiente

Una revisión anterior encontró los defectos corregidos. Tras la nueva instrucción de modelos, se interrumpieron esos agentes; `integrity_review_sol` y `native_share_sol` se lanzaron explícitamente con `gpt-6.1-sol`. El reviewer nuevo aprobó estáticamente los bloques de ledger/aislamiento, intercambio y algoritmo de backup, condicionando ejecución y documentación. No aprobó G7 ni los flujos todavía incompletos.

La configuración de modelos se actualizó según la instrucción del propietario y la [documentación oficial de subagentes](https://learn.chatgpt.com/docs/agent-configuration/subagents). La aceptación de los spawns verifica estas delegaciones, no el modelo de la sesión líder ni el acceso futuro.

## Recuperación

Primer ensayo: `20260929T195554Z-restore-71e3caae.json`, 110 tablas/808 filas/106 secuencias, todavía sin stock/media. Después se eliminó la carrera del fingerprint funcional: ahora se verifica desde una base probe restaurada del dump.

Ensayo ampliado GREEN: `20260929T202503Z-restore-86e06222.json`, bundle `data/cuaderno/backups/20260929T202047Z-e5b0ffc9`, destino nuevo `cuaderno_restore_a7fb7b1628624266bbcccd2dd7512334`; 110 tablas, 827 filas, 106 secuencias y tres archivos media. Se verificaron login de tres cuentas, cinco costes, tres saldos, denegación anónima y aislamiento entre Spaces. Dump SHA256 `f8ddf6a393024808a3eac2cc643d1f0bc1676cd537e2e76c818a64d9a775e158`; restauración 95.383 s, pausa de escrituras 12.506 s. El snapshot corresponde al build con migración 0009, no al futuro flujo de servicios 0010.

## Límite visual

Conexión al navegador repetida el 29/09: «No browser is available», lista `[]`. No capturas, prueba visual de impresión ni iPad físico. El build y la revisión de código no acreditan esas verificaciones.

## Baseline limpio y servicios (ronda posterior)

`pin_baseline.py` verifica que `f77a459ff` y el pin no difieren en código/config/tests ejecutables y exige el digest completo del baseline T002 (`sha256:68946d4df1351cf5b30c7c606243856d65681439d6db4436baed9298d88cea8b`). No monta el checkout modificado; crea PostgreSQL y red nuevos. La primera ejecución falló por suponer metadatos version_info no vacíos, sin ejecutar tests; no cuenta como baseline.

`20260929T204914Z-pin-baseline-e7b168b5.json`: ambos fallos se reprodujeron en 219.45 s. Cooklang produce el nombre de la fixture sin el prefijo «Christmas» esperado; el renderer difiere en blockquote y saneado de atributos de scalable-number. Son fallos de comparación heredados reproducidos, no una justificación para modificar tests ni afirmar ausencia de riesgos de seguridad. Los recursos aislados se conservaron (`cuaderno-pin-db-ba26cb5980ba`, `cuaderno-pin-tests-ba26cb5980ba`).

Servicios, primer candidato: `20260929T204533Z-service-workflow-564bfeda.json`, 13 tests/11 errores por FOR UPDATE sobre relaciones opcionales. Se corrige a `of=('self',)`; ejecución posterior pendiente. Origen/incompletitud RED significativo: `20260929T205223Z-service-integrity-a5e9e625.json`, snapshot sin origen y producción parcial aceptada con 200.

Unidades RED: `20260929T204038Z-format-conversion-a7541927.json` (bolsa global aceptada); RED de cadena mixta `20260929T204710Z-format-conversion-6b7d0eae.json`. La corrección valida dimensiones en cada arista genérica, no solo que exista alguna conversión específica en la cadena. GREEN pendiente.

Frontend: fecha civil/comensales y coste de presentación tuvieron RED real antes de implementar helpers; posteriormente 13/13 unitarios de formularios/retries/media pasan. Typecheck `20260929T205308Z-typecheck-0d1aa93d.json`, exit 0. Revisión estática independiente, sin aprobación visual.

## Cierre posterior y compras en curso

Integración `20260929T211547Z-integration-989512ba.json`: 76/76, 406.559 s. Incluye 17 servicios, ACL privada dinámica de raíces/hijos, FEFO, origen del documento, rollback y concurrencia. Los fallos anteriores de conversión y servicios quedan verdes en este snapshot. Frontend `20260929T211120Z-frontend-unit-f229be7f.json`: 15/15; dominio `20260929T210824Z-unit-768f01fc.json`: 27/27.

Precisión nativa: RED `20260929T211721Z-native-stock-precision-4f81893c.json` demuestra delta redondeado; GREEN `20260929T212245Z-native-stock-precision-309c8c22.json` después de localcontext64. Revisión independiente detecta además normalize() en digest; nueva regresión RED `20260929T213013Z-native-stock-precision-c57c6c2c.json` (200 en vez de 409). Un intento intermedio `8fb6c3a3` falló por indentación del test, no es evidencia del defecto funcional.

PWA: RED `20260929T212235Z-service-worker-a78d6af8.json` (3 fallos) demuestra caché privada y cola heredada. RED adicional `20260929T212540Z-service-worker-443e80a2.json` cubre fallback/session y caché offline anterior. GREEN `20260929T212628Z-service-worker-8ad36915.json`: 4/4, rutas NetworkOnly, ninguna escritura encolada, purga solo caches legados conocidos por origen y descarte de cola sin replay. Fallback 503 español constante/no-store. Son pruebas unitarias del worker transpileado con adaptadores Workbox, NO navegador real/IndexedDB real. Política sustentada en [Workbox strategies](https://developer.chrome.com/docs/workbox/modules/workbox-strategies) y [Background Sync](https://developer.chrome.com/docs/workbox/modules/workbox-background-sync).

Compras RED `20260929T212355Z-purchasing-d0260866.json`: cinco errores por ausencia de rutas y calculadora antigua sin validación. Se implementan ofertas sobre Supermarket nativo, pedidos sin saldo y recepciones sobre InventoryEntry/ledger; verificación y revisión pendientes. Migración 0012 aplicada al PostgreSQL de tests, no a preview release todavía.
