# Publicación del código en GitHub — 2026-10-06

El propietario solicita subir ahora el trabajo a GitHub y prohíbe arrancar Docker. Esta publicación de código no certifica una release aprobada ni un despliegue de producción.

## Corrección incorporada

La lectura de movimientos valida membresía, rol, hogar, espacios, alimento, unidad y privacidad de recetas dentro de la misma sentencia PostgreSQL que obtiene los datos. Se elimina la consulta previa de IDs autorizados, que permitía conservar permisos revocados entre ambas consultas.

La batería de seguridad del candidato R8 detectó tres fallos de revalidación de movimientos: retirada de grupos, pérdida del rol administrador y cambio de hogar. La corrección conserva esas regresiones y añade una prueba de retirada de acceso compartido a una receta privada inmediatamente antes de la proyección.

## Validación y pendientes

- Sintaxis Python de los dos archivos modificados: PASS.
- `git diff --check`: PASS.
- Revisión del diff: consulta parametrizada única; se mantienen límites, orden y representación de la respuesta.
- Pruebas PostgreSQL de la corrección: pendientes; no se arranca Docker por instrucción explícita del propietario.
- La aceptación completa de un nuevo candidato, incluido Playwright, auditoría de imagen y recuperación, sigue pendiente. Los resultados de candidatos anteriores no se transfieren a esta fuente.

Destino autorizado: `NexIA-AI-Web-Solutions/cuaderno-cocina`, rama `cuaderno/main`. No se publica en upstream, se crea una release aprobada ni se despliega un VPS mediante este push.
