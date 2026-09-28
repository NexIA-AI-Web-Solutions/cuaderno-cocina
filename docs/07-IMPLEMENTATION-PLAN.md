# 07 · Plan ejecutable de principio a fin

La fuente estructurada de tareas es `tooling/work-packets.json`. El listado siguiente explica el orden y las puertas. No hay una autorización de despliegue/compra en estas tareas. Todos los cambios usan TDD, revisión y registro de evidencias.

## Fases

G0 verifica entorno y modelo. G1 construye cimientos. G2 deja Esencial funcional, con persistencia y transferencia de datos. G3 añade trabajo por servicio. G4 conecta almacén y compras. G5 endurece rendimiento/operación. G6 cierra con navegadores, auditoría y paquete de entrega.

El checkpoint de G2 es el primer producto utilizable, pero no elimina los controles operativos finales. Para ALL_TIERS continuar automáticamente tras G2. No volver a pedir aprobación para cada CRUD.

Las dependencias habilitan paralelismo limitado: dominio y shell visual pueden avanzar por archivos distintos; migrations y lockfile permanecen bajo control del líder. Pruebas y review son parte del paquete, no una fase opcional «para más adelante».

## T001 · G0 · Preflight, modelos, versiones y riesgos

**Depende de:** inicio. **Responsable sugerido:** leader.

Inventario de entorno, modelo efectivo, dependencias oficiales y SQLite parcheado. No fabricar resultados.

**Se acepta cuando:** artifacts/preflight.json; docs/DEPENDENCY_BASELINE.md

## T002 · G1 · Scaffold y herramientas de calidad

**Depende de:** T001. **Responsable sugerido:** leader.

SvelteKit estable, Node24, lockfile, TypeScript strict, ESLint/Prettier, Vitest/Playwright y CI mínima. No borrar el handoff.

**Se acepta cuando:** Instalación limpia; test semántico inicial; build y scripts multiplataforma.

## T003 · G1 · Tipos de dinero, unidades y parser español

**Depende de:** T002. **Responsable sugerido:** cuaderno_domain.

Contratos decimales, dimensiones, nulos/ceros, conversiones, round HALF_UP y overflow.

**Se acepta cuando:** Unitarias con oráculos fijos y propiedades; sin float monetario.

## T004 · G1 · Persistencia y migraciones core

**Depende de:** T002. **Responsable sugerido:** cuaderno_data_ops.

SQLite real, Drizzle, foreign keys, WAL, private dirs, esquema mínimo y migración desde vacío.

**Se acepta cuando:** Migraciones y restricciones pasan en Windows y Linux disponibles.

## T005 · G1 · Acceso privado, sesiones y setup propietario

**Depende de:** T004. **Responsable sugerido:** cuaderno_data_ops.

Better Auth oficial, sin registro público, recuperar acceso por operador, logout y sesión revocada.

**Se acepta cuando:** Auth integrada, límites de login y acceso anónimo rechazado.

## T006 · G1 · Sistema visual y shell responsive

**Depende de:** T002. **Responsable sugerido:** cuaderno_web.

Tokens, navegación, botones/inputs/combobox accesibles, estados y estructura móvil/iPad.

**Se acepta cuando:** Capturas sintéticas, teclado, foco y ausencia de overflow global.

## T007 · G1 · Capacidades y autorización servidor

**Depende de:** T005. **Responsable sugerido:** leader.

Resolver edición acumulativa y permisos; pruebas de URL directa, import y archivos.

**Se acepta cuando:** Esencial no puede ejecutar funciones de otros tiers por endpoint.

## T008 · G2 · Ingredientes y formatos de compra

**Depende de:** T003, T004, T005, T006, T007. **Responsable sugerido:** cuaderno_web.

CRUD, búsqueda, precio desconocido/gratis, archivado, version conflict y formato claro.

**Se acepta cuando:** Alta/editar/reabrir; actualizar precio sin perder referencias.

## T009 · G2 · Motor de escandallos y recálculo

**Depende de:** T008. **Responsable sugerido:** cuaderno_domain.

Servicio puro más consultas por lote; costes completos/parciales y ración, cambio de precio.

**Se acepta cuando:** Golden cases y coste observado desde DB, sin redondeo por línea.

## T010 · G2 · Recetas completas y escalado

**Depende de:** T009. **Responsable sugerido:** cuaderno_web.

Crear/editar/duplicar/archivar, cantidades, raciones, pasos básicos, simulación sin mutación.

