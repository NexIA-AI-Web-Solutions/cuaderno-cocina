# language: es
Característica: Producción integrada y presupuestos por comensal
  Escenario: Un servicio consolida subelaboraciones
    Dado un servicio interno para 45 personas con dos platos que usan la misma salsa
    Y la salsa tiene receta, rendimiento y coste conocidos
    Cuando el responsable genera la hoja de producción
    Entonces las cantidades y el coste consolidado no duplican ni omiten la salsa
    Y puede imprimir la hoja usando los componentes del recetario
    Y planificar no consume inventario

  Escenario: Reserva interna sin sistema de pagos
    Dado un servicio de comida con 20 comensales previstos
    Cuando se registran 5 comensales adicionales y se cancelan 2
    Entonces la previsión es 23
    Y no se crea cobro, reserva pública ni asignación de mesa

  Escenario: Ciclo de subrecetas rechazado
    Dado una receta A que utiliza B
    Cuando se intenta añadir A como parte de B
    Entonces se rechaza la referencia circular con un error comprensible
