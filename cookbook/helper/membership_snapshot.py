"""Fresh PostgreSQL membership and role snapshot; only query metadata is cached."""
from functools import lru_cache

from django.db import connections

from cookbook.models import Space, UserSpace


@lru_cache(maxsize=None)
def _membership_query_shape(db_alias, filter_active):
    """Cache immutable SQL/model metadata, never authorization data."""
    connection = connections[db_alias]
    if connection.vendor != "postgresql":
        raise RuntimeError("The Cuaderno membership snapshot requires PostgreSQL")
    quote = connection.ops.quote_name

    membership_fields = tuple(UserSpace._meta.concrete_fields)
    space_fields = tuple(Space._meta.concrete_fields)
    groups_field = UserSpace._meta.get_field("groups")
    through = groups_field.remote_field.through
    group_model = groups_field.remote_field.model
    membership_link = through._meta.get_field(groups_field.m2m_field_name())
    group_link = through._meta.get_field(groups_field.m2m_reverse_field_name())
    group_name = group_model._meta.get_field("name")

    def projection(alias, prefix, fields):
        return [
            f'{alias}.{quote(field.column)} AS {quote(prefix + field.attname)}'
            for field in fields
        ]

    selected = [
        *projection("membership", "membership__", membership_fields),
        *projection("space", "space__", space_fields),
        (
            "ARRAY(SELECT DISTINCT role.{name} "
            "FROM {through} membership_role "
            "JOIN {group_table} role ON role.{group_pk} = membership_role.{group_fk} "
            "WHERE membership_role.{membership_fk} = membership.{membership_pk} "
            "AND role.{name} IS NOT NULL ORDER BY role.{name}) AS {alias}"
        ).format(
            name=quote(group_name.column),
            through=quote(through._meta.db_table),
            group_table=quote(group_model._meta.db_table),
            group_pk=quote(group_model._meta.pk.column),
            group_fk=quote(group_link.column),
            membership_fk=quote(membership_link.column),
            membership_pk=quote(UserSpace._meta.pk.column),
            alias=quote("role_names"),
        ),
    ]
    where = [
        f'membership.{quote(UserSpace._meta.get_field("user").column)} = %s',
    ]
    if filter_active:
        where.append(
            f'membership.{quote(UserSpace._meta.get_field("active").column)} = %s'
        )
    sql = " ".join((
        "SELECT", ", ".join(selected),
        "FROM", quote(UserSpace._meta.db_table), "membership",
        "JOIN", quote(Space._meta.db_table), "space",
        "ON", (
            f'space.{quote(Space._meta.pk.column)} = '
            f'membership.{quote(UserSpace._meta.get_field("space").column)}'
        ),
        "WHERE", " AND ".join(where),
        "ORDER BY", f'membership.{quote(UserSpace._meta.pk.column)}',
        "LIMIT %s",
    ))
    return sql, membership_fields, space_fields


def _converted_model_values(connection, fields, raw_values):
    """Apply the same backend/field conversion chain as Django's SQLCompiler.

    This matters for JSONField and custom fields: ``from_db`` marks model state
    but deliberately assumes values have already passed through converters.
    """
    converted = []
    for field, raw_value in zip(fields, raw_values, strict=True):
        expression = field.get_col(field.model._meta.db_table)
        converters = (
            connection.ops.get_db_converters(expression)
            + expression.get_db_converters(connection)
        )
        value = raw_value
        for converter in converters:
            value = converter(value, expression, connection)
        converted.append(value)
    return converted


def memberships_one_sql(user, *, active=None, limit=2):
    """Replacement body for ``ScopeMiddleware._memberships``."""
    if type(limit) is not int or limit < 1 or limit > 2:
        raise ValueError("Membership snapshot limit must be one or two")
    db_alias = user._state.db or "default"
    connection = connections[db_alias]
    sql, membership_fields, space_fields = _membership_query_shape(
        db_alias, active is not None,
    )
    params = [user.pk]
    if active is not None:
        params.append(bool(active))
    params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        raw_rows = cursor.fetchall()

    membership_names = [field.attname for field in membership_fields]
    space_names = [field.attname for field in space_fields]
    membership_width = len(membership_fields)
    space_width = len(space_fields)
    result = []
    for row in raw_rows:
        membership_values = _converted_model_values(
            connection, membership_fields, row[:membership_width],
        )
        space_values = _converted_model_values(
            connection,
            space_fields,
            row[membership_width:membership_width + space_width],
        )
        membership = UserSpace.from_db(db_alias, membership_names, membership_values)
        space = Space.from_db(db_alias, space_names, space_values)
        # Match select_related("space"): relation access remains zero-query and
        # parent-link/object identity checks see the same hydrated instance.
        membership._state.fields_cache["space"] = space
        membership.role_names = tuple(row[-1] or ())
        result.append(membership)
    return result
