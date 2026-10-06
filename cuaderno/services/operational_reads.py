"""Parameterized PostgreSQL projections for complete operational list responses.

Authorization is evaluated in the same statement as its data; there is no
permission or response cache. These projections do not participate in writes.
"""
import json

from django.db import connection
from django.utils import timezone

def _food_visibility(path):
    if path not in ('"cookbook_food"."path"', 'food."path"'):
        raise ValueError("Unknown fixed projection path")
    return f"""(
      NOT EXISTS (SELECT 1 FROM "cookbook_food" linked
                  WHERE linked.space_id = %(space)s AND linked.recipe_id IS NOT NULL)
      OR NOT EXISTS (
        SELECT 1 FROM "cookbook_food" ancestor
        WHERE ancestor.space_id = %(space)s AND ancestor.recipe_id IS NOT NULL
          AND ancestor.path = substring({path}, 1, length(ancestor.path))
          AND NOT EXISTS (
            SELECT 1 FROM "cookbook_recipe" recipe
            WHERE recipe.id = ancestor.recipe_id AND recipe.space_id = %(space)s
              AND (NOT recipe.private OR recipe.created_by_id = %(user)s
                   OR EXISTS (SELECT 1 FROM "cookbook_recipe_shared" shared
                              WHERE shared.recipe_id = recipe.id AND shared.user_id = %(user)s))
          )
      )
    )"""


AUTH_SQL = """WITH auth AS MATERIALIZED (
    SELECT MIN(membership.household_id) AS household_id,
           BOOL_OR(role.name = 'admin') AS admin
    FROM "cookbook_userspace" membership
    LEFT JOIN "cookbook_userspace_groups" roles ON roles.userspace_id = membership.id
    LEFT JOIN "auth_group" role ON role.id = roles.group_id
    WHERE membership.user_id = %(user)s AND membership.active
    GROUP BY membership.user_id
    HAVING COUNT(DISTINCT membership.id) = 1
       AND BOOL_AND(membership.space_id = %(space)s)
       AND BOOL_OR(role.name IN ('guest', 'user', 'admin'))
)
"""


PACKAGE_SQL = AUTH_SQL.rstrip() + """,
latest_prices AS MATERIALIZED (
    SELECT DISTINCT ON (price.package_id)
           price.package_id, price.id, price.amount::text AS amount,
           price.explicit_free, price.valid_from
    FROM "cuaderno_priceversion" price
    WHERE price.space_id = %(space)s AND price.valid_from <= %(now)s
    ORDER BY price.package_id, price.valid_from DESC, price.id DESC
)
SELECT COALESCE(JSON_AGG(ROW_TO_JSON(document))::text, '[]')
FROM (
    SELECT package.id, package.food_id AS food, food.name AS food_name,
           package.unit_id AS unit, unit.name AS unit_name, package.label,
           package.quantity::text AS quantity, package.is_reference,
           CASE WHEN latest_price.id IS NULL THEN NULL
                ELSE JSON_BUILD_OBJECT(
                    'id', latest_price.id, 'amount', latest_price.amount,
                    'explicit_free', latest_price.explicit_free,
                    'valid_from', latest_price.valid_from
                ) END AS current_price
    FROM "cuaderno_packageformat" package
    JOIN "cookbook_food" food ON food.id = package.food_id
    JOIN "cookbook_unit" unit ON unit.id = package.unit_id
    LEFT JOIN latest_prices latest_price ON latest_price.package_id = package.id
    WHERE package.space_id = %(space)s
      AND EXISTS (SELECT 1 FROM auth)
      AND food.space_id = %(space)s AND unit.space_id = %(space)s
      AND """ + _food_visibility('food."path"') + """
    ORDER BY package.id
) document
"""


