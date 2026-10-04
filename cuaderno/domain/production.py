"""Sub-recipe cycles and consolidated needs. Planning does not touch stock."""

from __future__ import annotations

from decimal import Decimal, localcontext

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal


def find_cycle(start: str, edges: dict[str, list[str]]) -> list[str] | None:
    if not isinstance(start, str) or not start or len(start) > 256 or not isinstance(edges, dict) or len(edges) > 1001:
        raise DomainError("invalid_graph", "El grafo debe tener identificadores de texto y como máximo 1001 nodos.")
    nodes = {start}
    edge_count = 0
    for node, children in edges.items():
        if not isinstance(node, str) or not node or len(node) > 256 or not isinstance(children, list):
            raise DomainError("invalid_graph", "Cada nodo debe contener una lista de identificadores de texto.")
        edge_count += len(children)
        if edge_count > 10000:
            raise DomainError("graph_limit", "El grafo supera el límite de 10000 referencias.")
        for child in children:
            if not isinstance(child, str) or not child or len(child) > 256:
                raise DomainError("invalid_graph", "Las referencias deben ser identificadores de texto válidos.")
        nodes.add(node)
        nodes.update(children)
    if len(nodes) > 1001:
        raise DomainError("graph_limit", "El grafo supera el límite de 1001 nodos.")
    path: list[str] = []
    seen: set[str] = set()

    def walk(node: str) -> list[str] | None:
        if node in path:
            return path[path.index(node):] + [node]
        if node in seen:
            return None
        if len(path) >= 64:
            raise DomainError("graph_depth", "El grafo supera la profundidad máxima de 64 niveles.")
        path.append(node)
        for child in edges.get(node, []):
            found = walk(child)
            if found:
                return found
        path.pop()
        seen.add(node)
        return None

    return walk(start)


def assert_no_cycle(start: str, edges: dict[str, list[str]]) -> None:
    cycle = find_cycle(start, edges)
    if cycle:
        route = " → ".join(cycle)
        raise DomainError("recipe_cycle", f"Referencia circular: {route}")


def consolidate(usages: list[tuple[str, str]]) -> dict[str, Decimal]:
    """Sum the same component once. `usages` is (component_id, quantity)."""
    totals: dict[str, Decimal] = {}
    with localcontext() as context:
        context.prec = 64
        for component_id, quantity in usages:
            amount = parse_decimal(quantity, allow_zero=True)
            totals[component_id] = totals.get(component_id, Decimal("0")) + amount
    return totals


def scale_covers(base_covers, extra, cancelled) -> Decimal:
    base = parse_decimal(base_covers, allow_zero=True)
    added = parse_decimal(extra, allow_zero=True)
    removed = parse_decimal(cancelled, allow_zero=True)
    with localcontext() as context:
        context.prec = 64
        result = base + added - removed
    if result < 0:
        raise DomainError("invalid_covers", "Los comensales no pueden quedar en negativo.")
    return result
