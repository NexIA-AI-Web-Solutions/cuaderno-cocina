from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

if __package__:
    from . import typecheck_gate as subject
else:
    import typecheck_gate as subject


class Runner:
    def __init__(self, output, *, status=1, node="v24.1.0"):
        self.output = output
        self.status = status
        self.node = node

    def __call__(self, argv, **_kwargs):
        if argv == ["node", "--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout=self.node + "\n", stderr="")
        return subprocess.CompletedProcess(argv, self.status, stdout=self.output, stderr="")


class TypecheckGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for package, version in (("vue-tsc", "3.3.5"), ("typescript", "5.9.3")):
            directory = self.root / "vue3/node_modules" / package
            directory.mkdir(parents=True)
            (directory / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")

    def test_accepts_explicit_inherited_baseline_and_records_toolchain(self):
        output = "src/legacy.ts(1,2): error TS1234: inherited\n" * 2
        result = subject.check(root=self.root, max_inherited=2, runner=Runner(output))
        self.assertTrue(result["passed"])
        self.assertEqual(result["diagnostics_inherited"], 2)
        self.assertEqual(result["vue_tsc"], "3.3.5")
        self.assertEqual(result["typescript"], "5.9.3")

    def test_default_release_gate_rejects_any_diagnostic(self):
        with self.assertRaises(subject.TypecheckGateFailure):
            subject.check(root=self.root, runner=Runner("src/legacy.ts(1,2): error TS1234: inherited\n"))

    def test_rejects_cuaderno_diagnostic_baseline_growth_and_environment_errors(self):
        with self.assertRaises(subject.TypecheckGateFailure):
            subject.check(root=self.root, runner=Runner("src/cuaderno/file.ts(1,2): error TS1: own\n"))
        with self.assertRaises(subject.TypecheckGateFailure):
            subject.check(root=self.root, max_inherited=0, runner=Runner("src/legacy.ts(1,2): error TS1: inherited\n"))
        with self.assertRaises(subject.TypecheckGateFailure):
            subject.check(root=self.root, runner=Runner("tool crashed", status=2))
        with self.assertRaises(subject.TypecheckGateFailure):
            subject.check(root=self.root, runner=Runner("", status=0, node="v25.8.1"))


if __name__ == "__main__":
    unittest.main()
