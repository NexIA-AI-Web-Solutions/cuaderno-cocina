# TDD y pruebas de aceptación

## Pirámide
- Dominio puro: pytest sobre Decimal/unidades/precios/rendimientos/subrecetas; tablas golden e invariantes, cero DB y cero API remota.
- Integración: pytest-django + PostgreSQL real, migraciones completas, transacciones, scopes, bulk, permisos y concurrencia. SQLite no sustituye Postgres para la aceptación.
- Frontend: Vitest + Vue Test Utils si no existe equivalente nativo, componentes reales y cliente API simulado únicamente en tests unitarios.
- End-to-end: Playwright contra build, backend y BD reales, Chromium/Firefox/WebKit y viewports objetivo. `axe` como ayuda, más teclado y revisión visual.
- Operación: restauración a entorno nuevo, migración desde pin, restart, export/import, rendimiento y smoke de imagen.

## Flujo de cada cambio
1. Definir contrato o caracterizar el comportamiento heredado.
2. Escribir un test nuevo que falle por la carencia esperada (no por dependencia ausente cuando se evalúa comportamiento).
3. Guardar comando, commit, salida y motivo en evidencia RED.
4. Implementar lo mínimo; ejecutar test y guardar GREEN.
5. Refactorizar y ejecutar regresión relevante + chequeos comunes.
6. Revisor distinto al autor inspecciona lógica/tests/diff; líder integra.
En wiring/CI/documentación, usar validación y revisión; no simular RED/GREEN artificial.

## Fixtures incluidas
`tests/cuaderno/contracts/costing-cases.json`: resultados decimales independientes y entradas inválidas; `acceptance.feature`: recorridos. NO constituyen una app implementada ni deben devolverse como producción. Crear un adaptador de tests hacia el motor real sin copiar resultados esperados al código. Casos nuevos se calculan a mano o con oráculo separado; no llamar a la función bajo test para construir su esperado.

## Criterios
Todos los contratos críticos pasan. En nuevos módulos de dinero/movimientos, objetivo >=95% branch; resto código nuevo >=85% lines como señal, no sustituto de ejemplos. No exigir cobertura global arbitraria a upstream antes de trabajar; fijar baseline y no empeorarlo. No tests con sleeps arbitrarios ni selectores por CSS frágil: usar roles/labels.

## Casos especialmente obligatorios
Desconocido ≠ gratis; envase ≠ unidad base; no conversión masa-volumen sin densidad; merma una vez; raciones sin persistir; ciclos subrecetas; precio nuevo no altera snapshot anterior; import idempotente; conflicto de edición; stock concurrente; receipt retry; CSRF/IDOR; receta privada no exportable; media privada no pública; compra no recibida no aumenta saldo.

## Regresiones de UI
Baseline de Tandoor antes/después. Ampliación visual coherente sin reescribir pantallas. Capturas desktop/tablet/móvil y console/network error-free en recorridos. WebKit CI es aproximación, revisión real iPad por separado.

## Registro de comandos
G0 debe crear `tooling/cuaderno/commands.json` con comandos reales del pin y nuevos checks. `python scripts/cuaderno/check.py <nombre>` los ejecutará de forma comprobable (incluido en kit). Si el comando no está configurado, falla: no debe imprimir éxito ni “simular test”.
Nunca declarar G7 aprobada porque pasen los tests del kit. Los del kit solo verifican bootstrap, configuración y fixtures.
