# Esencial: comprobación real de navegador de Reservas

10 de octubre de 2026. Entorno local aislado http://127.0.0.1:18082, Chromium 1234 mediante Playwright; cuentas Esencial Responsable, Cocina y Consulta. Una instancia de navegador como máximo, cerrada al terminar. Sin escrituras API, mutaciones, trazas, despliegue ni cambios de código. Credenciales leídas en memoria y excluidas de los artefactos.

**Resultado final: 27 PASS, 0 FAIL**, nueve comprobaciones por rol. [Resultados detallados](results.json) y [script reproducible](run.cjs).

| Comprobación por rol | Resultado y evidencia |
|---|---|
| Inicio de sesión real y navegación | PASS: identidad comprobada y ningún enlace de navegación a Reservas. [Responsable](responsable-home.png), [Cocina](cocina-home.png), [Consulta](consulta-home.png). |
| Ruta directa /cuaderno/reservas | PASS a 390, 768, 1024 y 1440 px: aviso de disponibilidad en Profesional e Integral, sin formulario ni botones de creación de reservas. Sin desbordamiento horizontal del documento. [Responsable 390](responsable-unavailable-390.png), [Cocina 768](cocina-unavailable-768.png), [Consulta 1440](consulta-unavailable-1440.png). |
| Comparativa comercial expandida | PASS a los cuatro anchos: fila Reservas internas, Esencial «No habilitado», Profesional e Integral «Incluido». Precios mostrados sin cambios: 500 € y 17 €/mes, 1000 € y 20 €/mes, 1500 € y 30 €/mes. Texto informativo de condiciones comprobado. [Responsable 390](responsable-comparison-390.png), [Cocina 1024](cocina-comparison-1024.png), [Consulta 1440](consulta-comparison-1440.png). |

Los 27 registros enumeran pasos, resultado esperado, observado y captura individual. No se detectaron eventos de consola o HTTP fallido en las sesiones finales aprobadas. Esta evidencia comprueba la exclusión funcional y presentación de Esencial; no certifica los flujos de creación, estados o inventario de otras ediciones, cubiertos por otros agentes.

## Intentos anteriores preservados

[Primer intento](harness-initial-label-mismatch.json): la aserción del script esperaba «No incluido», mientras la interfaz mostraba correctamente «No habilitado». Se corrigió la expectativa del script. Las comprobaciones previas de navegación y exclusión sí habían pasado; el fallo de etiqueta fue del arnés.

[Segundo intento](retry-with-login-throttle.json): los inicios de sesión de Responsable y Cocina recibieron HTTP 429 del límite nativo de acceso y agotaron la espera de navegación. Consulta completó sus nueve comprobaciones. El intento final dirigido completó las nueve de Responsable y Cocina, sin 429. Los resultados finales combinan esas sesiones completas sin contar los fallos de entorno como defectos de Reservas. Ningún inicio de sesión adicional se hizo después de completar la ejecución.

No se crearon registros, por lo que no fue necesaria limpieza de datos. Las 27 capturas y el script quedan disponibles en esta carpeta. No se recopilaron cookies, cabeceras de autorización ni almacenamiento de sesión.
