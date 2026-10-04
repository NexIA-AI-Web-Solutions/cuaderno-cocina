"""Tests for exact frontend bundle/provenance reconciliation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import frontend_assets as subject
else:
    import frontend_assets as subject


class FrontendAssetsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "assets").mkdir()
        (self.root / "index.html").write_bytes(b"<main>Cuaderno</main>\n")
        (self.root / "assets/app.js").write_bytes(b"export const ready = true\n")
        self.report = self.root / subject.REPORT_NAME
        self.write_report()

    def rows(self):
        return [
            {"file_name": path.relative_to(self.root).as_posix(), "bytes": len(path.read_bytes()),
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(self.root.rglob("*"))
            if path.is_file() and path != self.report
        ]

    def write_report(self, *, rows=None, extra=None):
        document = {"schema_version": 1, "rollup": {}, "final_assets": self.rows() if rows is None else rows}
        if extra:
            document.update(extra)
        self.report.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")

    def test_accepts_exact_regular_file_set_bytes_and_hashes(self):
        result = subject.verify(self.root)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["files"], 2)
        self.assertRegex(result["sha256"], r"^[0-9a-f]{64}$")

    def test_missing_extra_size_and_hash_each_fail_closed(self):
        rows = self.rows()
        for changed in (
            rows[:-1],
            rows + [{"file_name": "ghost.js", "bytes": 0, "sha256": "0" * 64}],
            [{**rows[0], "bytes": rows[0]["bytes"] + 1}, *rows[1:]],
            [{**rows[0], "sha256": "0" * 64}, *rows[1:]],
        ):
            self.write_report(rows=changed)
            with self.assertRaises(subject.FrontendAssetsFailure):
                subject.verify(self.root)

    def test_rejects_duplicates_unsafe_names_wrong_types_and_nonfinite_json(self):
        rows = self.rows()
        cases = (
            [rows[0], rows[0], *rows[1:]],
            [{**rows[0], "file_name": "../app.js"}, *rows[1:]],
            [{**rows[0], "bytes": True}, *rows[1:]],
            list(reversed(rows)),
        )
        for changed in cases:
            self.write_report(rows=changed)
            with self.assertRaises(subject.FrontendAssetsFailure):
                subject.verify(self.root)
        self.report.write_text('{"schema_version":1,"schema_version":1,"final_assets":[]}', encoding="utf-8")
        with self.assertRaisesRegex(subject.FrontendAssetsFailure, "duplicada"):
            subject.verify(self.root)
        self.report.write_text('{"schema_version":1,"final_assets":[],"value":NaN}', encoding="utf-8")
        with self.assertRaisesRegex(subject.FrontendAssetsFailure, "no finita"):
            subject.verify(self.root)

    def test_rejects_linked_report_asset_and_root(self):
        original = subject._is_link
        for linked in (self.report, self.root / "assets/app.js", self.root):
            with patch.object(subject, "_is_link", side_effect=lambda path, linked=linked: path == linked or original(path)):
                with self.assertRaises(subject.FrontendAssetsFailure):
                    subject.verify(self.root)

    def test_report_is_the_only_excluded_file(self):
        (self.root / "other-report.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(subject.FrontendAssetsFailure, "faltan"):
            subject.verify(self.root)


if __name__ == "__main__":
    unittest.main()
