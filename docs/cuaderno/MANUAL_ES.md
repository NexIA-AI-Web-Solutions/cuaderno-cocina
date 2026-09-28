# Cuaderno Cocina — uso local

La aplicación es Tandoor con el módulo de costes. Abre `http://127.0.0.1:18080` cuando el contenedor está en marcha.

Cuenta de demostración, solo en esta máquina: usuario `demo`, contraseña `Demo-Cocina-2026!`.

## Esencial

1. Entra y abre Costes.
2. Crea el alimento y la unidad en las pantallas nativas de Tandoor.
3. Registra el formato, por ejemplo garrafa de 5 L a 32 €. Sin existencias.
4. En la receta, el panel muestra el coste y el coste por ración. Cambiar las raciones de la vista no guarda la receta.
5. Si falta un precio, el total queda incompleto. No aparece como cero.
6. Imprime desde el navegador: el panel de coste entra en la página.

## Profesional e Integral

Esas operaciones exigen subir la edición del espacio en `PUT /api/cuaderno/edition/` con `profesional` o `integral`. Un pedido no mueve stock. Una recepción usa clave de idempotencia. Planificar un servicio no descuenta existencias. Un alérgeno no declarado no se da por ausente.

## Copia

Con la base aislada en marcha:

`python scripts/cuaderno/backup.py`

Eso vuelca solo `cuaderno-g0-t002-db`. No hay despliegue en el VPS ni prueba en un iPad físico.
