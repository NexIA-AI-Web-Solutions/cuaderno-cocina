import subprocess
import unittest
from unittest.mock import patch

from scripts.cuaderno import docker_test


class DockerTestUnitTests(unittest.TestCase):
    def test_builds_exact_capability_probe_and_remote_pytest_argv(self):
        calls = []

        def launcher(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[-2:] == ["timeout", "--help"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout="Usage: timeout [-s SIG] [-k KILL_SECS] SECS PROG ARGS\n",
                )
            return subprocess.CompletedProcess(argv, 0)

        result = docker_test.run_pytest(
            container="cuaderno-g0-t002-web",
            database="cuaderno_native_profile_20260930",
            environment="test",
            deadline_seconds=1100,
            pytest_args=["-o", "addopts=", "-q", "cookbook/tests", "--reuse-db"],
            launcher=launcher,
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            calls,
            [
                (
                    ["docker", "exec", "cuaderno-g0-t002-web", "timeout", "--help"],
                    {
                        "check": False,
                        "stdout": subprocess.PIPE,
                        "stderr": subprocess.STDOUT,
                        "text": True,
                    },
                ),
                (
                    [
                        "docker",
                        "exec",
                        "-e",
                        "TEST_POSTGRES_DB=cuaderno_native_profile_20260930",
                        "cuaderno-g0-t002-web",
                        "timeout",
                        "-s",
                        "INT",
                        "-k",
                        "30",
                        "1100",
                        "/opt/recipes/venv/bin/pytest",
                        "-o",
                        "addopts=",
                        "-q",
                        "cookbook/tests",
                        "--reuse-db",
                    ],
                    {"check": False},
                ),
            ],
        )

    def test_timeout_exit_is_propagated_and_never_reported_as_success(self):
        for remote_status, public_status in ((124, 124), (130, 124), (137, 124), (5, 5)):
            with self.subTest(remote_status=remote_status):
                def launcher(argv, **kwargs):
                    if argv[-2:] == ["timeout", "--help"]:
                        return subprocess.CompletedProcess(
                            argv,
                            0,
                            stdout="timeout [-s SIG] [-k KILL_SECS] SECS PROG ARGS",
                        )
                    return subprocess.CompletedProcess(argv, remote_status)

                self.assertEqual(
                    docker_test.run_pytest(
                        container="cuaderno-g0-t002-web",
                        database="cuaderno_native_regression_20260930",
                        environment="local",
                        deadline_seconds=1099,
                        pytest_args=["cookbook/tests", "--reuse-db"],
                        launcher=launcher,
                    ),
                    public_status,
                )

    def test_rejects_unknown_container_production_and_unsafe_namespaces(self):
        valid = {
            "container": "cuaderno-g0-t002-web",
            "database": "cuaderno_native_profile_20260930",
            "environment": "test",
            "deadline_seconds": 1100,
            "pytest_args": ["cookbook/tests"],
        }
        bad_values = (
            ("container", "cuaderno-web"),
            ("environment", "production"),
            ("environment", "prod"),
            ("environment", ""),
            ("database", "recipes"),
            ("database", "cuaderno_native_prod"),
            ("database", "cuaderno_native_productioncopy"),
            ("database", "cuaderno_native_profile;drop"),
            ("database", "CUADERNO_NATIVE_PROFILE"),
        )
        for field, value in bad_values:
            with self.subTest(field=field, value=value):
                arguments = {**valid, field: value}
                with self.assertRaises(docker_test.DockerTestFailure):
                    docker_test.run_pytest(**arguments, launcher=lambda *_a, **_k: self.fail("must not launch"))

    def test_rejects_invalid_deadlines_and_unsafe_pytest_arguments(self):
        for deadline in (0, -1, 1101, True, "1100"):
            with self.subTest(deadline=deadline), self.assertRaises(docker_test.DockerTestFailure):
                docker_test.build_test_argv(
                    "cuaderno-g0-t002-web",
                    "cuaderno_native_profile_20260930",
                    deadline,
                    ["cookbook/tests"],
                )
        for arguments in ([], [""], ["cookbook/tests", "bad\x00argument"], [1]):
            with self.subTest(arguments=arguments), self.assertRaises(docker_test.DockerTestFailure):
                docker_test.build_test_argv(
                    "cuaderno-g0-t002-web",
                    "cuaderno_native_profile_20260930",
                    1100,
                    arguments,
                )

    def test_capability_probe_fails_closed_before_starting_pytest(self):
        calls = []

        def launcher(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="timeout SECS PROG ARGS")

        with self.assertRaisesRegex(docker_test.DockerTestFailure, "-s.*-k"):
            docker_test.run_pytest(
                container="cuaderno-g0-t002-web",
                database="cuaderno_native_profile_20260930",
                environment="test",
                deadline_seconds=1100,
                pytest_args=["cookbook/tests"],
                launcher=launcher,
            )
        self.assertEqual(len(calls), 1)

    def test_cli_strips_separator_and_returns_remote_status(self):
        with patch.object(docker_test, "run_pytest", return_value=124) as run:
            status = docker_test.main(
                [
                    "--container",
                    "cuaderno-g0-t002-web",
                    "--database",
                    "cuaderno_native_profile_20260930",
                    "--environment",
                    "test",
                    "--deadline",
                    "1100",
                    "--",
                    "-q",
                    "cookbook/tests",
                ]
            )
        self.assertEqual(status, 124)
        run.assert_called_once_with(
            container="cuaderno-g0-t002-web",
            database="cuaderno_native_profile_20260930",
            environment="test",
            deadline_seconds=1100,
            pytest_args=["-q", "cookbook/tests"],
        )

    def test_smoke_command_is_fixed_and_propagates_124(self):
        calls = []

        def launcher(argv, **kwargs):
            calls.append(argv)
            if argv[-2:] == ["timeout", "--help"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout="timeout [-s SIG] [-k KILL_SECS] SECS PROG ARGS",
                )
            return subprocess.CompletedProcess(argv, 130)

        result = docker_test.run_timeout_smoke(
            container="cuaderno-g0-t002-web",
            database="cuaderno_native_timeout_smoke_20260930",
            environment="test",
            launcher=launcher,
        )
        self.assertEqual(result, 124)
        self.assertEqual(
            calls[-1],
            [
                "docker",
                "exec",
                "-e",
                "TEST_POSTGRES_DB=cuaderno_native_timeout_smoke_20260930",
                "cuaderno-g0-t002-web",
                "timeout",
                "-s",
                "INT",
                "-k",
                "2",
                "1",
                "sleep",
                "30",
            ],
        )


if __name__ == "__main__":
    unittest.main()
