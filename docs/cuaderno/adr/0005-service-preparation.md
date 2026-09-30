# Preparación por servicio desde pasos nativos

Estado: implementado y revisado por bloques; build/upgrade/restore0016 comprobados en591 y HTTP preparación histórico en c07. Gate final y comprobación visual pendientes.

Tandoor conserva instrucciones canónicas en Recipe.steps/Step. Ingredient.checked es estado de cliente, ShoppingListEntry.checked pertenece a compras, CookLog no representa tareas de servicio. Las referencias fijadas tampoco ofrecen un equivalente persistido sobre ServicePlan. No se portan carpetas ni un segundo editor/calendario.

ServicePreparationItem guarda una copia de los pasos al confirmar por primera vez el servicio, en la misma transacción que su snapshot. Orden raíz primero y después subrecetas del grafo congelado; pasos por order/PK. Una tarea por pareja Recipe/Step, aunque el mismo preparado aparezca repetido en el grafo. No escala ni repite instrucciones según comensales. El FK de origen puede quedar nulo si se elimina Step; el texto congelado permanece. Marcar una tarea no modifica receta, coste, snapshot ni stock.

Servicios confirmados antes de0016 permanecen sin checklist: sus snapshots no contenían las instrucciones históricas. Ni GET ni reconfirmar inventan un backfill desde recetas actuales. Un checklist vacío se presenta como solo lectura.

PUT requiere revisión SHA256, item ID y booleano estricto. Locks Space→Service→ítems y ACL dinámica de Space/Hogar/todas las recetas privadas del grafo, sin bypass admin. Revisión incluye contenido congelado, estados, autor/fechas y último LogEntry nativo. Stale409 precede no-op; no-op no cambia auditoría. Dos escritores con una revisión producen200/409. Auditoría mínima nativa, sin otra entidad de logs.

GET usa los mismos locks para mantener coherencia con PUT; tradeoff de simplicidad que serializa lecturas del Space. La UI lo llama solo por acción explícita, no para100 servicios al abrir la página. No se promete snapshot isolation frente a escritores nativos externos que no respeten estos locks. El límite de grafo es compartido con el existente, sin recortar capacidades para el checklist.

Pruebas PostgreSQL17 e integración250, helpersUI10 y montaje virtual del SFC3. Build063934Z, upgrade070137Z y restore065043Z sobre591 PASS; HTTP043636Z histórico sobre c07 PASS. El restore conserva dos tareas reales, no solo servicios históricos vacíos. El montaje sustituye solo API/widgets en tests unitarios, no DOM/Vuetify/navegador. Responsividad visual e impresión siguen pendientes; no certificación de iPad físico.
