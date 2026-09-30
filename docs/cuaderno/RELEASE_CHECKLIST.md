# Aceptación final

Snapshot local del 2026-09-30: imagen efectiva `59172af037da`, build `063934Z-local-up-97392261`, cookbook0243/cuaderno0016. Source ref y digest completos en STATUS. G7 abierto: no es el artefacto final del scope. Las casillas compuestas quedan abiertas si falta cualquier parte.

- [x] Base del SHA fijado, historia y avisos preservados.
- [ ] UI Tandoor preservada y módulos visuales verificados en navegador.
- [x] Sin runtime de Mealie/KitchenOwl/Grocy.
- [ ] Flujo Esencial500/17 completo, sin stock obligatorio, incluido recorrido visual.
- [ ] Profesional1000/20 e Integral1500/30 completos.
- [ ] Dominio, PostgreSQL real, regresión nativa vigente y navegadores pasan.
- [ ] Matriz completa de privacidad/Spaces/export/media/roles verificada.
- [ ] Ningún API/producto mock en entrega; montaje SFC unitario no equivale a E2E.
- [ ] Concurrentes/retries de todos los escritores no duplican movimientos.
- [ ] Build del artefacto final y migración desde baseline pasan. Candidato591: build PASS; `070137Z-migrations-c39da16a` PASS hasta0016, con conservación de datos nativos y checklist real. No baseline socketHTTP/browser.
- [ ] Backup/restore del artefacto final y rollback comprobados. Candidato591: `065043Z-restore-84bdbe5b` PASS,114 tablas/931 filas/110 secuencias/3 media; dos ítems reales de preparación y par desperdicio/reversión. Rollback completo pendiente.
- [ ] Precios comerciales/ediciones y traducciones completos y revisados.
- [ ] SBOM empacado, licencias/procedencia y patches completos. Estructura CycloneDX validada:453 componentes frontend stageLinux preservado en591,451 host y153 Python runtime; no equivale al cierreJS empacado ni a escaneo OS.
- [ ] Performance/storage cumplen presupuestos. Benchmark concurrente RED3 conservado.
- [ ] Comandos exactos de arranque y tests finales reproducidos.
- [ ] Revisión independiente final aprobada con evidencia.
- [x] Alcances externos identificados y separados de la aceptación local; no se ejecutaron iPad físico, migración de cliente ni despliegue VPS.

Resultados del candidato: integración250/250 PASS; permisos17/17 PASS; preparación17 y helpersUI10/SFCvirtual3 PASS; causaAPI13/helpers7/SFC3 PASS. HTTP desperdicio PASS sobre591; preparación/precios históricos PASS sobre c07. Typecheck efectivo RED626, cero Cuaderno/service-worker; lint Cuaderno exit0. Regresión nativa050917Z exit124timeout1200 pese a salida1279passed en1243.57s; nuevo perfil18606 en curso, no se presenta como PASS. Runtime audit070438Z exit1 sobre591 por aviso OAuthlib conservado por versión pese al backport exacto; sin consultas PyPI irresueltas; SBOM153 validado070555Z.

Faltan valoración/desperdicio vinculado, matriz operativa de roles, batching/rendimiento, intercambio completo, rollback, cierre exactoJS/escaneo OS, capturas y firma G7. El SBOM del stage453 sí está empacado en591, no es el cierreJS. B04 impide navegador autorizado; no certificación física iPad. Export antiguo bloquea solo su extractor.

No marcar por intención. Adjuntar commit, entorno, comandos, exit codes y revisión. Evidencia: [continuación](evidence/2026-09-30-continuacion.md), [estado](STATUS.md), [reanudación](RESUME.md) y [procedencia](SBOM_PROVENANCE.md).
