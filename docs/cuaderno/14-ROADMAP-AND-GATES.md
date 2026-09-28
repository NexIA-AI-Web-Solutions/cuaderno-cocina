# Roadmap y puertas de aceptación

Las tareas máquina están en `tooling/cuaderno/tasks.json`; este archivo expresa las puertas. Construir funcionalidad completa no implica desplegarla sin permiso.

| Gate | Resultado | Evidencia mínima |
|---|---|---|
| G0 | Base Tandoor reproducida y diferencias entendidas | SHA/verificaciones, versiones, tests baseline, capturas, mapa de modelos y comandos reales. |
| G1 | Esencial funciona sin inventario | Food/precios→receta→raciones→coste→cambio precio→reabrir; tests decimales y permisos. |
| G2 | Esencial entregable local | Import/export genérico, prueba de backup inicial, impresión, UI móvil/tablet/PC y guía. |
| G3 | Profesional coherente | Subrecetas, mermas, menús/servicios, necesidades consolidadas, notas de alérgenos y fichas. |
| G4 | Integral coherente | Compras/recepciones/stock/desperdicio, retries y concurrencia, impacto y reposición; sin doble saldo. |
| G5 | Hardening | Permisos privados/Spaces, upload, CSRF/SSRF según rutas, dependencies, performance y storage. |
| G6 | Release reproducible | Build limpio, migration-from-pin, restore nuevo, tres ediciones, docs y SBOM. |
| G7 | Revisión independiente y entrega | Ningún falso DONE, evidencia comprobada, comandos probados, gaps explícitos y revisión final. |

## Detención válida
Fallo de acceso al repo/modelo, falta de infraestructura autorizada, requisito de cliente que no puede inferirse o datos reales no disponibles. Continuar tareas no dependientes. No pedir confirmación para elegir nombres de variables o añadir un test.

## No es aceptación
“Compila” sin ejecutar; endpoints 200 con datos falsos; UI sin persistencia; subir un precio que no invalida el escandallo; aceptar stock incoherente; un ZIP de docs confundido con producto; pasar solo tests de este kit.

## Preview Esencial
Al terminar G2, crear release local o tag solo si working tree/revisión lo permiten; guardar instrucciones de evaluación con datos sintéticos. Continuar con G3–G7 según solicitud de producto completo, manteniendo Esencial libre de regresiones.
