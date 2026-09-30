# ADR 0009 — Perfil PostgreSQL por conexión para OLTP

Estado: configuración local revisada y testada; aceptación de rendimiento abierta.

## Evidencia y decisión

El perfil192821Z-performance-profile-d7192740 conservó los presupuestos y dataset. Movimientos alcanzó5208.460ms secuencial; el EXPLAIN posterior, separado de las muestras de aceptación, consumió5037.517ms, de los cuales5031.132ms eran JIT. El subplan de ancestros tenía cero loops. No era necesario retirar la política privada: el coste estimado del plan activaba una compilación desproporcionada para esta lectura OLTP.

Se reutiliza `recipes.settings.setup_database`: `DB_OPTIONS` nativo, literal Python parseado por `ast.literal_eval` y enviado a libpq. `compose.local.yml` configura `{'options': '-c jit=off'}` solo para las conexiones de la aplicación. El servidor PostgreSQL y otros proyectos no se modifican. Los comandos benchmark reciben `TEST_DB_OPTIONS` equivalente. No se suben umbrales ni se cambian warmups, concurrentes o cardinalidades.

SHOWjit REDon193609Z→GREENoff195323Z;195711Z GREEN2/2 también caracteriza conservación `sslmode=require` junto con `options`, sin afirmar conexiónSSL. Si se configura un entornoSSL autorizado, proporcionar un único diccionario combinado mediante overrideCompose; el perfil local no hereda automáticamente DB_OPTIONS externos.

El benchmark200419Z-performance-profile-73adc2c7 RED4 mide coste237.393ms/15SQL y movimientos138.446ms/7SQL secuenciales dentro de presupuesto; servicios262.691ms/8SQL secuencial cumple. Concurrentes servicios930.143/movimientos1012.712 y formatos705.592seq/2020.425conc aún fallan500. Dataset íntegro y respuestas correctas. EXPLAIN movimientos4.712ms, sinJIT; formatos712.464ms conserva semi-join con1.124M combinaciones descartadas. Esto justifica el ajuste, no una aprobación global de rendimiento.

## Predicado de formatos

La política Food se centraliza sin alterar el predicado privado. `visible_foods` usa `OuterRef('path')`; `visible_packages` aplica el mismo predicado a `OuterRef('food__path')` con Space de formato/alimento/unidad explícitos. Evita el semi-join Food, sin IDs materializados ni evaluaciónPython previa. Caso SQL/ancestro privado/share/revoke/FKforeign RED201038Z→GREEN5/5 201316Z; revisión independiente aprobada. Regresión89PG PASS202249Z,390.970s; commitcb474ccf9. Benchmark posterior203010Z RED5/320.490s: coste303.960, servicios226.423seq/1026.090conc, movimientos213.380seq/1398.686conc, formatos530.232seq/2158.155conc. EXPLAINformatos53.789ms frente712.464 previo, SQL mejora pero presupuesto global sigue incumplido. Sin modificar muestras/umbrales. No modelo, índice, migración ni caché de permisos añadidos.

Fuentes primarias: [decisión de JIT por coste](https://www.postgresql.org/docs/16/jit-decision.html), [JIT PostgreSQL16](https://www.postgresql.org/docs/16/jit.html) y parser del checkout `recipes/settings.py`. Las queries del diagnóstico son SELECT, sobre BD sintética aislada; no certificar hardware comercial ni HTTP/socket a partir del APIClient en proceso.
