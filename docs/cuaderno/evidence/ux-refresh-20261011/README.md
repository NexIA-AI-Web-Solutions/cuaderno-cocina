# Mejora de recorridos y presentación · 11 octubre 2026

Base: `a7b3f79`, correspondiente a la imagen productiva `c16fd5a58da2`.
Rama de trabajo: `cuaderno/ux-refresh-20261011`.

## Cambios comprobables

- Inicio: búsqueda directa por nombre, creación e importación visibles según permisos, cabecera con tonos y componentes del producto.
- Navegación móvil: primero los módulos de trabajo; título y cierre explícitos, cabecera fija y lista desplazable en teléfonos pequeños.
- Calendario y menús de receta: nombres accesibles y controles de al menos 44 px.
- Producción: herramientas agrupadas en un desplegable cerrado inicialmente; servicios guardados visibles sin recorrer cinco formularios; títulos enlazados a la receta nativa.
- Reservas: cambiar la fecha actualiza automáticamente lista y resumen, conservando protección frente a respuestas antiguas; platos enlazados a las recetas.
- Compras: nombre de ingrediente, formato e identificador por pedido; pulsar el título abre las recepciones existentes; acciones debajo del contenido en móvil; acceso directo al catálogo.
- Costes: nombres de formato pulsables; precio e historial dentro de un diálogo desplazable y con cierre. Se mantienen validación, borradores con error y bloqueo durante guardado.

No cambia API, aritmética, permisos, migraciones ni estructura de datos.

## Método

Tres agentes reales: cocina/reservas, compras/catálogo y auditoría/revisión independiente. Integración de inicio y navegación por el agente principal. Cada agente usó Chromium aislado, autenticación real y cuentas sintéticas autorizadas de Responsable, Cocina y Consulta.

Baseline en la web servida por Caddy. Verificación del candidato mediante interceptación de recursos estáticos en el navegador: HTML y Vue compilado locales, API y autenticación reales. No se simularon respuestas de negocio. Solo navegación, lectura, apertura/cierre de formularios y cambios de filtros: no se enviaron precios, pedidos, recepciones, reservas ni movimientos de stock.

Viewports: 390×844, 768×1024, 1024×768 y 1440×900; revisión adicional de navegación a 375×667. Chromium emulado no acredita un iPad físico ni Firefox/WebKit.

## Evidencia

- `frontend-tests.log`: **291/291 PASS**, suite completa de `vue3/src/cuaderno/*.test.mjs`; incluye tests de interacción, roles, errores y respuestas fuera de orden.
- `home-browser.json`: búsqueda, creación y navegación sin errores de página ni desbordamiento en cuatro tamaños.
- `kitchen-browser.json`: servicios, apertura de herramientas, navegación a recetas y actualización de fecha.
- `home-desktop.png`, `home-mobile.png`, `price-dialog-mobile.png`: capturas del candidato.
- Logs, scripts, capturas antes/después y revisión completos en `/home/kripta/cuaderno-ux-evidence-20261011/`. Las sesiones privadas permanecen fuera de Git.

Pruebas de búsqueda nuevas y pruebas funcionales de cocina/compras fallaron antes del cambio y pasaron después. La suite original necesitaba un contenedor de renderizado aislado; se creó sin red, volúmenes ni conexión a producción. No se apuntó ningún test automatizado de escritura a la BD productiva.

## Repetición

Desde `vue3/`, con Node 24 y dependencias de `package-lock.json` instaladas:

```sh
node --test src/cuaderno/*.test.mjs
node node_modules/vite/bin/vite.js build
```

El test existente de renderizado Markdown requiere su contenedor aislado `cuaderno-g0-t002-web`. Las pruebas de navegador están en el directorio de evidencia externo y usan las credenciales autorizadas sin imprimirlas.

## Entrega

Revisión independiente final: **SHIP**, tras corregir el cierre fijo del menú y el desbordamiento de herramientas en móvil. Bundle compilado: `/home/kripta/cuaderno-ux-evidence-20261011/cuaderno-ux-frontend.tar.gz`, SHA-256 `319de745bc84a0987a2f84f3b6d7f324696a374a54148f18e3d1e7215c7753cf`.

Candidato local compilado y probado; producción conserva su imagen original. El despliegue real requiere autorización según `AGENTS.md`. Esta entrega no sustituye los gates históricos de CI, restauración o aceptación de otros cambios documentados en el repositorio.

## Ampliación a 100 mejoras — segundo lote

Se han aceptado 60 resultados distintos en `improvements.json`: los 18 del primer lote, 20 de planificación/reservas/preparación, 20 de compras/almacén/costes y 2 de recuperación de navegación. Los 40 nativos restantes siguen en implementación y revisión. No se cuentan pruebas, capturas ni correcciones introducidas por este trabajo como resultados adicionales.

El segundo lote conserva borradores y datos al fallar peticiones, evita respuestas obsoletas, simplifica filtros y navegación y permite leer datos completos en móvil. Las pruebas funcionales acumuladas pasaron 411/411; la corrección posterior de recuperación de receta pasó sus 9 pruebas específicas. El build Vite pasó. Se verificaron los cuatro tamaños 390×844, 768×1024, 1024×768 y 1440×900 y las nueve combinaciones de edición/rol.

Las escrituras de prueba (plantillas, eventos, dietas, reservas, listas, formatos y mínimos) se ejecutaron contra una base sintética aislada en localhost:18092. La aplicación publicada no recibió escrituras de negocio ni despliegue. Credenciales y sesiones permanecen fuera de Git. Véase `final-review-batch2.md` para revisión independiente y sus límites. El aviso técnico redundante de receta403/404 mencionado allí se suprimió después con prueba roja/verde.
