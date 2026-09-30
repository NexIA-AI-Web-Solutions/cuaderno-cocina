"""Pure validation of native PK precedence for portable conversions."""

from __future__ import annotations

from collections.abc import Mapping

from cuaderno.domain.errors import DomainError


_MAX_CONVERSIONS = 10_000
_MESSAGE = "No se puede conservar la prioridad de las conversiones en el espacio de destino."


def _conflict() -> DomainError:
    return DomainError("conversion_precedence", _MESSAGE)


def _actual_order(ref, document_index, resolved_conversions):
    if ref not in resolved_conversions:
        raise _conflict()
    conversion = resolved_conversions[ref]
    if conversion is None:
        # Imported rows are inserted in document order after every mapped row.
        return (1, document_index)
    pk = getattr(conversion, "pk", None)
    if isinstance(pk, bool) or not isinstance(pk, int) or pk <= 0:
        raise _conflict()
    return (0, pk)


def _validate_effective_graph(edges, resolved_conversions):
    """Check only components where traversal has more than one possible path."""
    parent = {}

    def find(node):
        root = parent.setdefault(node, node)
        while root != parent[root]:
            root = parent[root]
        while node != root:
            next_node = parent[node]
            parent[node] = root
            node = next_node
        return root

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    effective = []
    for edge in edges:
        _, _, base_ref, converted_ref = edge
        if base_ref == converted_ref:
            continue
        union(base_ref, converted_ref)
        effective.append(edge)

    component_edges = {}
    component_vertices = {}
    for edge in effective:
        _, _, base_ref, converted_ref = edge
        root = find(base_ref)
        component_edges.setdefault(root, []).append(edge)
        component_vertices.setdefault(root, set()).update((base_ref, converted_ref))

    for root, rows in component_edges.items():
        # In an undirected multigraph E >= V means a cycle. Parallel and
        # inverse rows are therefore detected without inspecting ratios.
        if len(rows) < len(component_vertices[root]):
            continue
        previous = None
        for document_index, ref, _, _ in rows:
            current = _actual_order(ref, document_index, resolved_conversions)
            if previous is not None and current <= previous:
                raise _conflict()
            previous = current


def validate_conversion_precedence(catalog_conversions, resolved_conversions):
    """Reject imports whose target PK order would alter ambiguous BFS paths.

    Global conversions compete with each other and with conversions for each
    individual food. Conversions for two different foods never share a graph.
    Self edges cannot discover another unit, so their relative order is inert.
    """
    if not isinstance(catalog_conversions, Mapping) or not isinstance(resolved_conversions, Mapping):
        raise _conflict()
    if len(catalog_conversions) > _MAX_CONVERSIONS:
        raise _conflict()

    global_edges = []
    food_edges = {}
    for document_index, (ref, item) in enumerate(catalog_conversions.items()):
        if not isinstance(ref, str) or not isinstance(item, Mapping):
            raise _conflict()
        base_ref = item.get("base_unit_ref")
        converted_ref = item.get("converted_unit_ref")
        if not isinstance(base_ref, str) or not isinstance(converted_ref, str):
            raise _conflict()
        edge = (document_index, ref, base_ref, converted_ref)
        food_ref = item.get("food_ref")
        if food_ref is None:
            global_edges.append(edge)
        elif isinstance(food_ref, str):
            food_edges.setdefault(food_ref, []).append(edge)
        else:
            raise _conflict()

    _validate_effective_graph(global_edges, resolved_conversions)
    for specific_edges in food_edges.values():
        # Both lists retain document indices; sorting reconstructs the exact
        # source order after combining global and food-specific rows.
        effective = sorted((*global_edges, *specific_edges), key=lambda edge: edge[0])
        _validate_effective_graph(effective, resolved_conversions)
    return None


