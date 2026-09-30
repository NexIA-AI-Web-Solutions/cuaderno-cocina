#!/usr/bin/env python3
"""Validate a CycloneDX 1.6 SBOM against commit-pinned official schemas."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import BinaryIO

from jsonschema import FormatChecker
from jsonschema.validators import validator_for
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource


SCHEMA_COMMIT = "8a27bfd1be5be0dcb2c208a34d2f4fa0b6d75bd7"
SCHEMA_NAMES = (
    "bom-1.6.schema.json",
    "spdx.schema.json",
    "jsf-0.82.schema.json",
)
SCHEMA_BASE_URL = (
    "https://raw.githubusercontent.com/CycloneDX/specification/"
    f"{SCHEMA_COMMIT}/schema/"
)
SCHEMA_URLS = {name: f"{SCHEMA_BASE_URL}{name}" for name in SCHEMA_NAMES}
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
NETWORK_TIMEOUT_SECONDS = 10


class SbomValidationFailure(Exception):
    """A bounded, user-facing validation failure."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _request, _file_pointer, _code, _message, _headers, _new_url):
        return None


def _default_opener():
    return urllib.request.build_opener(_NoRedirect())


def _bounded_read(stream: BinaryIO, *, label: str) -> bytes:
    payload = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise SbomValidationFailure(f"{label} supera el límite de 2 MiB.")
    return payload


def _decode_json(raw: bytes, *, error_message: str):
    def reject_constant(token: str):
        raise ValueError(f"Constante numérica no JSON: {token}")

    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise SbomValidationFailure(error_message) from error


def fetch_schema(url: str, *, opener=None) -> tuple[dict, str]:
    if url not in SCHEMA_URLS.values():
        raise SbomValidationFailure("URL de esquema fuera del pin permitido.")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/schema+json, application/json",
            "User-Agent": "cuaderno-cocina-sbom-validator/1",
        },
        method="GET",
    )
    try:
        with (opener or _default_opener()).open(
            request,
            timeout=NETWORK_TIMEOUT_SECONDS,
        ) as response:
            if response.geturl() != url:
                raise SbomValidationFailure("El esquema respondió desde una URL no autorizada.")
            if getattr(response, "status", None) != 200:
                raise SbomValidationFailure("La descarga del esquema no devolvió HTTP 200.")
            raw_length = response.headers.get("Content-Length")
            if raw_length is not None:
                try:
                    declared_length = int(raw_length)
                except (TypeError, ValueError) as error:
                    raise SbomValidationFailure("Content-Length de esquema inválido.") from error
                if declared_length < 0 or declared_length > MAX_DOCUMENT_BYTES:
                    raise SbomValidationFailure("El esquema supera el límite de 2 MiB.")
            raw = _bounded_read(response, label="El esquema")
    except SbomValidationFailure:
        raise
    except (OSError, urllib.error.URLError) as error:
        raise SbomValidationFailure("No se pudo descargar un esquema fijado.") from error

    schema = _decode_json(raw, error_message="El esquema fijado no es JSON UTF-8 válido.")
    if not isinstance(schema, dict):
        raise SbomValidationFailure("El esquema fijado no es un objeto JSON.")
    return schema, hashlib.sha256(raw).hexdigest()


def fetch_schemas(*, opener=None) -> tuple[dict[str, dict], dict[str, str]]:
    schemas = {}
    hashes = {}
    for name, url in SCHEMA_URLS.items():
        schema, digest = fetch_schema(url, opener=opener)
        schemas[name] = schema
        hashes[name] = digest
    return schemas, hashes


def read_sbom(stream: BinaryIO) -> dict:
    raw = _bounded_read(stream, label="El SBOM")
    document = _decode_json(raw, error_message="La entrada no es JSON UTF-8 válido.")
    if not isinstance(document, dict):
        raise SbomValidationFailure("El SBOM debe ser un objeto JSON.")
    return document


def _closed_registry(schemas: Mapping[str, dict]) -> Registry:
    def reject_remote(uri: str):
        raise NoSuchResource(ref=uri)

    registry = Registry(retrieve=reject_remote)
    aliases: dict[str, Resource] = {}
    for name in SCHEMA_NAMES:
        schema = schemas.get(name)
        if not isinstance(schema, dict):
            raise SbomValidationFailure(f"Falta el esquema fijado {name}.")
        try:
            resource = Resource.from_contents(schema)
        except Exception as error:
            raise SbomValidationFailure(f"No se reconoce la especificación de {name}.") from error
        identifiers = [SCHEMA_URLS[name]]
        schema_id = schema.get("$id")
        if isinstance(schema_id, str) and schema_id:
            identifiers.append(schema_id)
        for identifier in identifiers:
            previous = aliases.get(identifier)
            if previous is not None and previous is not resource:
                raise SbomValidationFailure("Dos esquemas declaran el mismo identificador.")
            aliases[identifier] = resource
    for identifier, resource in aliases.items():
        registry = registry.with_resource(identifier, resource)
    return registry


def validate_document(
    document: dict,
    schemas: Mapping[str, dict],
    schema_hashes: Mapping[str, str],
) -> dict:
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != "1.6":
        raise SbomValidationFailure("La entrada no declara CycloneDX 1.6.")
    if set(schema_hashes) != set(SCHEMA_NAMES):
        raise SbomValidationFailure("No están disponibles todos los hashes de esquema.")

    registry = _closed_registry(schemas)
    try:
        for name in SCHEMA_NAMES:
            schema_validator = validator_for(schemas[name])
            schema_validator.check_schema(schemas[name])
        bom_schema = schemas["bom-1.6.schema.json"]
        validator_class = validator_for(bom_schema)
        validator = validator_class(
            bom_schema,
            registry=registry,
            format_checker=FormatChecker(),
        )
        errors = list(validator.iter_errors(document))
    except Exception as error:
        raise SbomValidationFailure("La validación cerrada de esquemas no pudo completarse.") from error
    if errors:
        first = min(errors, key=lambda error: tuple(str(part) for part in error.absolute_path))
        path = "/".join(str(part) for part in first.absolute_path) or "$"
        raise SbomValidationFailure(
            f"El SBOM no cumple el esquema en {path} ({first.validator or 'referencia'})."
        )

    canonical = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    components = document.get("components")
    return {
        "status": "valid",
        "format": "CycloneDX",
        "spec_version": "1.6",
        "components": len(components) if isinstance(components, list) else 0,
        "schema_commit": SCHEMA_COMMIT,
        "schema_sha256": {name: schema_hashes[name] for name in SCHEMA_NAMES},
        "sbom_canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "validator": f"jsonschema {importlib.metadata.version('jsonschema')}",
    }


def main() -> int:
    if len(sys.argv) != 1:
        raise SbomValidationFailure("Este comando no acepta argumentos ni rutas.")
    document = read_sbom(sys.stdin.buffer)
    schemas, hashes = fetch_schemas()
    report = validate_document(document, schemas, hashes)
    sys.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SbomValidationFailure as error:
        sys.stderr.write(f"CUADERNO_SBOM_INVALID: {error}\n")
        raise SystemExit(1) from None
