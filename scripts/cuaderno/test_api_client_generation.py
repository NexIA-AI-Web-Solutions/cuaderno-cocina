"""Transactional tests for scripts/generate_api_client.py."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import generate_api_client as subject


CONFIGURED_CSRF_RUNTIME = """import {csrfHeadersForUrl} from '@/utils/djangoConfig';
let fetchParams = {url, init};
const headers = new Headers(fetchParams.init.headers);
headers.delete('X-CSRFToken');
for (const [name, value] of Object.entries(csrfHeadersForUrl(fetchParams.url))) headers.set(name, value);
fetchParams.init = {...fetchParams.init, headers, redirect: 'error'};
fetch(fetchParams.url, fetchParams.init);
"""


def snapshot(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


class ApiClientGenerationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.client = self.root / "vue3/src/openapi"
        (self.client / "apis").mkdir(parents=True)
        (self.client / "models").mkdir()
        (self.client / "templates").mkdir()
        (self.client / "apis/OriginalApi.ts").write_text("original api\n", encoding="utf-8")
        (self.client / "models/Original.ts").write_text("original model\n", encoding="utf-8")
        (self.client / "index.ts").write_text("original index\n", encoding="utf-8")
        (self.client / "runtime.ts").write_text("original runtime\n", encoding="utf-8")
        (self.client / "templates/runtime.mustache").write_text("template\n", encoding="utf-8")
        self.schema = self.root / "schema.json"
        self.schema.write_text('{"openapi":"3.0.3","paths":{"/demo":{"get":{}}}}\n', encoding="utf-8")
        self.before = snapshot(self.client)

    def generated(self, argv: list[str], *, csrf: bool = True, suffix: str = "generated") -> Path:
        mount = next(item for item in argv if item.startswith("type=bind,source="))
        stage = Path(mount.removeprefix("type=bind,source=").split(",target=", 1)[0])
        output = stage / "generated"
        (output / "apis").mkdir(parents=True)
        (output / "models").mkdir()
        (output / "apis/DemoApi.ts").write_text(f"api {suffix}\n", encoding="utf-8")
        (output / "models/Demo.ts").write_text(f"model {suffix}\n", encoding="utf-8")
        (output / "index.ts").write_text(f"index {suffix}\n", encoding="utf-8")
        runtime = CONFIGURED_CSRF_RUNTIME if csrf else "fetch('/api')\n"
        (output / "runtime.ts").write_text(runtime, encoding="utf-8")
        return output

    def call(self, runner, *, check: bool = False):
        with patch.object(subject, "ROOT", self.root), patch.object(subject, "CLIENT", self.client):
            return subject.generate(self.schema, check=check, runner=runner)

    def assert_original_sdk(self):
        self.assertEqual(snapshot(self.client), self.before)

    def test_generator_runs_as_the_host_user_on_posix(self):
        with patch.object(subject.os, "name", "posix"), \
             patch.object(subject.os, "getuid", return_value=1001, create=True), \
             patch.object(subject.os, "getgid", return_value=1002, create=True):
            self.assertEqual(subject.generator_user_args(), ["--user", "1001:1002"])
        with patch.object(subject.os, "name", "nt"):
            self.assertEqual(subject.generator_user_args(), [])

        def generate_as_user(argv, **_kwargs):
            self.assertEqual(argv[argv.index("--user") + 1], "1001:1002")
            self.assertEqual(argv[argv.index("--network") + 1], "none")
            self.assertIn(subject.GENERATOR, argv)
            self.generated(argv)

        with patch.object(subject, "generator_user_args", return_value=["--user", "1001:1002"]):
            self.assertTrue(self.call(generate_as_user))

    def test_failed_generator_preserves_every_original_sdk_file(self):
        def fail(_argv, **_kwargs):
            raise subject.subprocess.CalledProcessError(17, ["docker", "run"])
        with self.assertRaises(subject.subprocess.CalledProcessError):
            self.call(fail)
        self.assert_original_sdk()

    def test_incomplete_or_csrf_less_output_preserves_sdk(self):
        def incomplete(argv, **_kwargs):
            output = self.generated(argv)
            shutil.rmtree(output / "models")
        with self.assertRaisesRegex(ValueError, "complete client"):
            self.call(incomplete)
        self.assert_original_sdk()

        def without_csrf(argv, **_kwargs):
            self.generated(argv, csrf=False)
        with self.assertRaisesRegex(ValueError, "CSRF"):
            self.call(without_csrf)
        self.assert_original_sdk()

    def test_check_reports_staged_diff_without_mutating_sdk(self):
        def changed(argv, **_kwargs):
            self.generated(argv, suffix="changed")
        output = io.StringIO()
        with redirect_stdout(output):
            result = self.call(changed, check=True)
        self.assertFalse(result)
        self.assertIn("SDK differs: apis/", output.getvalue())
        self.assertIn("SDK differs: runtime.ts", output.getvalue())
        self.assert_original_sdk()

    def test_swap_failure_rolls_back_every_part(self):
        real_move = shutil.move

        def generated(argv, **_kwargs):
            self.generated(argv)

        def fail_during_swap(source, destination, *args, **kwargs):
            source_path, destination_path = Path(source), Path(destination)
            if source_path.name == "models" and source_path.parent.name == "generated" and destination_path == self.client / "models":
                raise OSError("synthetic swap failure")
            return real_move(source, destination, *args, **kwargs)

        with patch.object(subject.shutil, "move", side_effect=fail_during_swap):
            with self.assertRaisesRegex(OSError, "synthetic swap failure"):
                self.call(generated)
        self.assert_original_sdk()

    def test_rejects_linked_generated_artifact(self):
        outside = self.root / "outside-runtime.ts"
        outside.write_text("getCookie('csrftoken'); headers['X-CSRFToken'] = token;\n", encoding="utf-8")
        def linked(argv, **_kwargs):
            output = self.generated(argv)
            runtime = output / "runtime.ts"
            runtime.unlink()
            try:
                runtime.symlink_to(outside)
            except OSError:
                self.skipTest("El host no permite symlinks de prueba.")
        with self.assertRaises((ValueError, OSError)):
            self.call(linked, check=True)
        self.assert_original_sdk()

    def test_rejects_duplicate_keys_and_nonfinite_schema_before_generator(self):
        invalid_documents = (
            '{"openapi":"3.0.3","paths":{"/one":{}},"paths":{"/two":{}}}',
            '{"openapi":"3.0.3","paths":{"/one":{"get":{"x":NaN}}}}',
        )
        for index, document in enumerate(invalid_documents):
            with self.subTest(index=index):
                self.schema.write_text(document, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.call(lambda *_args, **_kwargs: self.fail("generator must not run"))
                self.assert_original_sdk()

    def test_csrf_words_in_comments_do_not_satisfy_runtime_contract(self):
        def comments_only(argv, **_kwargs):
            output = self.generated(argv)
            (output / "runtime.ts").write_text(
                "// csrftoken and X-CSRFToken are intentionally not implemented\nfetch('/api')\n",
                encoding="utf-8",
            )
        with self.assertRaisesRegex(ValueError, "CSRF"):
            self.call(comments_only)
        self.assert_original_sdk()

    def test_csrf_construct_in_string_does_not_satisfy_runtime_contract(self):
        def string_only(argv, **_kwargs):
            output = self.generated(argv)
            (output / "runtime.ts").write_text(
                'const decoy = "const token = getCookie(\'csrftoken\'); headers[\'X-CSRFToken\'] = token;";\nfetch("/api")\n',
                encoding="utf-8",
            )
        with self.assertRaisesRegex(ValueError, "CSRF"):
            self.call(string_only)
        self.assert_original_sdk()

    def test_header_must_bind_the_configuration_helper_value(self):
        def wrong_value(argv, **_kwargs):
            output = self.generated(argv)
            (output / "runtime.ts").write_text(
                CONFIGURED_CSRF_RUNTIME.replace("headers.set(name, value)", "headers.set(name, other)"),
                encoding="utf-8",
            )
        with self.assertRaisesRegex(ValueError, "CSRF"):
            self.call(wrong_value)
        self.assert_original_sdk()

    def test_checked_in_runtime_and_generator_template_keep_configured_csrf(self):
        client = Path(__file__).resolve().parents[2] / "vue3/src/openapi"
        for relative in ("runtime.ts", "templates/runtime.mustache"):
            with self.subTest(relative=relative):
                self.assertTrue(subject.executable_csrf_contract((client / relative).read_bytes()))

    def test_configured_csrf_contract_binds_destination_headers_and_fetch_init(self):
        self.assertTrue(subject.executable_csrf_contract(CONFIGURED_CSRF_RUNTIME.encode()))
        for wrong in (
            CONFIGURED_CSRF_RUNTIME.replace("@/utils/djangoConfig", "@/other/config"),
            CONFIGURED_CSRF_RUNTIME.replace("csrfHeadersForUrl(fetchParams.url)", "csrfHeadersForUrl(other.url)"),
            CONFIGURED_CSRF_RUNTIME.replace("headers.set(name, value)", "headers.set(name, other)"),
            CONFIGURED_CSRF_RUNTIME.replace("headers.set(name, value)", "other.set(name, value)"),
            CONFIGURED_CSRF_RUNTIME.replace("...fetchParams.init, headers,", "...fetchParams.init, headers: other,"),
            CONFIGURED_CSRF_RUNTIME.replace("fetch(fetchParams.url, fetchParams.init)", "fetch(fetchParams.url, other.init)"),
            CONFIGURED_CSRF_RUNTIME.replace("headers.delete('X-CSRFToken');", ""),
            CONFIGURED_CSRF_RUNTIME.replace("redirect: 'error'", "redirect: 'follow'"),
            CONFIGURED_CSRF_RUNTIME.replace("fetch(fetchParams.url, fetchParams.init)", "fetchParams.url = external; fetch(fetchParams.url, fetchParams.init)"),
            "const token = getCookie('csrftoken'); headers['X-CSRFToken'] = token;",
            "// " + CONFIGURED_CSRF_RUNTIME.replace("\n", "\n// "),
            "const decoy = " + repr(CONFIGURED_CSRF_RUNTIME) + ";",
        ):
            with self.subTest(runtime=wrong):
                self.assertFalse(subject.executable_csrf_contract(wrong.encode()))
                def invalid_runtime(argv, **_kwargs):
                    output = self.generated(argv)
                    (output / "runtime.ts").write_text(wrong, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "CSRF"):
                    self.call(invalid_runtime)
                self.assert_original_sdk()


if __name__ == "__main__":
    unittest.main()
