---
name: cuaderno-import
description: "Implementar o auditar importación/exportación versionada y migración reversible; no permite acceder sin autorización a programas del cliente."
---

# cuaderno-import

1. Leer docs/09-IMPORT-MIGRATION.md y las muestras sintéticas.
2. Distinguir importador general de extractor del programa antiguo aún desconocido.
3. Validación→normalización→preview→incidencias→confirmación→commit→informe.
4. Preservar external_id/procedencia; no casar nombres similares, inventar cantidades ni bajar precisión.
5. Repetir importación no duplica; error no deja escrituras parciales.
6. Probar roundtrip, relaciones, CSV peligroso, ZIP y límites; backup antes de datos reales.
7. Sin acceso origen, terminar genérico y marcar CLIENT_MIGRATION_PENDING.

## Entrega

Resumen de cambios o hallazgos, archivos concretos, comandos ejecutados, códigos de salida, evidencia y límites. Las instrucciones de esta skill no conceden permisos extra ni sustituyen las capacidades reales del cliente.
