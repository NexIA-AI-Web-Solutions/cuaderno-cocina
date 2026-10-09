# ADR: controlador separado para recuperar G7 del candidato 4335e6e

Estado: preparado para revisión; no ejecutado ni admitido por este documento. Fecha: 9 de octubre de 2026.

El run original 37972458941 conserva su resultado: ocho jobs aprobados y un fallo de infraestructura en G7. Esta recuperación no cambia sus artefactos ni lo convierte en un run original de nueve jobs aprobados. El cierre, si se aprueba, será compuesto por los ocho resultados originales y un G7 nativo posterior, con procedencia explícita.

El workflow de esta rama se llama `Cuaderno G7Recovery433`, responde exclusivamente a push en `cuaderno/g7-recovery-20261009` y contiene solo `release-gate`. No incorpora workflow_dispatch, no ejecuta de nuevo las matrices de aplicación y pide únicamente contents:read y actions:read. El commit controlador es distinto del commit runtime.

Se hace checkout separado del controlador y checkout limpio de la fuente runtime fijada a `4335e6e9b858581c724e154c799c095cddb88383`, SHA `111e3b15e098839437c8e64a67bb3a9b34a04863f946ca344a7e7a853c377f05`. Del run original 37972458941 se descargan `cuaderno-candidate-image` y `cuaderno-e2e-records-root`. Se conserva `ci-context.json` sin regenerarlo ni modificarlo; se comprueban fuente, imagen y SHA del contexto antes y después del gate.

El baseline anterior procede de la V12 oficialmente aceptada: run37905852791, artifact11605008153, commit643e37ada841b182890daf77790e3e21768d5952 y SHA9205105e02bccdb45ff5cc6048720e2a293532b660db2c3ee46e52394f52623b. Su imagen se carga con la comprobación nativa de archivo/imagen y su backup se crea en el worktree explícito de esa misma fuente. Sustituye la referencia histórica inaccesible del workflow original; no publica un baseline nuevo ni cambia producción.

Las restantes órdenes de preparación, `ci_release_gate.py`, los diecisiete controles nativos y el roundtrip productivo aislado permanecen como en fuente4335e6e. El controlador no añade filtros, omisiones o una variante del gate. La prueba de procedencia se escribe en RUNNER_TEMP, fuera del checkout runtime; se copia a un staging de artefactos también fuera de la fuente runtime y se sube con el mismo nombre `cuaderno-release-gate-evidence`. Ese staging conserva exactamente las rutas nativas `.cuaderno-runs/` y `data/cuaderno/`, sin prefijos de checkout ni ruta RUNNER_TEMP dentro del artefacto. Se registran commit/run del controlador, fuente runtime, runs/artifact de entrada y SHA del contexto.

El entorno usa secretos sintéticos enmascarados y recursos CI aislados. No usa cuentas productivas ni modifica timers, producción o informes owner. El cierre del preview conserva la orden original. Antes de push, ROOT debe revisar el diff y commit controlador. Tras ejecución, el verificador compuesto debe comprobar el resultado original y este run separado, la prueba de procedencia y los 17 registros nativos del mismo candidate_id/contexto. Un workflow válido localmente no demuestra que G7 haya pasado.

## Seguimiento de mantenimiento de CI, separado del cierre actual

La descarga del pin anterior `37451427468` no está disponible para el job original. Esto no prueba que expirase: pueden existir otras causas de ausencia o acceso. Se conserva el fallo de infraestructura y no se añade un campo `expiry_proven` ni se declara nueve de nueve jobs originales aprobados.

La decisión actual es ejecutar un commit controlador separado, con fuente4335e6e congelada. **No se fusiona ahora esta rama controladora a `cuaderno/main`**: su workflow contiene deliberadamente solo G7 y su trigger exclusivo. La admisión de la versión y el mantenimiento posterior del pipeline general son decisiones distintas de ROOT.

Propuesta mínima pendiente de revisión para un checkout de mantenimiento de `cuaderno/main`, después del cierre autorizado: mantener el workflow completo y aplicar conjuntamente estos tres cambios a `.github/workflows/cuaderno.yml`. No son cambios aplicados por este ADR.

```diff
 # candidate-image: upload cuaderno-candidate-image (solo este artefacto)
-          retention-days: 3
+          retention-days: 90

 # release-gate: descarga de la imagen anterior aceptada
           name: cuaderno-candidate-image
-          run-id: 37451427468
+          run-id: 37905852791
           github-token: ${{ secrets.GITHUB_TOKEN }}
           path: .cuaderno-runs/prior-image

 # release-gate: fuente del backup anterior, en el mismo cambio
-          git worktree add --detach .cuaderno-runs/prior-source f2e3f3ca6da66848fd1234c6189a342184316d52
+          git worktree add --detach .cuaderno-runs/prior-source 643e37ada841b182890daf77790e3e21768d5952
```

El pin run/commit debe cambiar de forma inseparable: el baseline aceptado es V12, run37905852791, artifact11605008153 y fuente643e37ada841b182890daf77790e3e21768d5952. Antes de aplicar el mantenimiento se volverán a comprobar la disponibilidad del artefacto, su identidad/archivo/imagen y la política máxima de retención del repositorio. Si deja de estar disponible, se detiene la propuesta y ROOT decide un baseline verificable; no se elige «latest» ni una fuente sin aceptación.

Los 90 días solo afectan artefactos candidatos subidos en ejecuciones futuras; no recuperan un archivo ausente ni amplían retrospectivamente la retención de V12. No proporcionan permanencia. Un mecanismo duradero de publicación del baseline requerirá otra decisión y no se añade aquí: no hay publisher, permisos de escritura ni credenciales nuevas. El mantenimiento conserva todos los jobs, tests, collector y diecisiete controles, sin skips ni regeneración de contextos; se validará su diff y YAML y requerirá su propia CI. Esta propuesta documental no cambia el runtime ni constituye evidencia de G7 aprobado.

## Primer intento conservado y corrección de checksum previo

El controlador `87eb36138bf5ab6a9455c47cf5810a7974e977b1`, run37982670172, falló antes de ejecutar los controles nativos G7. El descriptor V12 contiene exactamente una línea SHA256 con el nombre `.cuaderno-runs/candidate-image.tar.gz`; el paso había cambiado de directorio a `.cuaderno-runs/prior-image`, donde el archivo descargado se llama `candidate-image.tar.gz`. `sha256sum -c` resolvía la ruta relativa del descriptor desde ese directorio y buscaba un archivo inexistente. El fallo no demuestra corrupción del tar ni expiración del artefacto y se conserva sin reclasificarlo.

La corrección limita la modificación operativa a ese checksum previo: Python exige una sola línea con 64 hexadecimales minúsculas, dos espacios y el nombre exacto `.cuaderno-runs/candidate-image.tar.gz`, y calcula SHA256 por streaming del archivo real `candidate-image.tar.gz` en el directorio de descarga. Compara los hashes sin editar el descriptor ni el tar. La posterior orden `verify_loaded_image.py`, sus argumentos y el resto de controles nativos permanecen idénticos. Un formato distinto o un hash incorrecto abortan antes de `docker load`.

El ZIP V12 retenido permite reproducir la discrepancia de ruta y verificar el hash del tar mediante su stream ZIP, sin extraer ni modificar el archivo. La comprobación local del checksum no acredita G7. El segundo intento requiere commit/push de ROOT en la misma rama exclusiva y queda pendiente de su resultado real. El run37982670172 y sus recibos fallidos se conservan; cualquier binding compuesto posterior debe identificar explícitamente el nuevo run aprobado.
