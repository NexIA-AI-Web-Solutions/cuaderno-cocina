import hashlib
import io
import json
import unittest

if __package__:
    from . import validate_sbom
else:
    import validate_sbom


def _schemas():
    spdx = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "http://cyclonedx.org/schema/spdx.schema.json",
        "definitions": {
            "licenseChoice": {
                "type": "object",
                "required": ["license"],
                "properties": {
                    "license": {
                        "type": "object",
                        "minProperties": 1,
                        "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                    }
                },
            }
        },
    }
    jsf = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "http://cyclonedx.org/schema/jsf-0.82.schema.json",
        "definitions": {
            "property": {
                "type": "object",
                "required": ["name", "value"],
                "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                "additionalProperties": False,
            }
        },
    }
    bom = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "type": "object",
        "required": ["bomFormat", "specVersion", "version", "components"],
        "properties": {
            "bomFormat": {"const": "CycloneDX"},
            "specVersion": {"const": "1.6"},
            "version": {"type": "integer", "minimum": 1},
            "components": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["type", "name", "version", "purl", "licenses", "properties"],
                    "properties": {
                        "type": {"const": "library"},
                        "name": {"type": "string"},
                        "version": {"type": "string"},
                        "purl": {"type": "string"},
                        "licenses": {
                            "type": "array",
                            "items": {"$ref": "spdx.schema.json#/definitions/licenseChoice"},
                        },
                        "properties": {
                            "type": "array",
                            "items": {"$ref": "jsf-0.82.schema.json#/definitions/property"},
                        },
                    },
                },
            },
        },
    }
    return {
        "bom-1.6.schema.json": bom,
        "spdx.schema.json": spdx,
        "jsf-0.82.schema.json": jsf,
    }


def _valid_sbom():
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "@scope/raw-license",
                "version": "1.0.0+build",
                "purl": "pkg:npm/%40scope/raw-license@1.0.0%2Bbuild",
                "licenses": [{"license": {"name": "SEE LICENSE IN LICENSE.txt"}}],
                "properties": [{"name": "cuaderno:package_json_sha256", "value": "a" * 64}],
            }
        ],
    }


class FakeResponse:
    def __init__(self, payload, url, *, status=200, declared_length=None):
        self._stream = io.BytesIO(payload)
        self._url = url
        self.status = status
        length = len(payload) if declared_length is None else declared_length
        self.headers = {"Content-Length": str(length)}

    def read(self, size=-1):
        return self._stream.read(size)

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeOpener:
    def __init__(self, payloads, *, final_url=None):
        self.payloads = payloads
        self.final_url = final_url
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        return FakeResponse(
            self.payloads[request.full_url],
            self.final_url or request.full_url,
        )


class ValidateSbomTests(unittest.TestCase):
    def test_fetches_only_three_https_schemas_at_the_commit_pin(self):
        payloads = {
            url: json.dumps(_schemas()[name]).encode()
            for name, url in validate_sbom.SCHEMA_URLS.items()
        }
        opener = FakeOpener(payloads)

        loaded, hashes = validate_sbom.fetch_schemas(opener=opener)

        self.assertEqual(set(loaded), set(validate_sbom.SCHEMA_NAMES))
        self.assertEqual(set(hashes), set(validate_sbom.SCHEMA_NAMES))
        self.assertEqual([call[0] for call in opener.calls], list(validate_sbom.SCHEMA_URLS.values()))
        self.assertTrue(all(url.startswith("https://raw.githubusercontent.com/CycloneDX/specification/") for url in payloads))
        self.assertTrue(all(validate_sbom.SCHEMA_COMMIT in url for url in payloads))
        self.assertTrue(all(timeout == validate_sbom.NETWORK_TIMEOUT_SECONDS for _, timeout in opener.calls))

    def test_rejects_redirected_identity_even_when_response_has_schema_json(self):
        url = next(iter(validate_sbom.SCHEMA_URLS.values()))
        opener = FakeOpener({url: b"{}"}, final_url="https://example.invalid/schema.json")
        with self.assertRaises(validate_sbom.SbomValidationFailure):
            validate_sbom.fetch_schema(url, opener=opener)

    def test_bounds_schema_download_using_header_and_actual_bytes(self):
        url = next(iter(validate_sbom.SCHEMA_URLS.values()))
        oversized = b" " * (validate_sbom.MAX_DOCUMENT_BYTES + 1)
        for response in (
            FakeResponse(b"{}", url, declared_length=validate_sbom.MAX_DOCUMENT_BYTES + 1),
            FakeResponse(oversized, url, declared_length=1),
        ):
            class OneResponseOpener:
                def open(self, _request, timeout):
                    self.timeout = timeout
                    return response

            with self.assertRaises(validate_sbom.SbomValidationFailure):
                validate_sbom.fetch_schema(url, opener=OneResponseOpener())

    def test_validates_scoped_component_and_raw_declared_license(self):
        schemas = _schemas()
        hashes = {
            name: hashlib.sha256(json.dumps(schema).encode()).hexdigest()
            for name, schema in schemas.items()
        }

        report = validate_sbom.validate_document(_valid_sbom(), schemas, hashes)

        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["components"], 1)
        self.assertEqual(report["schema_commit"], validate_sbom.SCHEMA_COMMIT)
        self.assertEqual(report["schema_sha256"], hashes)
        self.assertEqual(len(report["sbom_canonical_sha256"]), 64)
        self.assertIn("jsonschema", report["validator"])

    def test_rejects_wrong_cyclonedx_identity_and_invalid_shape(self):
        schemas = _schemas()
        hashes = {name: "0" * 64 for name in schemas}
        for mutation in (
            {"specVersion": "1.5"},
            {"bomFormat": "NotCycloneDX"},
            {"components": "one"},
        ):
            document = _valid_sbom()
            document.update(mutation)
            with self.assertRaises(validate_sbom.SbomValidationFailure):
                validate_sbom.validate_document(document, schemas, hashes)

    def test_rejects_malformed_or_oversized_stdin_json(self):
        for payload in (b"{", b"[]", b" " * (validate_sbom.MAX_DOCUMENT_BYTES + 1)):
            with self.assertRaises(validate_sbom.SbomValidationFailure):
                validate_sbom.read_sbom(io.BytesIO(payload))

    def test_rejects_non_json_numeric_constants_in_sbom_and_schema(self):
        sbom = json.dumps(_valid_sbom()).encode()
        sbom = sbom[:-1] + b', "probe": NaN}'
        with self.assertRaises(validate_sbom.SbomValidationFailure):
            validate_sbom.read_sbom(io.BytesIO(sbom))

        url = next(iter(validate_sbom.SCHEMA_URLS.values()))
        for token in (b"NaN", b"Infinity", b"-Infinity"):
            payload = b'{"type":"object","probe":' + token + b"}"
            opener = FakeOpener({url: payload})
            with self.assertRaises(validate_sbom.SbomValidationFailure):
                validate_sbom.fetch_schema(url, opener=opener)

    def test_external_schema_reference_fails_closed_without_retrieval(self):
        schemas = _schemas()
        schemas["bom-1.6.schema.json"] = {
            **schemas["bom-1.6.schema.json"],
            "properties": {"components": {"$ref": "https://example.invalid/untrusted.json"}},
        }
        hashes = {name: "0" * 64 for name in schemas}

        with self.assertRaises(validate_sbom.SbomValidationFailure):
            validate_sbom.validate_document(_valid_sbom(), schemas, hashes)


if __name__ == "__main__":
    unittest.main()