# The authorized IDs and response are one statement, so PostgreSQL evaluates
# both from the same snapshot. Materializing the small ID array also prevents
# the Food/Unit/private-recipe ACL graph from running for every movement row.
MOVEMENT_SQL = AUTH_SQL.rstrip() + """,
authorized_entries AS MATERIALIZED (
    SELECT COALESCE(ARRAY_AGG(entry.id ORDER BY entry.id), ARRAY[]::bigint[]) AS ids
    FROM "cookbook_inventoryentry" entry
    JOIN "cookbook_inventorylocation" location ON location.id = entry.inventory_location_id
    JOIN "cookbook_household" household ON household.id = location.household_id
    LEFT JOIN "cookbook_food" food ON food.id = entry.food_id
    LEFT JOIN "cookbook_unit" unit ON unit.id = entry.unit_id
    WHERE entry.space_id = %(space)s AND location.space_id = %(space)s
      AND household.space_id = %(space)s
      AND EXISTS (SELECT 1 FROM auth)
      AND ((SELECT admin FROM auth) OR household.id = (SELECT household_id FROM auth))
      AND (entry.unit_id IS NULL OR unit.space_id = %(space)s)
      AND (entry.food_id IS NULL OR (food.space_id = %(space)s AND
""" + _food_visibility('food."path"') + """))
)
SELECT COALESCE(JSON_AGG(ROW_TO_JSON(document))::text, '[]')
FROM (
    SELECT movement.id, movement.kind, movement.quantity::text AS quantity,
           movement.entry_id AS entry, movement.balance_after::text AS balance,
           movement.reverses_id AS reverses,
           to_char(movement.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS')
             || CASE WHEN EXTRACT(MICROSECONDS FROM movement.created_at)::integer %% 1000000 = 0
                     THEN '' ELSE '.' || to_char(movement.created_at AT TIME ZONE 'UTC', 'US') END
             || '+00:00' AS created_at,
           movement.created_by_id AS created_by, movement.metadata_snapshot
    FROM "cuaderno_stockmovement" movement
    WHERE movement.space_id = %(space)s
      AND movement.entry_id = ANY((SELECT ids FROM authorized_entries)::bigint[])
    ORDER BY movement.id DESC
    LIMIT 100
) document
"""


SERVICE_ROWS_SQL = AUTH_SQL.rstrip() + """
SELECT plan.id, plan.title, plan.covers, plan.service_date, plan.state,
       plan.meal_plan_id, plan.household_id, plan.snapshot,
       plan.confirmed_at, plan.produced_at, plan.created_by_id,
       meal.recipe_id
FROM "cuaderno_serviceplan" plan
LEFT JOIN "cookbook_mealplan" meal ON meal.id = plan.meal_plan_id
WHERE plan.space_id = %(space)s
  AND EXISTS (SELECT 1 FROM auth)
  AND (
      (SELECT admin FROM auth)
      OR plan.household_id = (SELECT household_id FROM auth)
      OR (plan.household_id IS NULL AND plan.created_by_id = %(user)s)
  )
ORDER BY plan.id DESC
LIMIT 100
"""


VISIBLE_RECIPE_IDS_SQL = """
SELECT recipe.id
FROM "cookbook_recipe" recipe
WHERE recipe.space_id = %(space)s AND recipe.id = ANY(%(recipe_ids)s)
  AND (
      NOT recipe.private OR recipe.created_by_id = %(user)s
      OR EXISTS (
          SELECT 1 FROM "cookbook_recipe_shared" shared
          WHERE shared.recipe_id = recipe.id AND shared.user_id = %(user)s
      )
  )
"""


def _document(sql, request, **parameters):
    if connection.vendor != "postgresql":
        raise ValueError("Operational projections require PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute(sql, {"space": request.space.pk, "user": request.user.pk, **parameters})
        return cursor.fetchone()[0]


def package_document(request):
    return _document(PACKAGE_SQL, request, now=timezone.now())


def movement_document(request):
    return _document(MOVEMENT_SQL, request)


def service_plan_rows(request):
    """Return fixed list columns without Django's per-request query compiler cost."""
    if connection.vendor != "postgresql":
        raise ValueError("Operational projections require PostgreSQL")
    columns = (
        "pk", "title", "covers", "service_date", "state", "meal_plan_id",
        "household_id", "snapshot", "confirmed_at", "produced_at",
        "created_by_id", "meal_plan__recipe_id",
    )
    with connection.cursor() as cursor:
        cursor.execute(SERVICE_ROWS_SQL, {"space": request.space.pk, "user": request.user.pk})
        rows = []
        for values in cursor.fetchall():
            row = dict(zip(columns, values))
            # Django deliberately configures raw PostgreSQL cursors to leave
            # jsonb as text; model JSONField normally performs this decode.
            if isinstance(row["snapshot"], str):
                try:
                    row["snapshot"] = json.loads(row["snapshot"])
                except (json.JSONDecodeError, UnicodeError):
                    # Historical corruption must reach the existing list ACL
                    # validator as an invalid value and remain undisclosed.
                    pass
            rows.append(row)
        return rows


def visible_service_recipe_ids(request, recipe_ids):
    if not recipe_ids:
        return set()
    if connection.vendor != "postgresql":
        raise ValueError("Operational projections require PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute(
            VISIBLE_RECIPE_IDS_SQL,
            {"space": request.space.pk, "user": request.user.pk, "recipe_ids": list(recipe_ids)},
        )
        return {row[0] for row in cursor.fetchall()}
