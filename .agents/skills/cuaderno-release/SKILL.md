---
name: cuaderno-release
description: "Cerrar una versión solo con pruebas reproducibles, revisión independiente, manuales y límites externos explícitos."
---

# cuaderno-release

1. Leer docs/12-DEFINITION-OF-DONE.md y el estado real de todas las tareas.
2. Comprobar código integrado, no solo resumen de workers o capturas.
3. Ejecutar verify, seguridad, E2E release, restore y bench; guardar comandos/códigos/versiones.
4. Auditar dependencias, licencias y artefactos para no publicar secretos o datos reales.
5. Distinguir LOCAL_VERIFIED, LINUX_VERIFIED, iPad físico, migración cliente y deploy externo.
6. Entregar manuales, paquete runtime reproducible y hash; no adjuntar browsers o caches de desarrollo.
7. Un paso no ejecutado es NOT_RUN. No declarar terminado con un fallo crítico/alto aplicable abierto.

## Entrega

Resumen de cambios o hallazgos, archivos concretos, comandos ejecutados, códigos de salida, evidencia y límites. Las instrucciones de esta skill no conceden permisos extra ni sustituyen las capacidades reales del cliente.
