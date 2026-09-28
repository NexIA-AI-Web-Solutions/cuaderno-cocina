# Escandallo Esencial contra PostgreSQL

`python -m unittest cuaderno.tests.test_domain_costing` en el contenedor: 12 pruebas, OK.

Sobre la receta nativa `Caldo demo G0` (id 1), ingrediente 400 mL de Aceite demo, envase 5 L:

- Precio 32.00 → `display` 2.56, `saved_recipe` false, raciones de la receta siguen en 1.
- Precio nuevo 35.00 (otra `PriceVersion`, la de 32 no se reescribe) → `display` 2.80.

El precio ausente queda cubierto por el caso C005 del contrato: estado `incomplete` y total `null`, no cero.
