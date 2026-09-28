# 03 · Modelo de datos y estructura del repositorio

## Tablas sugeridas (migraciones incrementales)

| Bloque | Tablas | Invariantes principales |
|---|---|---|
| Acceso | Tablas oficiales de Better Auth; user_profile | Sesión protegida, rol separado, sin contraseñas propias |
| Instalación | kitchen_settings | Una instalación, moneda, base comparable de precios, edición servidor |
| Ingredientes | ingredient, purchase_format, ingredient_price_event | Dimensión estable; cantidad positiva; precio null distinto de cero |
| Recetas | recipe, recipe_line, category, recipe_category, media_asset | Versionado, referencia existente, orden, archivado |
| Profesional | recipe_yield, allergen, ingredient_allergen, service, service_recipe, internal_reservation | DAG sin ciclos, servicio con fuente de comensales única |
| Integral | supplier, supplier_product, purchase, purchase_line, receipt, receipt_line | Unidades comparables, recepción idempotente y parcial |
| Stock | stock_movement, stock_balance | Ledger autoritativo; balance derivado verificable; saldo no negativo |
| Operación | import_batch, import_mapping, audit_event, idempotency_record | Procedencia, permisos y resultados trazables |

No crear todas las tablas el primer día. Core en G1/G2, Profesional en G3, Integral en G4. El motor de licencias no es una tabla de pagos; la edición se configura por servidor.

Cada tabla nueva tiene migration SQL revisada, pruebas de upgrade y referencia de su contrato. Auth usa el esquema que genere la versión instalada de Better Auth, no una copia antigua inventada.

## Campos clave

`ingredient`: id UUID, name, normalized_search_name, dimension, active_cost_format_id, archived_at, version.
`purchase_format`: id, ingredient_id, label, amount_decimal, unit, price_cents nullable, price_known, updated_at, version. Restricción evita combinaciones null/known incompatibles.
`recipe`: id, title, normalized_search_title, base_servings, preparation_text, photo_id nullable, archived_at, version.
`recipe_line`: id, recipe_id, ingredient_id XOR child_recipe_id, amount_decimal, unit, quantity_basis, position. child_recipe_id solo Profesional.
`media_asset`: opaque id, private storage key, content hash, dimensions, byte length, MIME verificado, creator.
`stock_movement`: id, ingredient_id, quantity_delta_decimal, value_delta_decimal, event_kind, source_type/id, idempotency_key, actor_id, occurred_at, reason, reversal_of nullable.

Tipos monetarios y cantidad se basan en `02-DOMAIN-CONTRACTS.md`, no en comodidad de un ORM. SQL CHECK y servicios deben reforzarse mutuamente. Índices para FK, filtros por fecha, búsqueda normalizada, referencias de importación y claves únicas de idempotencia.

## Estructura objetivo

```text
cuaderno-cocina/
  AGENTS.md
  README.md
  .agents/skills/<skill>/SKILL.md
  .codex/config.toml
  .codex/agents/*.toml
  docs/
  tooling/
  examples/
  src/
    app.html
    hooks.server.ts
    lib/
      domain/
        quantities/ money/ costing/ recipes/ planning/ inventory/
      application/
        ingredients/ recipes/ services/ purchasing/ stock/ imports/
      server/
        auth/ db/schema/ db/repositories/ storage/ audit/ permissions/
      components/
        ui/ layout/ ingredients/ recipes/ planning/ inventory/
      validation/
      i18n/es.ts
      styles/tokens.css
    routes/
      (public)/acceso/
      (app)/+layout.server.ts
      (app)/recetas/
      (app)/ingredientes/
      (app)/planificacion/
      (app)/compras/
      (app)/inventario/
      (app)/ajustes/
      media/[id]/+server.ts
      exportar/+server.ts
      health/ready/+server.ts
      api/auth/[...all]/+server.ts
  drizzle/
  tests/
    unit/ integration/ e2e/ security/ fixtures/ performance/
  scripts/
    setup-local.ts seed-demo.ts backup.ts restore.ts import.ts export.ts
  deploy/
    Caddyfile.example cuaderno-cocina.service.example
  .github/workflows/ci.yml
  package.json
  pnpm-lock.yaml
  svelte.config.js
  vite.config.ts
  tsconfig.json
  playwright.config.ts
  vitest.config.ts
```

Las carpetas vacías no se crean para aparentar progreso. Se materializan al implementar cada módulo. Un repositorio y un package.json; no monorepo de tres apps, no paquetes de negocio publicados por separado.

## Datos fuera del código

Desarrollo: `var/` ignorado por Git. Producción: `/var/lib/cuaderno-cocina/<installation>/`, con DB, media y backups en directorios separados y permisos mínimos. Una nueva release no reemplaza esos directorios.

`artifacts/` contiene evidencia sintética, no datos del cliente. No guardar binarios de Node, SQLite o navegador en Git. Exportaciones del cliente y contraseñas se excluyen con defensas de configuración y revisión, no solo .gitignore.
