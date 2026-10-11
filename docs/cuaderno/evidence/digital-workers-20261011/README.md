# Trabajadores digitales locales — evidencia del candidato

Fecha: 2026-10-11. Fuente base: `9e645c7`; cambios de esta campaña en el
commit que incorpora este documento. Implementación local, no desplegada.

## Alcance entregado

Ocho análisis deterministas, dos acciones aprobables (versiones de precios y
pedido nativo en borrador), CSV estricto, simulación de costes, evidencia con
huellas SHA-256, historial reautorizado, propuestas obsoletas, reintentos sin
duplicación y programación de informes de solo lectura. Navegación, formularios,
resultados, confirmación, descargas y accesos contextuales integrados en Vue.

Detalle funcional y límites: [manual](../../TRABAJADORES_ES.md).
Arquitectura y alternativas gratuitas investigadas: [ADR 0015](../../adr/0015-local-digital-workers.md).
No dependencia nueva de runtime, proveedor de IA ni clave API.

## Entorno y aislamiento

- PostgreSQL 16 propio: `cuaderno-workers-db`, red `cuaderno-workers-test`, base
  sintética `cuaderno_demo` y base de pruebas `test_cuaderno_native_workers`.
- Aplicación `cuaderno-workers-web`, imagen base productiva existente con fuente
  candidata montada, migraciones nuevas aplicadas solo al entorno aislado,
  activos compilados y Gunicorn. Escucha solo en `127.0.0.1:18083`.
- El navegador muta únicamente esa URL: la configuración rechaza otro destino.
  Credenciales sintéticas en archivo privado fuera de Git; no se incluyen aquí.
- Producción `cuaderno-prod-*`, puerto 18081, no se usa para tests ni migraciones.
  No se construyó una nueva imagen inmutable ni se ejecutó un despliegue.
- Node 24.19.0; navegador real Chromium/Chrome for Testing 151.0.7922.34.

## Resultados verificados

| Comprobación | Resultado | Evidencia local |
|---|---|---|
| Suite completa Cuaderno/PostgreSQL | 734 PASS, 347,54 s | `backend-regression.log` |
| Suite final de trabajadores, análisis y programación | 42 PASS, 18,44 s | `workers-final.log` |
| Suite completa frontend final | 355 PASS; 0 fallos/omisiones | `frontend-regression.log` |
| UI final, incluido render de costes | 23 PASS; 0 fallos/omisiones | `frontend-ui-tests.log` |
| Tipos Vue y compilación Vite final | Ambos exit 0 | `frontend-typecheck.log`, `frontend-build.log` |
| Navegador Chromium final | 8 PASS, 47,2 s; 0 fallos/omisiones/reintentos | [JSON](browser-results.json), `browser-test.log` |
| Django check | Sin incidencias | `django-check.log` |
| Consistencia de migraciones | Sin cambios pendientes | `migrations-check.log` |

Las 42 pruebas enfocadas se solapan con la suite completa; no se suman como
pruebas distintas. Incluyen una regresión adicional posterior a la suite completa
para fuentes borradas en el historial. El último ajuste visual está incluido en la suite frontend final y en el
recorrido de navegador final.

Las pruebas del backend cubren Decimal, entradas inválidas y cero explícito,
subrecetas, ausencia de escrituras de negocio en los ocho informes, permisos
actuales, aislamiento de hogares, revocación con caché, CSRF, recepción/conversión,
reposición por período, stock caducado, fuentes eliminadas, aprobación explícita,
obsolescencia, concurrencia real y programación sin acciones de escritura.

El navegador recorre los ocho informes, aprobación y lectura del precio guardado,
borrador de compra sin cambio de stock, rechazo 409 y regeneración tras un cambio
externo, programación diaria/semanal y fechas móviles/fijas, descarga JSON y
anchos 390/768/1440 px. Los contadores de negocio comprueban que el análisis no
modifica precios, pedidos ni inventario. La consola se comprueba durante los casos.

## Reproducción

Los comandos `workers-backend` y `workers-ui` están registrados en
`tooling/cuaderno/commands.json`; requieren el entorno aislado descrito, nunca
sustituirlo por el contenedor productivo. Para la suite completa del frontend:

```sh
CUADERNO_MARKDOWN_TEST_CONTAINER=cuaderno-workers-web \
  /opt/jaautomation/runtime/node-v24.19.0/bin/node --test --test-concurrency=1 \
  vue3/src/cuaderno/*.test.mjs
```

Desde `vue3/`, con sus dependencias fijadas instaladas:

```sh
/opt/jaautomation/runtime/node-v24.19.0/bin/node node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.app.json --pretty false
/opt/jaautomation/runtime/node-v24.19.0/bin/node node_modules/vite/bin/vite.js build
```

Tras recopilar los activos en el runtime aislado, desde `tests/cuaderno/e2e/`:

```sh
CUADERNO_WORKER_BROWSER_EXECUTABLE=/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome \
  /opt/jaautomation/runtime/node-v24.19.0/bin/node node_modules/@playwright/test/cli.js \
  test -c digital-workers.config.ts
```

## Incidencias de ejecución y límites de la evidencia

Se conservan localmente los intentos incompletos: una ejecución inicial coincidió
con la incorporación de la migración de programación; otra fue interrumpida por
un reinicio externo del VPS. La suite completa válida se ejecutó después, con
esquema fresco y JIT desactivado según el contrato de tests existente. El test
heredado de Markdown apuntaba a un contenedor antiguo detenido: se añadió una
selección restringida entre los dos contenedores de prueba, conservando sus
aserciones. La ejecución completa posterior aprobó.

Los logs `.log` siguen la exclusión existente de Git y se conservan en el VPS.
El informe JSON, capturas sintéticas y [registro con hashes](verification.json)
se conservan como evidencia versionada.
No se incluyen trazas con sesiones ni credenciales. Los avisos existentes de
Vite sobre tamaño de bundle, `eval` de mavon-editor y opción de service worker
no se presentan como corregidos.

No se certifica aquí Firefox, WebKit, iPad físico, carga a gran escala, la matriz
histórica G7, backup/restauración de una imagen nueva ni aceptación pública.
El temporizador periódico no está instalado; el comando y sus permisos sí están
probados. Lectura PDF/OCR, correo, envío a proveedores, predicción y optimización
global de menús no forman parte de esta entrega ni se anuncian como pendientes
únicamente de una clave LLM.

## Revisión independiente y capturas

La revisión final de otro agente inspeccionó servicios, análisis/simulación,
programación, API, permisos, modelos/migraciones, integración de compras y tests.
No encontró bloqueos concretos de backend; no ejecutó una segunda suite ni accedió
a producción. El agente de interfaz comprobó formularios y navegador; el líder
revisó el diff integrado y las capturas. La revisión no sustituye las limitaciones
operativas y de navegadores indicadas arriba.

- [Móvil 390 px](browser/digital-workers-worker-report-stays-usable-at-390px/workers-390.png)
- [768 px](browser/digital-workers-worker-report-stays-usable-at-768px/workers-768.png)
- [Escritorio 1440 px](browser/digital-workers-worker-report-stays-usable-at-1440px/workers-1440.png)

El ajuste final muestra total y coste por ración, colapsa detalles del motor y
recorta únicamente ceros decimales redundantes para presentación. El navegador
comprueba que el JSON descargado conserva los valores originales. No cambia
el cálculo ni la precisión del backend.
