---
name: cuaderno-storage
description: "Mantener persistencia SQLite, imágenes, backups y despliegue ligero Windows/Linux sin pérdida de datos."
---

# cuaderno-storage

1. Leer docs/10-PERFORMANCE-STORAGE.md y docs/11-DEPLOY-BACKUP.md.
2. Verificar SQLite embebido y parches; transacciones cortas, disco local persistente, un escritor.
3. No copiar DB viva ignorando WAL ni copiar node_modules Windows a Linux.
4. Media privada inmutable y manifiesto coherente con snapshot; no borrar blobs durante backup.
5. Restaurar en destino aislado y verificar costes, saldos, integridad y hashes.
6. Medir disco/RSS/latencia antes de optimizar; no inventar resultados ni desplegar sin permiso.
7. Retención/logs acotados y destino externo cifrado pendiente si falta configuración.

## Entrega

Resumen de cambios o hallazgos, archivos concretos, comandos ejecutados, códigos de salida, evidencia y límites. Las instrucciones de esta skill no conceden permisos extra ni sustituyen las capacidades reales del cliente.
