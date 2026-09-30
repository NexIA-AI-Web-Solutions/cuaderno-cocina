# Revisión independiente acotada

Agente real `integrity_review_sol`, spawn aceptado explícitamente `gpt-6.1-sol`, contexto inicial independiente, sin escritura. Instrucción actual: solo GPT-6 Luna/GPT-6.1 Sol para agentes. No atribuye el modelo de la sesión líder ni aprueba G7.

Rectificación posterior: los PASS históricos de typecheck citados abajo fueron vacuos. La revisión vigente usa `vue-tsc --noEmit -p tsconfig.app.json`: pin 650/checkout 626, RED global; ninguna mención anterior a typecheck constituye aceptación actual.

Bloques aprobados estáticamente y evidencias de ejecución aportadas:

- Servicios: `service_plans.py`, secciones ServicePlan/ProductionSheet de operations, migraciones 0010/0011. Fecha civil, snapshot, Household congelado, ACL privada dinámica, FEFO y producción sin doble consumo. 17 tests incluidos en integración anterior 76/76 y posterior 86/86.
- Precisión: serializer nativo delta localcontext64 y digest canonical_decimal; ledger límites 32,16 y huella sin normalize. RED c57c6c2c → GREEN 4b94aa29, 2/2.
- PWA: service-worker.ts + test, autenticados NetworkOnly, no replay, purga legado y fallback constante. 4/4 GREEN 290da336; typecheck/build. Navegador/IndexedDB real pendiente.
- Compras: purchasing.py API/servicios, legacy adapter y guard ledger, modelos/0012/0013. GET receipts limitado/ACL; solo reversión documental cambia saldo del pedido; oferta gratis equivale exactamente a cero. RED GET/legacy 20098945, RED bypass e50ffb16, RED constraint 0237238e → compras GREEN f548b639 7/7.
- UI compras: PurchasingPanel/Almacen. Clave incluye pedido y payload, reutilización tras A→B→A hasta éxito, precio desconocido distinto de cero, errores por pedido y vacío no afirmado ante fallo. RED 0a637dd6 → GREEN 735a448a, 1/1; typecheck 0e8496b8.

El revisor informó inicialmente un orden de locks inverso en reverse_receipt. Al releer líneas 292–302 retiró expresamente ese hallazgo: Space ya se bloqueaba primero. No se cambió código para corregir un defecto inexistente; se preserva la rectificación.

Integración ampliada `20260929T215448Z-integration-e975abb8.json`: 86/86, 96.954 s, PostgreSQL real, nuevos pines Python instalados. Dominio `20260929T215315Z-unit-44ad3c58.json`: 27/27. Lint `20260929T215520Z-format-c8bbc07a.json`: exit 0. Estas aprobaciones no cubren automáticamente dependencias transitivas del nuevo build ni tareas visuales, performance, rollback completo, margen/mermas/impacto pendientes.

Build limpio actualizado, restore final y revisión global siguen abiertos. La existencia de evidence/review_evidence en tasks.json significa trazabilidad parcial; no DONE ni aceptación de todos los requisitos de la tarea.
