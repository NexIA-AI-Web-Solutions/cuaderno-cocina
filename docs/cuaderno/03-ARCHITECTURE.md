# Arquitectura técnica

## Base real fijada
Tandoor 2.6.15: backend Python/Django 5.2 (requirements fijadas), DRF, frontend `vue3/` Vue 3 + Vuetify 3 + Pinia + Vite. Dockerfile inspeccionado usa Python 3.13. No usar el Python 3.14 del host para forzar dependencias distintas. Versiones exactas y digest de imagen se validan en G0, no se actualiza todo a latest.
PostgreSQL para desarrollo integrado, tests de persistencia y producción. Ejemplo oficial consultado utiliza PostgreSQL 16; conservar línea soportada por el pin y congelar parche/digest. No sustituir por SQLite solo para ahorrar un servicio: Tandoor utiliza componentes PostgreSQL de búsqueda; evitar bifurcación y falsa portabilidad.

## Unidad de despliegue
Un proyecto Compose: app Tandoor personalizada + PostgreSQL + proxy TLS existente o pequeño proxy cuando haga falta. Nginx embebido de upstream solo si sigue siendo necesario. No duplicar proxies sin razón. Primera reproducción conserva upstream; optimizar después con mediciones.
Vue se compila en build y sirve como estático: no dev server ni toolchain frontend en producción cuando se pueda separar con test. Redis/worker adicionales solo si el pin realmente los requiere para funciones seleccionadas y queda documentado; una dependencia listada no implica servicio obligatorio.
No usar servidor Django de desarrollo en entrega; misma base y migraciones en local y producción.

## Extensiones dentro del mismo proyecto
Propuesta a validar contra los puntos de extensión existentes:
```
cuaderno/                    # app Django nueva, registrada por patch mínimo
  apps.py
  models/                    # únicamente nuevas entidades de negocio
  domain/                    # aritmética y validación puras
  services/                  # casos de uso y transacciones
  api/                       # serializers/viewsets/permissions DRF
  migrations/
  tests/
vue3/src/cuaderno/
  components/                # Vuetify y tokens heredados
  pages/
  composables/
  services/                  # cliente tipado, no secretos
  locales/es.json
  tests/
docs/cuaderno/
scripts/cuaderno/
tooling/cuaderno/
```
No imponerla si el pin ofrece un módulo nativo equivalente más mantenible: justificar ADR. No escribir todo en `cookbook/models.py` ni crear un segundo sistema de recetas.

## Parches mínimos permitidos
Registro app Django/settings/URLs; routers y menús Vue; componente Costes en receta; endpoints nativos que necesiten versionado o protección de escritura de stock; handlers de merge/delete para preservar FK de precios/movimientos. Cada cambio a núcleo tiene justificación y test. Ver `UPSTREAM_PATCHES.md`.

## Ownership de datos
| Dato | Autoridad |
|---|---|
| Usuario/Space/Household/permisos | Tandoor |
| Receta/Step/Ingredient/Food/Unit | Tandoor |
| Menús y listas | Modelos Tandoor con extensiones si faltan campos |
| Precio actual de referencia, moneda, formato | Catálogo de escandallo del producto ligado a Food |
| Coste calculado | Servicio Decimal determinista; respuesta con versión/fuentes |
| Compra/recepción/variación de precio | Documentos profesionales vinculados a Food y al historial |
| Stock | Ruta de mutación única sobre InventoryEntry/Log nativos extendidos; ledger adicional solo si ADR demuestra la necesidad y define proyección atómica, nunca segunda autoridad |

Nuevos campos no se copian a food.name/description para “ahorrar tabla”. Extensiones y relaciones tienen Space y verificaciones cruzadas. Señales, bulk updates, merges/importadores y admin forman parte de la auditoría de integridad.

## Contratos de API
Namespaces de extensión `/api/cuaderno/...` (ruta propuesta a confirmar). Reutilizar autenticación/cookies/CSRF, no otro JWT ni proveedor. OpenAPI como fuente de tipos; errores de dominio explícitos; ids estables; cantidades y importes como strings decimales; `currency`, `as_of`, `price_policy`, `version`, `warnings` en escandallos. Toda query scoping + object permissions, también batch y export.
Actualizaciones con versión/If-Match y 409/412 comprensible. Paginación obligatoria y caps. No funciones de escritura con GET. Aislar formatos de importación de modelos ORM.
