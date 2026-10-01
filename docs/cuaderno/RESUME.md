# Checkpoint de cierre — 30 de septiembre de 2026

**Actualización del 1 de octubre:** por petición del propietario, las 13 carpetas de `data/cuaderno/backups` están ahora en la Papelera, no en el checkout. La base activa y los destinos de restore/rollback permanecen intactos. Recuperar la copia o generar y validar otra antes de repetir los comandos `rollback`/`rollback-current` fijados a bundles históricos; actualizar sus rutas solo después de comprobar el nuevo bundle. La caché Docker retirada liberó 14,39 MB; se conservó la caché compartida o sin atribución segura. Preview `ready=true` después de la limpieza.

Tanda cerrándose a petición del propietario, con push GitHub autorizado; no ampliación a VPS o datos reales. Base de los cambios de documentación: `a447e1db1`; consultar `git rev-parse HEAD` para el commit final posterior. Primer push confirmó origin/cuaderno/main=cfffdd338, sin force/PR. Último push debe comprobarse con `git ls-remote --heads origin cuaderno/main`. Solo agentes hijos GPT‑6.1 Sol, sin recursión.

## Preview y comprobaciones

http://127.0.0.1:18081 — imagen `sha256:a3c426362270c835ed795741ff92c205c62cf40d53ac6c6905dc69d728a8598c`.
Fuente `f191c6b29c5afb2e1b251b8ae446d4fa19205b64+worktree.e8999bc1868565229f2129adfa77543cdaa4b4b6262396bc04652f551d4a53fb`.
Build205924Z PASS1321.767s, Pythonstage reconstruido153constraints, frontendCACHEed4. Runtime lock153PASS211202Z/pipcheck211213Z/JIToff211224Z/PyJWT4PASS211029Z. Food/Package/JIT ya empacados. NodePython nativo24.19 presente, no frontendNode_modules/Git/tests.

DEMO SOLO locales: demo-esencial/demo-profesional/demo-integral, `Demo-Cocina-2026!`. HTTP serial del a3c:212029genérico/212155precios/212324lecturas/212448preparación/212611reversión/212733waste PASS. Los dos últimos son replays de históricos, no nueva producción/WASTE.6servicios/Integralaceite5L; preparación deja4auditorías adicionales.

Backup `data/cuaderno/backups/20260930T212850Z-32d8a6a3`; restore213552Z PASS114tablas/949filas/110secuencias/3media, DB `cuaderno_restore_b4a9a4ce523b4e69af1700a26efb6d6c`. DumpSHA dcf40880166589e9948fe7b15aa3bf423d8e4c64bec98815ed8b6a517ef57b7a; fingerprint07c232c3544bf4d91b86fef9ab182feebbcb332867d6e58d7518112ed6eb1315.
Rollback por runner `214236Z-rollback-current-6c30d463` PASS107.430s, DB `cuaderno_restore_rollback_db56b593d8b7`, reporte `data/cuaderno/rollbacks/rollback-db56b593d8b7/rollback-result.json`, imagen/fingerprint idénticos y destinos nuevos. Ensayo directo anterior115.782s también retenido. Terminal7468 terminó; no quedan procesos de esta tanda activos. No activaciónpreview/downgrade vivo.

## Código y evidencias posteriores

- Scanner7106 fullGit40 y cfff DBstatusschema real, ROOTunit11GREEN211252/reviewfresh. Scan210844 FAILpreflight corregido;211543 FAILWindowslayerscolon. Conservar `data/cuaderno/scans/ccb83f86-f85e-48b1-9758-75826e9168d2/image.tar` (269268480bytes), grype.json vacío NOresultadoOS.
- LinuxGrype0.119 preparado, no ejecutado: archiveSHA3fa2dc4b924621ab65404cf08d0b8438d896d80ab949c9d5a4ca283c36004c9b; binarioSHAe02ba25615668c6bae03473e3c6493b6dfffc2e4e419f65f9bd62555ac10cd0e, en `data/cuaderno/tooling/grype-linux-0.119.0`. DBoffline fijada04d141a2… y exeWindows5fa9104f… no cambiaron. Siguiente scan debe correr aislado enLinux, sin socketDocker/red ni tocar DBdemo; preservar findings, fuenteImageID/archivo exactos y pins.
- JS tooling a447 preparado: frontend_build_provenance.mjs + índice reutilizado. TDD10/2FAIL→GREEN10, reviewerP1outDirjunction/P2catchvacuos→RED212417/10PASS1FAIL→ROOT11GREEN212643. Freshreviewaprueba. **NO wiringVite/Docker/build real ni closure npm exacta**. Root integra configuración compartida cuando se retome; no afirmar postWorkbox real por fixture.
- Guia `PRODUCCION_ES.md` y READMEindex actualizados. Composeejemplo `214015Z-production-doc-config-43a4ed15` PASSconfig--quiet, solo sintaxis; settingsSecurebind/proxy/TLS/VPS no ejecutados. Caddytemplate54525952bytes alinea52MiBnginx (preserva50MiB+multipart), validar Caddy real antes de usar.

