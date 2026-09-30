"""Verify the exact production Python version set, not artifact byte hashes."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re

from packaging.requirements import InvalidRequirement, Requirement


def canonical_name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("Nombre de distribución inválido.")
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(text: str, *, constraints: bool) -> dict[str, str]:
    result = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement as exc:
            raise ValueError("Requisito Python inválido.") from exc
        specifications = list(requirement.specifier)
        allowed = {"=="} if constraints else {"==", "==="}
        if (requirement.url or requirement.marker or len(specifications) != 1
                or specifications[0].operator not in allowed
                or "*" in specifications[0].version
                or (constraints and requirement.extras)):
            raise ValueError("Se exige una versión exacta sin URL, marker ni wildcard.")
        name = canonical_name(requirement.name)
        if name in result:
            raise ValueError(f"Distribución duplicada: {name}")
        result[name] = specifications[0].version
    if not result:
        raise ValueError("Conjunto Python vacío.")
    return result


def version_set(rows) -> dict[str, str]:
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("version"), str) or not row["version"]:
            raise ValueError("Metadata de distribución inválida.")
        name = canonical_name(row.get("name"))
        if name in result:
            raise ValueError(f"Metadata duplicada: {name}")
        result[name] = row["version"]
    if not result:
        raise ValueError("Metadata Python vacía.")
    return result


def assert_equal(expected: dict[str, str], actual: dict[str, str]) -> None:
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = {name: {"expected": expected[name], "actual": actual[name]}
               for name in sorted(expected.keys() & actual.keys()) if expected[name] != actual[name]}
    if missing or extra or changed:
        raise ValueError(json.dumps({"missing": missing, "extra": extra, "changed": changed}, sort_keys=True))


def check_requirements(expected: dict[str, str], production_text: str) -> None:
    roots = parse_pins(production_text, constraints=False)
    for name, version in roots.items():
        if expected.get(name) != version:
            raise ValueError(f"Requisito raíz no congelado correctamente: {name}")


def _strict_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Clave JSON duplicada.")
        result[name] = value
    return result


def sbom_versions(path: Path) -> dict[str, str]:
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("SBOM demasiado grande.")
    def invalid_constant(_value):
        raise ValueError("Constante JSON inválida.")
    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_pairs,
                          parse_constant=invalid_constant)
    if not isinstance(document, dict):
        raise ValueError("SBOM debe ser un objeto.")
    sbom = document.get("sbom", document)
    if not isinstance(sbom, dict) or sbom.get("bomFormat") != "CycloneDX":
        raise ValueError("Se exige SBOM CycloneDX Python.")
    rows = sbom.get("components")
    if not isinstance(rows, list):
        raise ValueError("Falta lista de componentes.")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("purl"), str):
            raise ValueError("El conjunto contiene componentes no Python.")
        match = re.fullmatch(r"pkg:pypi/([A-Za-z0-9][A-Za-z0-9._-]*)@([^/@?#%\s]+)", row["purl"])
        if (match is None or canonical_name(match.group(1)) != canonical_name(row.get("name"))
                or match.group(2) != row.get("version")):
            raise ValueError("Identidad o versión PURL Python incoherente.")
    return version_set(rows)


def installed_versions() -> dict[str, str]:
    return version_set({"name": distribution.metadata["Name"], "version": distribution.version}
                       for distribution in metadata.distributions())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--constraints", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--installed", action="store_true")
    source.add_argument("--sbom", type=Path)
    parser.add_argument("--requirements", type=Path)
    args = parser.parse_args(argv)
    try:
        expected = parse_pins(args.constraints.read_text(encoding="utf-8"), constraints=True)
        if args.requirements:
            check_requirements(expected, args.requirements.read_text(encoding="utf-8").split("# Development", 1)[0])
        actual = installed_versions() if args.installed else sbom_versions(args.sbom)
        assert_equal(expected, actual)
        digest = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        print(json.dumps({"passed": True, "distributions": len(actual), "version_set_sha256": digest,
                          "byte_reproducibility_claimed": False, "os_packages_locked": False}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR Python version lock: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
