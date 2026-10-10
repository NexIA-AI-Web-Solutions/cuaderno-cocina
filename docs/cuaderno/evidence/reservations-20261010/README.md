# Validación local de reservas — 10 de octubre de 2026

Implementación en `/home/kripta/cuaderno-reservas-20261010`, rama `cuaderno/reservas-20261010`, sobre `4335e6e9b858581c724e154c799c095cddb88383`. [Hashes de los 43 archivos de código, tests y contrato cambiados](source-manifest.json). No se ha desplegado ni publicado. El servidor indicado por el usuario conserva su aplicación anterior.

## Alcance y resultados

Se añadieron reservas en Profesional e Integral, revisión de cambios y motivos, permisos por rol y hogar, resumen diario por versión del menú y producción con los servicios y movimientos nativos. La guía funcional está en [RESERVAS_ES](../../RESERVAS_ES.md).

| Comprobación | Resultado |
|---|---|
| Suite Django `cuaderno.tests`, PostgreSQL aislado | 669 ejecutados: **668 PASS, 1 FAIL** de rendimiento concurrente; 568,823 s, exit 1. [Registro](backend-validation.json); log local `backend-full-final.log`. |
| Regresiones de integración de reservas | 10 PASS; rojo inicial conservado para las mutaciones externas, el calendario retirado y la precisión de consumo. |
| Componentes y validación de reservas | 19 PASS. [Registro](frontend-validation.json). |
| Suite frontend, Node 24.21, ejecución secuencial de 68 archivos | 430 casos: 428 PASS, 2 FAIL preexistentes de portadas de menú. Ambos reproducidos en la fuente anterior sin cambios. |
| TypeScript de la aplicación | `vue-tsc --noEmit -p tsconfig.app.json`: exit 0. El intento previo sin proyecto explícito no certificaba la aplicación; se conserva el diagnóstico y su corrección. |
| Build Vue/PWA | Exit 0; snapshot aislado de 774 archivos fuente comparados por SHA256 antes de instalar los assets locales. [Entradas](frontend-build-inputs.json). |
| Migraciones | `makemigrations --check --dry-run`: sin cambios pendientes. Migración 0020 aplicada en PostgreSQL del preview. |
| OpenAPI y SDK | Generación `--validate --fail-on-warn` sin avisos; snapshot actualizado y SDK reproducible mediante generador fijado, `--check` exit 0. |
| Revisión independiente | [V1](review/fresh-diff-review-v1.md), [V2](review/fresh-diff-review-v2.md), [V3](review/fresh-diff-review-v3.md): corregidos los cuatro bloqueos y el caso de usuario sin hogar. |

Las pruebas frontend anteriores se conservan en `frontend-suite-node24-serial.log`; los dos fallos heredados se reproducen en `frontend-baseline-menu-media.log`. El intento con Node 20 no soportaba los tests TypeScript del repositorio y no cuenta como validación. El test de límites comerciales incorpora la nueva capacidad de reservas en sus fixtures y comprueba los tres planes.

## Navegadores reales

Tres agentes utilizaron Chromium/Playwright real, sesiones separadas y cuentas sintéticas. La copia local utiliza PostgreSQL independiente y escucha únicamente en loopback. Las credenciales aleatorias están fuera del repositorio, en `/tmp/reservas-preview-credentials.json`, modo 600. Nunca se incluyen contraseñas, cookies o estados de sesión en los informes.

- **Esencial:** 27 comprobaciones PASS entre Responsable, Cocina y Consulta: navegación, acceso directo sin controles de reservas, comparación comercial y anchos 390/768/1024/1440. [Informe](browser-esencial/report.md).
- **Profesional:** 22 comprobaciones PASS: altas reales, confirmación de 20 + 15 + 30 + 10 = 75, dos platos, persistencia, historial legible, conflicto 409 entre dos pestañas, Cocina, Consulta, cambios de menú y anulación por Responsable. Las cuatro reservas finales se repitieron sobre el último bundle y quedan como demo confirmada. [Informe externo de esta sesión](../../../../../cuaderno-informes-20261009/browser-audit-20261010/profesional/reservations-preview/report.md).
- **Integral:** 11 comprobaciones PASS: Cocina confirma 75 comensales sin alterar stock, necesidades por periodo, producción, anulación con compensación exacta, servida fuera de pendientes, pedido sin consumo/entrada y recepción de 10 kg, más Consulta sin acciones. [Informe externo de esta sesión](../../../../../cuaderno-informes-20261009/browser-audit-20261010/integral/preview-reservations/report.md). Los huecos explícitos del informe no se presentan como probados.