**Se acepta cuando:** E2E vertical de ingrediente→receta→coste→persistencia.

## T011 · G2 · Fotos privadas optimizadas

**Depende de:** T010. **Responsable sugerido:** cuaderno_data_ops.

Subida segura, límites, variantes, EXIF fuera, almacenamiento atómico y acceso privado.

**Se acepta cuando:** MIME falso/imagen enorme/path inválido bloqueados, foto válida visible.

## T012 · G2 · Búsqueda, fichas impresas y responsive Esencial

**Depende de:** T011. **Responsable sugerido:** cuaderno_web.

Paginación/filtros, detalle y print A4; flujos táctiles y errores legibles.

**Se acepta cuando:** Receta de 30 líneas imprimible; móvil/tablet/escritorio funcionales.

## T013 · G2 · Import/export genérico y backup básico

**Depende de:** T010, T011. **Responsable sugerido:** cuaderno_data_ops.

JSON canónico, CSV validado, preview, idempotencia, export total y snapshot seguro con media.

**Se acepta cuando:** Roundtrip y restore aislado Esencial; no datos reales.

## T014 · G2 · Puerta de aceptación Esencial

**Depende de:** T012, T013. **Responsable sugerido:** cuaderno_qa.

Todos los escenarios básicos y permisos pasan; checkpoint funcional antes de ampliar.

**Se acepta cuando:** Revisión independiente y etiqueta interna ESSENTIAL_VERIFIED; no deploy comercial automático.

## T015 · G3 · Subrecetas y propagación por DAG

**Depende de:** T014. **Responsable sugerido:** cuaderno_domain.

Aristas, salida medible, costes transitivos, ciclos y profundidad, versiones y precio faltante.

**Se acepta cuando:** Rechaza A→B→A y propaga cambios correctos, sin N+1.

## T016 · G3 · Mermas, rendimientos y alérgenos declarados

**Depende de:** T015. **Responsable sugerido:** cuaderno_domain.

Separar merma de ingrediente y rendimiento de elaboración; registro manual sin certificación sanitaria.

**Se acepta cuando:** Ejemplo 80% una sola vez; agregación de alérgenos revisable.

## T017 · G3 · Menús, servicios y reservas internas

**Depende de:** T016. **Responsable sugerido:** cuaderno_web.

Semana/agenda, raciones por plato, comensales manuales O reservas, cancelación, capacidad y consolidación.

**Se acepta cuando:** No doble cómputo; DST y reservas canceladas; planificar no consume stock.

## T018 · G3 · Presupuestos y fichas de producción

**Depende de:** T017. **Responsable sugerido:** cuaderno_web.

Coste por servicio/persona, presupuesto sin venta, contribución opcional sobre base comparable y ficha avanzada.

**Se acepta cuando:** Sin falsa rentabilidad neta ni margen sobre precios incompletos.

## T019 · G3 · Puerta de aceptación Profesional

**Depende de:** T018. **Responsable sugerido:** cuaderno_qa.

E2E menú con subrecetas/merma/reservas y sus bloqueos por edición/rol.

**Se acepta cuando:** Revisión nueva; PRO_VERIFIED; Esencial sigue limpio y rápido.

## T020 · G4 · Proveedores y productos normalizados

**Depende de:** T019. **Responsable sugerido:** cuaderno_data_ops.

Fichas y referencias proveedor, formatos comparables, edición/archivado.

**Se acepta cuando:** Mismo ingrediente con varios proveedores sin inventar conversiones.

## T021 · G4 · Libro de movimientos y saldo de existencias

**Depende de:** T020. **Responsable sugerido:** cuaderno_domain.

Ledger inmutable, entrada/apertura/ajuste, saldo transaccional, versiones y anti-negativos.

**Se acepta cuando:** Carrera de consumo reproducida; no doble escritura ni saldo negativo.

## T022 · G4 · Compras y recepciones idempotentes

**Depende de:** T021. **Responsable sugerido:** cuaderno_data_ops.

Borrador/pedido/recepción parcial, líneas, precios, eventos y snapshot.

**Se acepta cuando:** Reintento de recepción no duplica stock; pedido sin recepción no incrementa saldo.

## T023 · G4 · Consumo por producción y desperdicios

**Depende de:** T022. **Responsable sugerido:** cuaderno_domain.

Confirmación explícita, explosión a ingredientes base, cantidades reales, motivos y compensaciones.

