---
name: cuaderno-security
description: "Revisar autenticación, capacidades, roles, archivos, importaciones y privacidad de Cuaderno Cocina."
---

# cuaderno-security

1. Leer docs/08-SECURITY.md; proteger datos de recetas y usuarios sin inventar perfiles personales.
2. Sesiones mantenidas por librería, no registro público ni credenciales por defecto.
3. Comprobar autorización por recurso, acción y edición en servidor; ocultar botones no basta.
4. Probar XSS/CSRF, subida de archivo falsa, path traversal y límites de importación.
5. No datos reales, secretos o recetas completas en logs, Git o servicios externos.
6. Clasificar hallazgos con ruta, reproducción e impacto; no certificar normativa por pasar tests.
7. Revisor independiente no edita producción para autocorregir y aprobar su propio diff.

## Entrega

Resumen de cambios o hallazgos, archivos concretos, comandos ejecutados, códigos de salida, evidencia y límites. Las instrucciones de esta skill no conceden permisos extra ni sustituyen las capacidades reales del cliente.
