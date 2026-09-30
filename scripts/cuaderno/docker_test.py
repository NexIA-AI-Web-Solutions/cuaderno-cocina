"""Run native tests with a deadline enforced inside the Docker container.

The outer check runner can stop its local ``docker`` client without stopping the
process created by ``docker exec``.  This launcher deliberately puts BusyBox's
``timeout`` in front of pytest *inside* the one approved test container.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence


ALLOWED_CONTAINER = "cuaderno-g0-t002-web"
ALLOWED_ENVIRONMENTS = frozenset({"local", "test"})
MAX_REMOTE_SECONDS = 1100
KILL_AFTER_SECONDS = 30
PYTEST_EXECUTABLE = "/opt/recipes/venv/bin/pytest"
_DATABASE_PATTERN = re.compile(r"^cuaderno_native_[a-z0-9]+(?:_[a-z0-9]+)*$")
_PRODUCTION_MARKERS = frozenset({"prod", "production", "live"})
_TIMEOUT_STATUSES = frozenset({124, 130, 137})

Launcher = Callable[..., subprocess.CompletedProcess[str]]


class DockerTestFailure(ValueError):
    """The requested run cannot be proven to target the isolated test setup."""


def _validate_target(container: str, database: str, environment: str) -> None:
    if container != ALLOWED_CONTAINER:
        raise DockerTestFailure("contenedor Docker no autorizado")
    if environment not in ALLOWED_ENVIRONMENTS:
        raise DockerTestFailure("CUADERNO_ENV debe ser local o test")
    _validate_database(database)


def _validate_database(database: str) -> None:
    if not isinstance(database, str) or len(database) > 63 or not _DATABASE_PATTERN.fullmatch(database):
        raise DockerTestFailure("namespace PostgreSQL nativo inválido")
    suffix_parts = database.removeprefix("cuaderno_native_").split("_")
    if any(part in _PRODUCTION_MARKERS or part.startswith("prod") for part in suffix_parts):
        raise DockerTestFailure("un namespace de producción nunca es válido")


def _validate_deadline(deadline_seconds: int) -> None:
    if (
        isinstance(deadline_seconds, bool)
        or not isinstance(deadline_seconds, int)
        or not 1 <= deadline_seconds <= MAX_REMOTE_SECONDS
    ):
        raise DockerTestFailure(f"deadline remoto debe estar entre 1 y {MAX_REMOTE_SECONDS} segundos")


def _validate_arguments(pytest_args: Sequence[str]) -> list[str]:
    if isinstance(pytest_args, (str, bytes)) or not pytest_args:
        raise DockerTestFailure("se requieren argumentos explícitos para pytest")
    result = list(pytest_args)
    if any(not isinstance(argument, str) or not argument or "\x00" in argument for argument in result):
        raise DockerTestFailure("argumento de pytest inválido")
    return result


def build_test_argv(
    container: str,
    database: str,
    deadline_seconds: int,
    pytest_args: Sequence[str],
) -> list[str]:
    """Build an argv list; no shell is involved and pytest flags stay verbatim."""
    if container != ALLOWED_CONTAINER:
        raise DockerTestFailure("contenedor Docker no autorizado")
    _validate_database(database)
    _validate_deadline(deadline_seconds)
    arguments = _validate_arguments(pytest_args)
    return [
        "docker",
        "exec",
        "-e",
        f"TEST_POSTGRES_DB={database}",
        container,
        "timeout",
        "-s",
        "INT",
        "-k",
        str(KILL_AFTER_SECONDS),
        str(deadline_seconds),
        PYTEST_EXECUTABLE,
        *arguments,
    ]


def _verify_timeout(container: str, launcher: Launcher) -> None:
    probe = launcher(
        ["docker", "exec", container, "timeout", "--help"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    help_text = probe.stdout or ""
    if probe.returncode != 0 or "timeout" not in help_text.lower() or "-s" not in help_text or "-k" not in help_text:
        raise DockerTestFailure("timeout remoto no ofrece las opciones requeridas -s y -k")


def _normalized_status(returncode: int) -> int:
    """Give GNU and BusyBox timeout outcomes one stable, non-success status."""
    return 124 if returncode in _TIMEOUT_STATUSES else returncode


def run_pytest(
    *,
    container: str,
    database: str,
    environment: str,
    deadline_seconds: int,
    pytest_args: Sequence[str],
    launcher: Launcher = subprocess.run,
) -> int:
    """Validate, probe and run; the exact remote status is returned to the caller."""
    _validate_target(container, database, environment)
    command = build_test_argv(container, database, deadline_seconds, pytest_args)
    _verify_timeout(container, launcher)
    completed = launcher(command, check=False)
    return _normalized_status(completed.returncode)


def run_timeout_smoke(
    *,
    container: str,
    database: str,
    environment: str,
    launcher: Launcher = subprocess.run,
) -> int:
    """Exercise the remote guard with one fixed, harmless sleep command."""
    _validate_target(container, database, environment)
    _verify_timeout(container, launcher)
    completed = launcher(
        [
            "docker",
            "exec",
            "-e",
            f"TEST_POSTGRES_DB={database}",
            container,
            "timeout",
            "-s",
            "INT",
            "-k",
            "2",
            "1",
            "sleep",
            "30",
        ],
        check=False,
    )
    return _normalized_status(completed.returncode)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--deadline", required=True, type=int)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    pytest_args = list(arguments.pytest_args)
    if pytest_args[:1] == ["--"]:
        pytest_args.pop(0)
    try:
        return run_pytest(
            container=arguments.container,
            database=arguments.database,
            environment=arguments.environment,
            deadline_seconds=arguments.deadline,
            pytest_args=pytest_args,
        )
    except DockerTestFailure as error:
        print(f"docker-test: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