**Se acepta cuando:** Subrecetas no descuentan dos veces; desperdicio tiene coste y actor.

## T024 · G4 · Valoración ponderada y consistencia

**Depende de:** T023. **Responsable sugerido:** cuaderno_domain.

Media ponderada, salidas al coste vigente operativo, residuos a saldo cero y reconstrucción.

**Se acepta cuando:** Caso 20 kg/60 €→5 kg consumo→2 kg desperdicio=13 kg/39 €.

## T025 · G4 · Histórico e impacto de precios

**Depende de:** T022, T024. **Responsable sugerido:** cuaderno_web.

Historial de compras y eventos, cambio de coste actual de recetas; snapshots pasados intactos.

**Se acepta cuando:** Cambiar precio actual no reescribe compras ni producciones previas.

## T026 · G4 · Reposición, compra sugerida y equipo

**Depende de:** T025. **Responsable sugerido:** cuaderno_web.

Necesidad menos disponible, mínimos, redondeo de envase, permisos responsable/cocina/consulta.

**Se acepta cuando:** Propuestas explicadas; no pedidos enviados solos; API y media no filtran importes.

## T027 · G4 · Puerta de aceptación Integral

**Depende de:** T026. **Responsable sugerido:** cuaderno_qa.

Flujo completo servicio→necesidad→recepción→producción→pérdida→saldo/valor; regresión demás tiers.

**Se acepta cuando:** INTEGRAL_VERIFIED con revisión independiente y evidencias.

## T028 · G5 · Portabilidad completa y recuperación

**Depende de:** T027. **Responsable sugerido:** cuaderno_data_ops.

Extender formato export/import a todas las entidades, backup coherente y restore completo.

**Se acepta cuando:** Claves/refs/snapshots/media/stock restaurados en otro destino.

## T029 · G5 · Benchmark y reducción de recursos

**Depende de:** T028. **Responsable sugerido:** cuaderno_qa.

Seed grande fijo, p50/p95, RSS, disco/bundle/WAL, queries; mejorar cuellos encontrados.

**Se acepta cuando:** Informe reproducible sin atribuir a VPS lo medido solo en portátil.

## T030 · G5 · Instalación Windows y publicación Linux

**Depende de:** T029. **Responsable sugerido:** cuaderno_data_ops.

setup local seguro, servicio Linux/Caddy, persistencia fuera build, migraciones y rollback documentados.

**Se acepta cuando:** Checkout limpio→build→smoke; ningún servidor real modificado.

## T031 · G5 · Auditoría seguridad y dependencias

**Depende de:** T030. **Responsable sugerido:** cuaderno_reviewer.

Revisión independiente de auth, roles, edición, uploads, SQL, import y supply chain.

**Se acepta cuando:** Sin fallos críticos/altos aplicables abiertos; alertas justificadas.

## T032 · G6 · Revisión cross-browser y manuales

**Depende de:** T031. **Responsable sugerido:** cuaderno_qa.

Chromium/WebKit/Firefox, vistas, accesibilidad, manual usuario y lista iPad físico pendiente.

**Se acepta cuando:** Ninguna prueba no ejecutada declarada como PASS.

## T033 · G6 · Auditoría final sobre árbol integrado

**Depende de:** T032. **Responsable sugerido:** cuaderno_reviewer.

Comparar requerimientos con código y evidencias; rerun pedido al líder; comprobar recetas y ledger.

**Se acepta cuando:** Veredicto independiente y fixes revalidados.

## T034 · G6 · Release local y handoff final

**Depende de:** T033. **Responsable sugerido:** leader.

Empaquetar runtime/manifest, SHA256, guías y estado; resumir ejecutado y pendientes externos.

**Se acepta cuando:** LOCAL_VERIFIED y Linux real cuando probado; nunca inventar deploy/migración cliente.

## Entorno sin acceso externo

La ausencia de dominio/servidor, datos del programa antiguo o iPad físico no impide completar desarrollo local y pruebas sintéticas. Registrar lo pendiente por separado. Si falta un modelo, permisos de ejecución o una dependencia esencial no descargable, conservar checkpoint y precisar qué está bloqueado; no anunciar que las 34 tareas están terminadas.

## Entrega de cada puerta

Actualizar `docs/STATUS.md` con commit, comandos/exit, evidencia y revisor. Un README con capturas no sustituye funciones. El cliente tiene datos exportables y un flujo de recuperación, no solo una interfaz bonita.