## Trabajo que falta para G7

1. No relanzar build por rutina al retomar: inspeccionar primero source/digest. Si se cambia pipeline, congelar HEAD+todos archivos hasta terminar; source_manifest incluye docs/registry. El próximo frontendstage se invalidará por cambios del inventario.
2. EscaneoLinux real y tratamiento de todos los avisos. AuditPython211047 exit1 SOLOOAuthlibversión, backport53f308e8reobservado. SBOMPython153211058/453frontend211115 validan esquema, no findings/OS/cierreJS.
3. Upgrade desde pin al artefacto final (`migrations` crea nuevosdestinos); integración ampliada y nativo bajo153versiones de producción. G0 contiene dependencias extra y3transitivos anteriores: no fingir mismo conjunto.
4. Rendimiento203010 RED5: cost303.960/15SQL; servicios226.423seq/1026.090conc; movements213.380seq/1398.686conc; packages530.232seq/2158.155conc. Presupuestos300/500, dataset3000recetas/45kingredientes/1500Foods-formatos/100kmovimientos/10usuarios intactos. Sin subir budgets/retirar outliers. Perfil singleCPU no demuestra causalidad concurrente; ExistsGroup enScopeMiddleware fue propuesta READONLY, no implementada.
5. Wiring/provenienciafrontend+build real, navegador autorizado (B04no binding, sin bypassCDP), impresión/capturas/responsive y revisión final. Typecheck626RED/baseline650, no nuevo PASS vacuo.
6. Mantener STATUS/checklist/tasks y hechos del artefacto. No declarar iPad físico, migracióncliente, SMTP o VPS.

## Comandos locales

```powershell
git status --short
git rev-parse HEAD
$env:CUADERNO_ENV='local'
$env:CUADERNO_DEMO_PASSWORD='Demo-Cocina-2026!'
$env:CUADERNO_BACKUP_TARGET='release'
# Los /tmp no sobreviven a recrear el contenedor:
docker cp scripts/cuaderno/restore_smoke.py cuaderno-release-web:/tmp/cuaderno_restore_smoke.py
docker cp scripts/cuaderno/audit_dependencies.py cuaderno-release-web:/tmp/cuaderno_audit_dependencies.py
docker cp scripts/cuaderno/python_lock.py cuaderno-release-web:/tmp/cuaderno_python_lock.py
docker cp scripts/cuaderno/test_pyjwt_security.py cuaderno-release-web:/tmp/cuaderno_test_pyjwt_security.py
python scripts/cuaderno/check.py runtime-python-lock
python scripts/cuaderno/check.py runtime-pip-check
python scripts/cuaderno/check.py runtime-db-profile
python scripts/cuaderno/check.py runtime-audit
python scripts/cuaderno/check.py restore --allow-isolated-mutations
python scripts/cuaderno/check.py rollback-current --allow-isolated-mutations
python scripts/cuaderno/check.py migrations --allow-isolated-mutations
```

Serializar procesos pesados y dejar >61s entre smokes por allauth5logins/min/IP. Registry argvnull/verifiedfalse para checks no configurados sigue siendo pendiente, no éxito. Los reportes raw/datos y secretos de data/.cuaderno-runs son locales ignorados; GitHub recibe código y evidencia resumida, no copias/recetas/credenciales reales.
