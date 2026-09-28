# language: es
Característica: Datos privados, importación segura y recuperación
  Escenario: Receta privada no se filtra por exportación o imagen
    Dado dos usuarios en Spaces diferentes y una receta privada
    Cuando el otro usuario intenta acceder por API, exportación, batch, lista o imagen
    Entonces no obtiene datos de la receta ni de sus precios

  Escenario: Archivo importado malicioso
    Dado un ZIP con una ruta ../../fuera.txt o un enlace simbólico
    Cuando intento importarlo
    Entonces se rechaza sin escribir fuera del staging ni modificar datos existentes

  Escenario: Restauración realmente comprobada
    Dado una copia local de recetas, imágenes, precios y movimientos
    Cuando restauro en una base y directorio nuevos de prueba
    Entonces coinciden conteos, hashes de imágenes, costes y saldos
    Y no se cambia la instalación original
