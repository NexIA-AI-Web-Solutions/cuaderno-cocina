# language: es
Característica: Recetario Esencial sobre la interfaz de Tandoor
  Escenario: Crear receta y calcular sin mantener inventario
    Dado un usuario autorizado en un Space privado con precios de ingredientes
    Y aceite a 32 euros por 5 litros y arroz a 12 euros por 5 kilos
    Cuando guarda una receta de 4 raciones con 400 ml de aceite y 750 g de arroz
    Entonces el coste de ingredientes es 4,36 euros y el coste por ración es 1,09 euros
    Y la receta persiste después de recargar y de abrir una nueva sesión
    Y no se ha creado compra ni movimiento de existencias

  Escenario: Simular comensales sin cambiar la receta de otros usuarios
    Dado una receta base de 4 raciones compartida por dos usuarios autorizados
    Cuando el primero simula 10 raciones
    Entonces ve cantidades multiplicadas por 2,5
    Y la receta base sigue siendo de 4 raciones para ambos

  Escenario: Un precio desconocido no es gratis
    Dado una receta con un ingrediente sin precio
    Cuando el usuario abre el escandallo
    Entonces ve el ingrediente pendiente y el coste como incompleto
    Y no ve un total completo con ese ingrediente valorado en cero
