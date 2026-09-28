---
name: cuaderno-domain
description: "Modelar y probar unidades, escandallos, mermas, subrecetas, planificación o inventario con exactitud decimal."
---

# cuaderno-domain

1. Leer docs/02-DOMAIN-CONTRACTS.md y examples/contracts/golden-cases.json.
2. No framework ni SQL en el dominio; entradas/salidas tipadas y errores discriminados.
3. Decimal exacto, céntimos de entrada, cantidades canónicas; precio desconocido distinto de gratis.
4. Validar dimensiones; no densidades/pesos inventados ni redondeo antes de sumar.
5. DAG sin ciclos, rendimientos una sola vez, planificación no consume stock; confirmar sí.
6. Ledger inmutable, idempotencia y saldo dentro de la misma transacción; snapshots no reescritos.
7. Probar con oráculos fijos y propiedades; reportar efecto de un cambio en otros módulos.

## Entrega

Resumen de cambios o hallazgos, archivos concretos, comandos ejecutados, códigos de salida, evidencia y límites. Las instrucciones de esta skill no conceden permisos extra ni sustituyen las capacidades reales del cliente.