El informe Profesional distingue los pasos del bundle previo de las comprobaciones repetidas sobre el último, que incorpora correcciones de tipos. Los intentos con fecha de filtro no persistida, etiqueta de comparación equivocada, proxy temporal interrumpido y límite nativo de 5 inicios de sesión/minuto/IP se conservan como incidencias del ensayo; no se contabilizan como fallos funcionales de reservas. No se ha desactivado el limitador.

El navegador Integral encontró un fallo real: un rendimiento 0,9 producía una necesidad periódica que excedía los 16 decimales del libro de stock. Se comprobó que el fallo revertía todos los platos, conservando ambas existencias a 100 kg. Tras corregir la asignación a lotes, se repitió sobre la misma reserva y receta: 20 comensales consumieron 5 kg y 2,2222222222222223 kg; anular devolvió exactamente ambos movimientos. La producción y cierre de 15 comensales dejó 96,25 kg y 98,3333333333333333 kg; recibir el pedido añadió 10 kg al primer ingrediente. Se conserva el fallo original como resuelto. [Revisión independiente](review/storage-precision-review.md); 87 pruebas dirigidas PASS en `recurring-yield-green-final.log`, incluidas tres regresiones nuevas con merma periódica, unidades distintas y una cola decimal superior a 28 dígitos.

## Entorno, límites y reproducción

Se reutilizó el runtime Python de la imagen anterior con los módulos del checkout montados y frontend recompilado. Esto valida código local, no una imagen nueva de entrega. El seed `scripts/cuaderno/seed_reservation_preview.py` exige la base efectiva `reservas_preview`, crea nueve cuentas, plantillas, recetas y existencias sintéticas, y rechaza sobrescribir credenciales o fixtures existentes.

Comandos principales, con el entorno de pruebas aislado ya preparado:

```sh
docker exec -e LITELLM_LOCAL_MODEL_COST_MAP=True -e DJANGO_SETTINGS_MODULE=recipes.test_settings cuaderno-reservas-20261010-test /opt/recipes/venv/bin/python manage.py test cuaderno.tests --noinput --keepdb --verbosity 1
cd vue3
node --test src/cuaderno/reservationsUi.test.mjs src/cuaderno/reservationsPage.test.mjs
node node_modules/.bin/vue-tsc --noEmit -p tsconfig.app.json
```

El build final se ejecutó en `/srv/mail/cuaderno-reservas-build-20261010` para usar el volumen con espacio disponible, conservando la procedencia de dependencias y sin relajar el verificador. El primer ensayo general falló por fixtures/dependencias ausentes y disco lleno; se repitió desde una base de tests nueva después de corregir el entorno. No se borraron datos de la aplicación publicada ni se limpiaron imágenes o recursos de otros proyectos.

La base sintética se trasladó al mismo volumen con espacio (`/srv/mail/cuaderno-reservas-runtime-20261010/postgres`). Se detuvieron únicamente sus contenedores, se compararon hashes de todos los archivos antes del arranque y los recuentos de usuarios/reservas/movimientos después; solo entonces se retiró la copia duplicada del volumen anterior. [Recibo del traslado](runtime-relocation.json). El proxy definitivo es un contenedor propio de 64 MiB publicado solo en `127.0.0.1:18082`; no depende de la duración de una terminal.

El benchmark final midió un p95 concurrente de movimientos de 1.704,959 ms frente a un objetivo de 800 ms con recursos limitados y carga compartida. **El control de rendimiento falla**. El registro anterior de 666 casos no permite certificar PASS: carece de resumen unittest y contiene una medición de 1.690,73 ms que contradice ese resultado. Se conserva como intento histórico y se retira la afirmación de suite aprobada. Tampoco se ha ejecutado una nueva CI completa, G7, una imagen final, backup/restauración de esta migración, WebKit/Firefox o iPad físico.

El SDK generado conserva el estilo del generador fijado, incluidas cuatro líneas nuevas con espacios finales en archivos ya existentes; `git diff --check` del código escrito a mano pasa. No se altera a mano el SDK para aparentar reproducibilidad.

La auditoría anterior de la aplicación publicada es independiente: [informe de navegador](../../../../../cuaderno-informes-20261009/INFORME_PRUEBAS_NAVEGADOR_20261010.md). Registra fallos observados y funcionalidades aún no probadas; no afirma cobertura exhaustiva.
