"""Contracts for production version pins and exact installed/SBOM sets."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.cuaderno.python_lock import (
    assert_equal, check_requirements, parse_pins, sbom_versions, version_set,
)


ROOT = Path(__file__).resolve().parents[2]


class PythonLockTests(unittest.TestCase):
    def test_constraints_require_unique_exact_base_names(self):
        self.assertEqual(parse_pins("PyJWT==2.15.0\n# comment\n", constraints=True), {"pyjwt": "2.15.0"})
        for text in ("", "pyjwt", "pyjwt>=2", "pyjwt==2.*", "pyjwt===2.15.0",
                     "pyjwt==2.15.0; python_version > '3'", "pyjwt[extra]==2.15.0",
                     "pyjwt @ https://synthetic.invalid/token.whl", "-e .",
                     "some_pkg==1.0\nsome-pkg==1.0"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_pins(text, constraints=True)

    def test_root_requirements_keep_extras_and_arbitrary_exact_pins(self):
        roots = "django-allauth[mfa,socialaccount]==65.18.0\ncryptography===50.0.1"
        pins = {"django-allauth": "65.18.0", "cryptography": "50.0.1"}
        self.assertEqual(parse_pins(roots, constraints=False), pins)
        check_requirements(pins, roots)
        for changed in ({}, {"django-allauth": "65.17.0", "cryptography": "50.0.1"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                check_requirements(changed, roots)

    def test_exact_runtime_set_rejects_missing_extra_changed_and_duplicate(self):
        expected = {"pyjwt": "2.15.0"}
        self.assertIsNone(assert_equal(expected, version_set([{"name": "PyJWT", "version": "2.15.0"}])))
        for actual in ({}, {"pyjwt": "2.14.0"}, {**expected, "other": "1.0"}):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                assert_equal(expected, actual)
        for rows in ([], [None], [{"name": "pyjwt", "version": None}],
                     [{"name": "unsafe/name", "version": "1.0"}],
                     [{"name": "Some_Pkg", "version": "1.0"}, {"name": "some-pkg", "version": "1.0"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                version_set(rows)

    def test_sbom_input_is_strict_and_python_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            row = {"name": "PyJWT", "version": "2.15.0", "purl": "pkg:pypi/pyjwt@2.15.0"}
            document = {"bomFormat": "CycloneDX", "components": [row]}
            for wrapped in (document, {"sbom": document}):
                path.write_text(json.dumps(wrapped), encoding="utf-8")
                self.assertEqual(sbom_versions(path), {"pyjwt": "2.15.0"})
            for invalid in ("[]", '{"sbom":NaN}', '{"sbom":{},"sbom":{}}',
                            json.dumps({"bomFormat": "CycloneDX", "components": [{**row, "purl": "pkg:npm/foo@1"}]}),
                            json.dumps({"bomFormat": "CycloneDX", "components": [row, row]})):
                path.write_text(invalid, encoding="utf-8")
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    sbom_versions(path)

    def test_checkout_production_roots_and_native_extras_match_153_pins(self):
        text = (ROOT / "tooling/cuaderno/python-production.constraints.txt").read_text(encoding="utf-8")
        pins = parse_pins(text, constraints=True)
        self.assertEqual(len(pins), 153)
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").split("# Development", 1)[0]
        self.assertIn("django-allauth[mfa,socialaccount]==65.18.0", requirements)
        check_requirements(pins, requirements)
        self.assertEqual({name: pins[name] for name in ("pip", "setuptools", "wheel", "setuptools-rust")}, {
            "pip": "26.2.1", "setuptools": "84.0.0", "wheel": "0.46.2", "setuptools-rust": "1.10.2",
        })

    def test_sbom_purl_must_match_component_identity_and_version(self):
        row = {"name": "PyJWT", "version": "2.15.0", "purl": "pkg:pypi/pyjwt@2.15.0"}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            for purl in ("pkg:pypi/other@2.15.0", "pkg:pypi/pyjwt@2.14.0",
                         "pkg:pypi/pyjwt@2.15.0?extra=value", "pkg:pypi/pyjwt@2.15.0#subpath",
                         "pkg:pypi/namespace/pyjwt@2.15.0", "pkg:pypi/pyjwt"):
                path.write_text(json.dumps({"bomFormat": "CycloneDX", "components": [{**row, "purl": purl}]}), encoding="utf-8")
                with self.subTest(purl=purl), self.assertRaises(ValueError):
                    sbom_versions(path)

    def test_release_build_applies_constraints_to_all_installs_and_verifies_set(self):
        dockerfile = (ROOT / "deploy/cuaderno/Dockerfile").read_text(encoding="utf-8")
        installs = [line for line in dockerfile.splitlines() if "pip install" in line]
        self.assertEqual(len(installs), 2)
        for line in installs:
            self.assertIn("-c /tmp/production.constraints.txt", line)
        self.assertIn("--requirements /tmp/production-requirements.txt --installed", dockerfile)
        self.assertIn("./PYTHON-PRODUCTION.constraints.txt", dockerfile)
        self.assertIn("!scripts/cuaderno/python_lock.py", (ROOT / "deploy/cuaderno/Dockerfile.dockerignore").read_text())


if __name__ == "__main__":
    unittest.main()
