# language: es
Característica: Existencias consistentes en todas las rutas
  Escenario: Recepción idempotente
    Dado 10 kg de arroz registrados
    Cuando confirmo una recepción de 5 kg y reintento la misma operación
    Entonces el saldo es 15 kg y existe una sola recepción efectiva

  Escenario: Dos consumos simultáneos
    Dado 10 kg de un alimento y no se permite saldo negativo
    Cuando dos peticiones simultáneas intentan consumir 7 kg y 6 kg
    Entonces solo una se confirma y la otra recibe un conflicto
    Y el saldo y los movimientos coinciden

  Escenario: Pedido no es recepción
    Dado un pedido de 12 litros de aceite pendiente de entrega
    Cuando lo guardo
    Entonces no aumenta el inventario

  Escenario: No hay ruta nativa que salte el nuevo registro de movimientos
    Dado un alimento gobernado por el servicio de movimientos
    Cuando un cliente utiliza una ruta nativa de Tandoor para cambiar su saldo
    Entonces la misma transacción registra el movimiento o la ruta rechaza expresamente la operación
    Y nunca quedan dos saldos independientes
