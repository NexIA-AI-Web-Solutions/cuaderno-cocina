#!/usr/bin/env python3
"""Generate a deterministic offline CycloneDX inventory from installed Python metadata."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

try:
    from .python_lock import assert_equal, canonical_name, parse_pins
except ImportError:
    from python_lock import assert_equal, canonical_name, parse_pins


SOURCE_RE = re.compile(r"^[0-9a-f]{40}(?:\+worktree\.[0-9a-f]{64})?$")


def _declared_licenses(fields) -> list[str]:
    values = []
    expression = fields.get("License-Expression")
    if isinstance(expression, str) and expression.strip():
        values.append(expression.strip())
    license_field = fields.get("License")
    if isinstance(license_field, str) and license_field.strip() and license_field.strip().upper() != "UNKNOWN":
        values.append(license_field.strip())
    for classifier in fields.get_all("Classifier", []):
        prefix = "License :: "
        if classifier.startswith(prefix):
            values.append(classifier[len(prefix):].strip())
    return sorted(set(filter(None, values)))


def _component(distribution) -> dict:
    fields = distribution.metadata
    name = canonical_name(fields.get("Name"))
    version = distribution.version
    if not isinstance(version, str) or not version:
        raise ValueError("Distribución Python sin versión.")
    licenses = _declared_licenses(fields)
    component = {
        "type": "library",
        "name": name,
        "version": version,
        "purl": f"pkg:pypi/{quote(name, safe='.-_')}@{quote(version, safe='.-_')}",
        "properties": [{
            "name": "cuaderno:declared_licenses",
            "value": json.dumps(licenses, ensure_ascii=False, separators=(",", ":")),
        }],
    }
    if licenses:
        component["licenses"] = [{"license": {"name": value}} for value in licenses]
    return component


def build_sbom(distributions, *, constraints: bytes, source_identity: str) -> dict:
    if SOURCE_RE.fullmatch(source_identity or "") is None:
        raise ValueError("Identidad de fuente inválida.")
    try:
        constraint_text = constraints.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Constraints no es UTF-8.") from exc
    expected = parse_pins(constraint_text, constraints=True)
    components = [_component(item) for item in distributions]
    actual = {component["name"]: component["version"] for component in components}
    if len(actual) != len(components):
        raise ValueError("Metadata Python duplicada tras normalizar nombres.")
    assert_equal(expected, actual)
    components.sort(key=lambda row: (row["name"], row["version"]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "cuaderno-cocina-python-runtime",
                "version": source_identity,
            },
            "properties": [
                {"name": "cuaderno:constraints_sha256", "value": hashlib.sha256(constraints).hexdigest()},
                {"name": "cuaderno:source_identity", "value": source_identity},
                {"name": "cuaderno:scope", "value": "installed-python-distributions"},
                {"name": "cuaderno:advisory_status", "value": "not-scanned-offline-inventory"},
            ],
        },
        "components": components,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--constraints", required=True, type=Path)
    parser.add_argument("--source-identity", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = build_sbom(
            metadata.distributions(), constraints=args.constraints.read_bytes(),
            source_identity=args.source_identity,
        )
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("El SBOM destino ya existe; no se sobrescribe.")
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR Python SBOM: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
