"""Sub-recipe cycles and consolidated needs. Planning does not touch stock."""

from __future__ import annotations

from decimal import Decimal

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal


def find_cycle(start: str, edges: dict[str, list[str]]) -> list[str] | None:
    path: list[str] = []
    seen: set[str] = set()

    def walk(node: str) -> list[str] | None:
        if node in path:
            return path[path.index(node):] + [node]
        if node in seen:
            return None
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
    for component_id, quantity in usages:
        amount = parse_decimal(quantity, allow_zero=True)
        totals[component_id] = totals.get(component_id, Decimal("0")) + amount
    return totals


def scale_covers(base_covers, extra, cancelled) -> Decimal:
    base = parse_decimal(base_covers, allow_zero=True)
    added = parse_decimal(extra, allow_zero=True)
    removed = parse_decimal(cancelled, allow_zero=True)
    result = base + added - removed
    if result < 0:
        raise DomainError("invalid_covers", "Los comensales no pueden quedar en negativo.")
    return result
