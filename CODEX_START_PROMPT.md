Trabaja dentro de este repositorio para desarrollar Cuaderno Cocina DE PRINCIPIO A FIN. No quiero únicamente un nuevo plan, un scaffold ni una demo con datos en memoria: implementa y verifica la aplicación completa descrita en el paquete.

Actúa como líder con GPT-5.6 Sol. Usa los roles de `.codex/agents` para la implementación con GPT-6 Astra en razonamiento medium, la interpretación explícita de «GPT 6 Medium» de este paquete. Verifica primero los modelos y el esquema reales del cliente; no simules agentes ni cambies de modelo en silencio. Un revisor GPT-5.6 Sol en contexto nuevo no debe revisar como independiente su propio trabajo.

Lee AGENTS.md, START_HERE_ES.md y los documentos de alcance, arquitectura, dominio, orquestación, pruebas, plan y definición de terminado. Activa las skills locales pertinentes. La matriz autoritativa está en tooling/product.json y las tareas en tooling/work-packets.json.

Objetivo: ALL_TIERS. Termina primero Esencial y sus pruebas de aceptación; continúa después con Profesional e Integral. La edición predeterminada de la instalación de Elisabeth será esencial. Respeta los precios de su último WhatsApp: 500 € +17 €/mes, 1.000 € +20 €/mes y 1.500 € +30 €/mes. No implementes pagos, fiscalidad, OCR, multiempresa ni reservas públicas. Las reservas de Profesional son previsiones internas de comensales por servicio.

Arquitectura: una app SvelteKit/TypeScript, Node 24 LTS, SQLite con driver mantenido y parcheado, Drizzle, Better Auth, validación Zod, cálculo decimal exacto y UI responsive minimalista en español. No añadas infraestructura innecesaria. Windows para desarrollo y Linux para producción; persistencia y copias fuera del build.

Antes de cada funcionalidad escribe y ejecuta una prueba que falle por el motivo esperado. Implementa, verifica, refactoriza y somete el cambio a revisión independiente. Mantén los contratos de unidades, precios desconocidos, subrecetas sin ciclos, mermas, movimientos de stock y permisos. Nunca maquilles pruebas o resultados.

Recorre T001–T034 y sus dependencias sin pedirme permiso para cada paso ordinario. Puedes crear archivos, instalar dependencias aprobadas del proyecto, ejecutar pruebas y hacer commits locales focalizados. No publiques el repo, no hagas push ni deploy, no compres servicios, no uses datos reales ni toques otros proyectos. No borres trabajo anterior. Pregunta únicamente ante acceso o autorización imprescindible, datos reales que no puedas obtener, o una ambigüedad que comprometa seguridad/datos; las decisiones técnicas menores se resuelven con supuestos documentados.

Máximo dos implementadores simultáneos con archivos no solapados y un revisor. El líder es el único que integra migraciones, lockfile y cambios comunes. No uses agentes para tareas de una línea ni paralelices operaciones que escriban en la misma base. Mantén docs/STATUS.md, docs/BLOCKERS.md y docs/DECISIONS.md actualizados.

Entrega una app funcional, manual de uso en español, guía Windows/Linux, backups y restauración comprobados, importación genérica con validación, datos sintéticos, CI y evidencias reales. Ejecuta format/check/lint/tests/build, pruebas navegador Chromium/WebKit/Firefox, autorización por edición y rol, benchmark y restauración en un destino aislado. Documenta cualquier prueba de iPad físico o despliegue externo que no se haya podido realizar sin afirmar que pasó.

Empieza ahora por G0 y continúa. No termines tu respuesta únicamente con «próximos pasos». Si un límite de la herramienta obliga a interrumpir, deja checkpoint exacto y la siguiente tarea reanudable, sin declarar completado el trabajo pendiente.
