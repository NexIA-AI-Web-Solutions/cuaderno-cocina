# Release de producción del 8 de octubre de 2026

**Admitida a las 06:06 UTC**, en
[Cuaderno Cocina](https://gex-dashboard.hopto.org/cuaderno-cocina/).
El recibo privado `c79b2ce-final-production-admission.json` (`0600`) declara
`passed=true` y `production_admitted=true`, SHA256
`c02d51990cc3fbc7df416d1ba1493b892402cb8927148376c6a6ea8d6a582452`.
Los pins públicos anteriores conservan `admitted=false`; la admisión final
separada es la atestación vigente. Ver [checklist completa](RELEASE_CHECKLIST.md).

## Identidad del runtime y alcance

Fuente congelada `source-release-20261008-v5`, commit
`c79b2ce54c20f778524e3dcadfac0bc7e8053aa0`, source SHA256
`1fb585ca77a057eda83900d8e7ea07ab13076f4a3d51cac59598753d3179fc5d`.
Imagen `sha256:88bf041a552f273f46e3856bb02dfc663397ebf113fbe05ba579446245f255a9`.
Web `18234e76f0b413d9dd1b90ee221dfce3f625e3bcc35593fd0b7d3d934cccfc5e`, healthy
observada desde las 04:58 UTC; DB conservada
`c92233bdb17fb5f302de9681fb2955d1e8c156cfadea58e3a6aaf8cbfb1c7c51`.
La rama de notas es separada; estos documentos no modifican fuente o imagen.

La sustitución propia `cuaderno-prod` cambió únicamente `CUADERNO_IMAGE` del
env protegido y recreó web con Compose `--no-deps --force-recreate --no-build
--pull never --wait --wait-timeout 600`, sin prestop separado ni recreación de
DB/media-init, puertos nuevos o cambios de Caddy. Env/wrapper/unit OLD quedan
retenidos en copias protegidas. La continuación post-health separada PASS,
`c79b2ce-post-health-continuation.json`, instaló wrapper NEW SHA
`c250e917e3adb9b0e14037469880cc6ca17dddd47fa522f22e24de0bf2eeda90` y unit NEW SHA
`1b9ce89fdab93aec56cfab84d829eafdd415c315f437505e2d78c35d671f6cb4`, vinculados a
source-v5. El helper original conserva su FAIL; no se reetiquetó.

## Validación completada

- [CI 37713643936](https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina/actions/runs/37713643936):
  nueve jobs PASS; backend Cuaderno 609 y nativo 1.296, frontend 342,
  Playwright raíz 599 y prefijo 715 en tres motores. G7 offline 17/17 y
  atestación cargada de nueve artefactos/1.081 archivos runtime y frontend PASS.
- Clon crítico v2: 12 informes PASS, nueve cuentas por edición/rol y tres
  intercambios entre Spaces; 72 PNG con dimensiones/hashes y modo `0600`
  comprobados. Revisión visual independiente de ocho capturas, cuatro anchuras
  × escritor/Consulta; no de las 72.
- Producción HTTPS 54/54 PASS: READ 36, WORKER 9, LOGIN/LOGOUT 9;
  tres fases exit0 y nueve logouts por fase. READ cubre 390×844, 768×1024,
  1024×768 y 1440×900; worker/login se ejecutan a 1440 px. Doce diagnósticos
  403 esperados vinculados a informes, tres fases/pins y prueba privada;
  ningún cambio de fuente, collector o informes para la aceptación.
- Cleanup PASS: nueve usuarios, tres Spaces y 27 sesiones propias eliminados;
  502 filas externas exactamente conservadas. Primarios/memberships/preferencias
  conservados; `primary_session_count=0` no prueba una sesión primaria positiva.
  `c79b2ce-synthetic-cleanup.json`, SHA256
  `3181724c39d31729d5fab464c089cece95eb964a4b84f64af483b23014ed7f1c`.
- Backup NEW limpio `20261008T055520Z-bab104011f10`: 123 tablas/330 migraciones,
  imagen/source exactos, cuatro miembros regulares descifrados y runtime healthy
  revalidado. `c79b2ce-new-backup-operation.json` y proof privado PASS.
- Restore NEW `cuaderno-restore-e320c008a6a3` PASS: 123 tablas/330 migraciones,
  119 secuencias y filas completas; cero archivos de media, assets/manifest
  nativos bajo prefijo y página login/CSRF verificados. Red interna, cero puertos
  publicados y recursos detenidos. Recibo SHA256
  `71460114f908515e07b304029d5daf6427a2e0cdaf80ab531d89c6c84f6e22bd`.
- Comparación final protegida PASS: contenedores conservados, redes, volúmenes,
  Caddy/boot y demás estados raw nativos coinciden. Sólo el restore propio añade
  dos contenedores, una red y dos volúmenes. Seis transiciones ambientales
  atribuidas, estados actuales y quince huellas de configuración exactos;
  no se afirma uptime ajeno inalterado ni inmutabilidad agregada de servicios.
- Host final PASS: 19 contenedores ajenos/cinco comprobaciones de Caddy;
  raíz HTTP200/33 ms y ready HTTP200/96 ms. Kernel 04:50–06:03:44 UTC:
  52 registros, cero relacionados con OOM; histórico OOM conservado.

## Backup periódico y persistencia

`c79b2ce-final-backup-timer-resumed.json` PASS: timer propio `active/waiting`,
con `enabled` conservado. Próximo backup viernes 9 de octubre a las
03:21:23 CEST; calendario diario 01:20 UTC (03:20 CEST en esta fecha), con jitter. Web y DB propias tienen
restart policy `unless-stopped`; Docker está activo/habilitado. El reboot
existente sigue programado para el 8 de octubre a las 08:30 CEST, sin cambios.
La observación acredita configuración de persistencia, no un ensayo posterior
al reboot futuro. Backups cifrados y bundles plaintext están protegidos en este
VPS; no hay offsite. No publicar ni imprimir los env protegidos con secretos.

## Cronología y fallos retenidos

Primer deploy 04:22:46 UTC: FAIL de preflight sin mutación, OLD healthy/env
idéntico. Seis lecturas demostraron mounts ajenos idénticos con orden variable;
canonicalización completa revisada conserva campos y duplicados. Evidencias
`c79-deploy-da2a09fba62f/result.json` y
`c79b2ce-deploy-preflight-mount-order-diagnostic.json`.

Quinto helper `c79-deploy-6768850b2bb3/result.json`: FAIL tras health y antes de
backup rebind. Cuatro bots nativos ciclaron por su configuración de seis horas
04:56:56–04:57:02; trece hashes históricos coinciden. Primera continuación
bloqueada antes de escribir por PHP automático 05:00:11 y activaciones
Polkit/DBus/PackageKit con configuración conservada. Se retienen
`c79b2ce-native-four-service-runtime-cycle.json` y
`c79b2ce-ambient-package-service-transitions.json`. Continuación PASS posterior
con recibo separado; no convierte los FAIL originales en PASS.

Cleanup original bloqueado antes de mutar por exigir diagnósticos vacíos;
`c79b2ce-cleanup-original-guard-block.json` y log `0600` conservados. Los doce
403 son GET del mismo origen de cuentas 2/6/7/8 para edition/unit/recipe-flat.
Reproducción instrumentada con plantilla original intacta: un caso nativo PASS
de la cuenta índice 6, con cuatro checks. Tres GET empezaron tras logout302 y
sin cookie a
+294/+596/+603 ms, prueba `c79b2ce-public-logout-diagnostic.json`. Esos tiempos
no se atribuyen a los doce diagnósticos originales. Adaptador privado revisado
`0d2e505b…`, 26 contratos PASS y revisión independiente: exige incondicionalmente
54 hashes de informes, tres fases/pins, prueba estática y esos doce diagnósticos
exactos con logout completado. La ejecución real posterior tiene recibo propio.

La unidad READ propia se aumentó preventivamente 1→1,5 GiB, sin OOM en esa
ejecución, sin reinicio ni retries ni cambios de límites productivos:
`c79b2ce-public-read-memory-adjustment.json`. Clon crítico v1 interrumpido,
verificación prematura del backup y primer restore OLD fallido se conservan.
El export SQL PostgreSQL16 sin `--file -` fue corregido y revisado; restore OLD
v2 real PASS de su punto 114/329/110. Los backups OLD posteriores y sus restore
reales quedan retenidos. No representan el backup NEW final ni borran el
historial; ver la [checklist](RELEASE_CHECKLIST.md).

## Límites y recuperación

Fingerprint DDL del esquema **no comparado**; backup offsite **no configurado**.
Media final vacía: no se acredita un restore de fotos reales. Cuaderno no tiene
SMTP configurado; IA y conectores externos desactivados; entrega SMTP no probada.
Navegador público Chromium con cuatro viewports emulados; CI en tres motores,
sin certificación de Safari/iPad físicos. Collector público conserva exclusión
preexistente de `ERR_ABORTED`, errores console/pageerror y HTTP ≥500 bloqueantes,
y 4xx diagnósticos; CI/clon crítico conservan todos los requestfailed. No se
declaran cero 4xx ni cobertura universal sin exclusiones. Scanner: ocho findings
raw, cero ignorados, revisión sin pendientes sin resolver; no cero vulnerabilidades.

Imagen/source OLD, backups y copias protegidas quedan retenidos para recuperación.
La imagen NEW puede aplicar migraciones: volver a OLD no deshace la DB.
No existe rollback automático, downgrade ni importación de dump en producción.
Ante un incidente, preservar fase/runtime y decidir el procedimiento de
recuperación para ese estado real. Restore OLD prueba su backup, no compatibilidad
con el esquema NEW migrado. Ver [seguridad](08-SECURITY.md) y
[operación](VPS_RUNBOOK_ES.md).
