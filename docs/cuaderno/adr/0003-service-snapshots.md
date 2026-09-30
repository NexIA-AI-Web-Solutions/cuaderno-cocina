# ADR 0003 — Servicio nativo, snapshot y producción explícita

Estado: implementación en verificación, 2026-09-29. No aprobación de G3/G4 completos.

Se extiende MealPlan mediante ServicePlan; no calendario paralelo. La fecha civil es Europe/Madrid y los instantes se almacenan en UTC. Los comensales son enteros de 1 a 9999, límite compatible con el campo nativo MealPlan.servings. El hogar se fija al crear el servicio: cambiar la membresía del creador no cambia su origen ni autoriza consumir otro inventario. En datos heredados sin hogar histórico demostrable se conserva NULL; no se inventa propiedad a partir de la membresía actual.

Confirmar conserva necesidades, unidades, grafo y costes con versiones de precio, sin alterar existencias. Los costes desconocidos permanecen incompletos, nunca cero. El snapshot no publica una receta privada: lista, detalle y transiciones revalidan las ACL nativas de raíz y todos los nodos del grafo congelado. La supervisión admin no concede lectura de recetas privadas ajenas. Si se retira permiso después de confirmar, el snapshot se conserva pero deja de ser accesible a esa persona.

Producir es explícito e idempotente. En Profesional registra el estado; en Integral consume ingredientes del hogar fijado, con movimientos y saldo nativo en una transacción. La disponibilidad excluye lotes caducados antes de `max(fecha_servicio, fecha_actual_local)` y usa caducidad más próxima primero. Una ficha con necesidades incompletas o stock insuficiente se rechaza sin consumo parcial. Las subrecetas se expanden a ingredientes; este flujo no registra stock de producto terminado ni consume a la vez ingredientes y subelaboraciones.

Cada movimiento conserva el origen estructurado `service_plan/id/service_date` dentro de metadata_snapshot. El origen forma parte de la huella idempotente; los movimientos anteriores sin origen conservan su huella. Las compensaciones de compras y movimientos independientes conservan origen y referencia al original. La reversión genérica de movimientos de servicio está bloqueada desde413abf14e; falta la reversión completa atómica del servicio. No se declara valoración contable/FIFO de costes: FEFO solo elige lotes físicos.

Evidencia RED/GREEN y revisión independiente: `docs/cuaderno/evidence/2026-09-29-integrity-round.md`. Antes de cerrar el gate faltan la regresión completa, build del snapshot final y pruebas visuales.
