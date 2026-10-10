# Referencia de rollback de la CI

El workflow conservaba el run 37451427468 como fuente de la imagen anterior. El registro oficial retenido de la CI 37972458941 demuestra que ese artefacto ya no podía descargarse. Se sustituye por el artefacto inmutable 11638282350 del run 37972458941, correspondiente a la fuente 4335e6e9b858581c724e154c799c095cddb88383 y a la imagen actualmente desplegada. La consulta de metadata del 10 de octubre devuelve `expired=false` y vencimiento 12 de octubre, 18:32:08 UTC. La fuente usada para crear la copia previa cambia al mismo commit.

El descriptor SHA256 conserva una ruta relativa a su directorio de construcción; al extraer en `prior-image` esa ruta no existe. Se comprueba su formato exacto y el hash del archivo explícito descargado, sin seguir la ruta del descriptor. La corrección conserva la validación del ImageID, la identidad fuente y los diecisiete controles G7. El caso válido pasa; un archivo alterado y una ruta de descriptor inesperada se rechazan.

El primer candidato de reservas 52d7d42 pasó frontend, tooling, 669 pruebas Cuaderno y la suite nativa. Se genera otro candidato para ejecutar toda la CI con esta corrección; esos resultados anteriores no se trasladan como certificación de la siguiente imagen.
