# 12 · Definición de terminado y evidencia

## No basta con que arranque

- [ ] T001–T034 implementadas, integradas y verificadas conforme al alcance ALL_TIERS.
- [ ] Esencial utilizable de manera independiente con todas sus funciones reales.
- [ ] Profesional e Integral no exponen capacidades por URL cuando están desactivadas.
- [ ] Sin placeholders funcionales, TODOs bloqueantes, datos en memoria sustituyendo persistencia o mocks en flujos productivos.
- [ ] Datos sintéticos y app en español, sin atribuir datos de muestra al cliente.
- [ ] Precisión decimal, unidades, desconocidos, mermas, DAG, stock e idempotencia probados.
- [ ] Login/logout/recuperación, archivos privados, límites y permisos probados.
- [ ] Formato, lint, tipos, unitarias, integración, cobertura, build y E2E reales en verde.
- [ ] Pruebas Chromium/WebKit/Firefox y matrices de edición/rol/viewport.
- [ ] Benchmark con entorno/commit/dataset identificados, no cifras inventadas.
- [ ] Backup/restore en destino aislado con datos y media.
- [ ] Revisiones independientes sin hallazgos críticos/altos abiertos aplicables.
- [ ] Manual de usuario, guía de instalación y runbook de recuperación en español.
- [ ] Lockfile, procedencia/licencias, versiones y script de setup reproducibles.
- [ ] Release local con manifiesto y SHA-256, sin datos privados ni dependencias de desarrollo.

## Entregables de cierre

`docs/USER_GUIDE_ES.md`, `docs/INSTALL_WINDOWS_ES.md`, `docs/INSTALL_LINUX_ES.md`, `docs/OPERATIONS_ES.md`, `docs/RELEASE_REPORT.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/THIRD_PARTY_NOTICES.md` y evidencia sintética en `artifacts/release/<id>/`.

El reporte incluye comandos, códigos de salida, fecha, commit, modelos efectivos cuando se puedan verificar, versión Node/SQLite y casos de aceptación. No incluir secretos ni transcripciones privadas de razonamiento.

## Estados que deben distinguirse

- `LOCAL_VERIFIED`: pruebas locales y aplicación funcional demostradas.
- `LINUX_VERIFIED`: build/arranque/smoke y persistencia verificados en Linux/CI, no inferidos desde Windows.
- `IPAD_REAL_NOT_RUN`: WebKit pasó, pero todavía no se probó un iPad físico. Es una validación de campo pendiente explícita.
- `CLIENT_MIGRATION_PENDING`: importador genérico probado; origen y datos reales sin acceso.
- `PRODUCTION_DEPLOYMENT_PENDING`: runbook listo, no desplegado sin autorización.
- `OFFSITE_BACKUP_PENDING`: restore local aprobado, destino externo no configurado.

No se considera verificación técnica integral si falla Linux o un navegador requerido; corregir o declarar el bloqueo. Los pendientes externos anteriores no exigen inventar credenciales para completar el producto local.

## Prueba funcional de aceptación en cinco minutos

Propietario entra → crea ingrediente aceite 5 L/32 € → crea receta con 200 ml y 4 raciones → comprueba 1,28 €/0,32 € → cambia aceite a 40 € → comprueba 1,60 €/0,40 € → escala a 10 raciones y ve 500 ml sin modificar base → imprime → cierra/reabre sesión → vuelve a encontrar receta → exporta → restaura prueba aislada.

G3 y G4 añaden escenarios de producción y stock de `examples/contracts/golden-cases.json`. No usar la duración «cinco minutos» como promesa de tiempo de ejecución a clientes; es una sesión de demostración diseñada para ser breve.
