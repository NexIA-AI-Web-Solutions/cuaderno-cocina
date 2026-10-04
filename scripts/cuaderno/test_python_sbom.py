"""Tests for deterministic offline Python SBOM generation."""
from __future__ import annotations

from email.message import Message
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import python_sbom as subject
else:
    import python_sbom as subject


SOURCE = "a" * 40 + "+worktree." + "b" * 64
CONSTRAINTS = b"Demo_Pkg==1.2.3\nsecond.pkg==2.0+local\n"


class Distribution:
    def __init__(self, name, version, *, expression=None, license_value=None, classifiers=()):
        self.version = version
        self.metadata = Message()
        self.metadata["Name"] = name
        if expression:
            self.metadata["License-Expression"] = expression
        if license_value:
            self.metadata["License"] = license_value
        for classifier in classifiers:
            self.metadata["Classifier"] = classifier


def distributions():
    return [
        Distribution("second.pkg", "2.0+local", license_value="UNKNOWN"),
        Distribution("Demo_Pkg", "1.2.3", expression="MIT", classifiers=(
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: MIT License",
        )),
    ]


class PythonSbomTests(unittest.TestCase):
    def test_generates_normalized_deterministic_cyclonedx_with_provenance(self):
        first = subject.build_sbom(distributions(), constraints=CONSTRAINTS, source_identity=SOURCE)
        second = subject.build_sbom(reversed(distributions()), constraints=CONSTRAINTS, source_identity=SOURCE)
        self.assertEqual(first, second)
        self.assertEqual(first["bomFormat"], "CycloneDX")
        self.assertEqual([row["name"] for row in first["components"]], ["demo-pkg", "second-pkg"])
        self.assertEqual(first["components"][0]["purl"], "pkg:pypi/demo-pkg@1.2.3")
        self.assertEqual(first["components"][1]["purl"], "pkg:pypi/second-pkg@2.0%2Blocal")
        self.assertEqual(first["components"][0]["licenses"], [
            {"license": {"name": "MIT"}},
            {"license": {"name": "OSI Approved :: MIT License"}},
        ])
        properties = {row["name"]: row["value"] for row in first["metadata"]["properties"]}
        self.assertEqual(properties["cuaderno:constraints_sha256"], hashlib.sha256(CONSTRAINTS).hexdigest())
        self.assertEqual(properties["cuaderno:source_identity"], SOURCE)
        self.assertEqual(properties["cuaderno:advisory_status"], "not-scanned-offline-inventory")

    def test_rejects_set_drift_duplicates_and_invalid_identity(self):
        with self.assertRaises(ValueError):
            subject.build_sbom(distributions()[:1], constraints=CONSTRAINTS, source_identity=SOURCE)
        duplicate = [*distributions(), Distribution("demo-pkg", "1.2.3")]
        with self.assertRaises(ValueError):
            subject.build_sbom(duplicate, constraints=CONSTRAINTS, source_identity=SOURCE)
        with self.assertRaises(ValueError):
            subject.build_sbom(distributions(), constraints=CONSTRAINTS, source_identity="worktree")

    def test_cli_writes_new_file_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            constraints = root / "constraints.txt"
            output = root / "SBOM.python.cdx.json"
            constraints.write_bytes(CONSTRAINTS)
            with patch.object(subject.metadata, "distributions", return_value=distributions()):
                self.assertEqual(subject.main([
                    "--constraints", str(constraints), "--source-identity", SOURCE,
                    "--output", str(output),
                ]), 0)
                document = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(len(document["components"]), 2)
                self.assertEqual(subject.main([
                    "--constraints", str(constraints), "--source-identity", SOURCE,
                    "--output", str(output),
                ]), 1)


if __name__ == "__main__":
    unittest.main()
