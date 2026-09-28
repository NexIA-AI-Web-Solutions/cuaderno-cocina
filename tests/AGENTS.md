# Pruebas

Oráculos independientes, fixtures sintéticas, DB temporal real por suite. No saltarse tests para cerrar hitos; no generar expected llamando la función que se está probando. Fallos por requisitos inexistentes se reportan, no se pintan como PASS.

WebKit emulado no equivale a iPad físico. Las pruebas del handoff en tools/ no son pruebas de aplicación.