def validate_destination_conversion_graph(
    catalog_conversions,
    resolved_conversions,
    resolved_units,
    resolved_foods,
    destination_rows,
):
    """Reject source-reachable ambiguity introduced by unmapped native rows.

    The API supplies one already-scoped snapshot of destination rows. This
    function intentionally performs no ORM access and never compares labels.
    """
    if not catalog_conversions:
        # Older documents omitted the conversion graph, so there is no source
        # topology against which destination completeness can be guaranteed.
        return None
    if not all(
        isinstance(value, Mapping)
        for value in (catalog_conversions, resolved_conversions, resolved_units, resolved_foods)
    ):
        raise _conflict()
    if len(catalog_conversions) > _MAX_CONVERSIONS:
        raise _conflict()

    def native_pk(value):
        pk = getattr(value, "pk", None)
        if isinstance(pk, bool) or not isinstance(pk, int) or pk <= 0:
            raise _conflict()
        return pk

    def unit_vertex(ref):
        if ref not in resolved_units:
            raise _conflict()
        unit = resolved_units[ref]
        return ("source-unit", ref) if unit is None else ("native-unit", native_pk(unit))

    represented_ids = set()
    for ref in catalog_conversions:
        if ref not in resolved_conversions:
            raise _conflict()
        conversion = resolved_conversions[ref]
        if conversion is not None:
            represented_ids.add(native_pk(conversion))

    source_global = []
    source_by_food = {}
    mapped_food_ids = {}
    for food_ref, food in resolved_foods.items():
        if not isinstance(food_ref, str):
            raise _conflict()
        mapped_food_ids[food_ref] = None if food is None else native_pk(food)
    for ref, item in catalog_conversions.items():
        if not isinstance(ref, str) or not isinstance(item, Mapping):
            raise _conflict()
        base = unit_vertex(item.get("base_unit_ref"))
        converted = unit_vertex(item.get("converted_unit_ref"))
        food_ref = item.get("food_ref")
        edge = (base, converted)
        if food_ref is None:
            source_global.append(edge)
            continue
        if not isinstance(food_ref, str) or food_ref not in resolved_foods:
            raise _conflict()
        source_by_food.setdefault(food_ref, []).append(edge)

    if isinstance(destination_rows, (str, bytes)):
        raise _conflict()
    try:
        rows = list(destination_rows)
    except TypeError as exc:
        raise _conflict() from exc
    if len(rows) > _MAX_CONVERSIONS:
        raise _conflict()

    extra_global = []
    extra_by_food = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise _conflict()
        row_id = row.get("id")
        if isinstance(row_id, bool) or not isinstance(row_id, int) or row_id <= 0:
            raise _conflict()
        if row_id in represented_ids:
            continue
        base_id = row.get("base_unit_id")
        converted_id = row.get("converted_unit_id")
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (base_id, converted_id)):
            raise _conflict()
        food_id = row.get("food_id")
        if food_id is not None and (isinstance(food_id, bool) or not isinstance(food_id, int) or food_id <= 0):
            raise _conflict()
        edge = (("native-unit", base_id), ("native-unit", converted_id))
        if food_id is None:
            extra_global.append(edge)
        else:
            extra_by_food.setdefault(food_id, []).append(edge)

    _reject_extra_cycles_reaching_source(source_global, extra_global)
    for food_ref, food_id in mapped_food_ids.items():
        specific_source = source_by_food.get(food_ref, ())
        specific_extra = extra_by_food.get(food_id, ()) if food_id is not None else ()
        _reject_extra_cycles_reaching_source(
            (*source_global, *specific_source),
            (*extra_global, *specific_extra),
        )
    return None


def _reject_extra_cycles_reaching_source(source_edges, extra_edges):
    """Union-find marks cycles closed by extras and propagates reachability."""
    parent = {}
    has_source = {}
    extra_cycle = {}

    def find(node):
        root = parent.setdefault(node, node)
        has_source.setdefault(root, False)
        extra_cycle.setdefault(root, False)
        while root != parent[root]:
            root = parent[root]
        while node != root:
            next_node = parent[node]
            parent[node] = root
            node = next_node
        return root

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return left_root, False
        parent[right_root] = left_root
        has_source[left_root] = has_source[left_root] or has_source[right_root]
        extra_cycle[left_root] = extra_cycle[left_root] or extra_cycle[right_root]
        return left_root, True

    for left, right in source_edges:
        if left == right:
            continue
        root, _ = union(left, right)
        has_source[root] = True

    for left, right in extra_edges:
        if left == right:
            continue
        root, merged = union(left, right)
        if not merged:
            extra_cycle[root] = True

    roots = {find(node) for node in parent}
    if any(has_source[root] and extra_cycle[root] for root in roots):
        raise _conflict()
