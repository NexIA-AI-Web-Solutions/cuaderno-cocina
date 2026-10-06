#!/usr/bin/env python3
"""Run browser acceptance against the exact, local release candidate preview."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
CONTAINER = "cuaderno-release-web"
BASE_URL = "http://127.0.0.1:18081"
PREFIX_BASE_URL = "https://127.0.0.1:18443/cuaderno-cocina/"
EXPECTED_BINDINGS = {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}]}
TIMEOUT_SECONDS = 7000
NODE_VERSION = "v24.21.0"
WINDOWS_NODE_SHA256 = "ba4e6d110e8c1592a1ecd390f6b05f3da124b13871a5be62b341a07a853c6c32"


class ReleaseE2EFailure(ValueError):
    """The release browser runner cannot prove its fixed execution context."""


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _regular_tree(path: Path, root: Path, label: str) -> None:
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ReleaseE2EFailure(f"{label} sale del checkout.") from exc
    cursor = root
    for part in relative.parts:
        cursor /= part
        if _is_link(cursor):
            raise ReleaseE2EFailure(f"{label} contiene un ancestro enlace o junction.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def node_executable() -> str:
    executable = os.environ.get("CUADERNO_E2E_NODE") or shutil.which("node")
    if not executable:
        raise ReleaseE2EFailure("No se encuentra el ejecutable local de Node.")
    path = Path(executable)
    if _is_link(path) or not path.is_file():
        raise ReleaseE2EFailure("Node debe ser un ejecutable local regular.")
    return str(path.resolve(strict=True))


def _validate_node(executable: str, *, version_runner=subprocess.run) -> None:
    try:
        completed = version_runner(
            [executable, "--version"], check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseE2EFailure("No se pudo verificar la versión de Node.") from exc
    if completed.returncode != 0 or completed.stdout.strip() != NODE_VERSION:
        raise ReleaseE2EFailure(f"El runner E2E exige Node {NODE_VERSION} exacto.")
    if os.name == "nt" and _sha256(Path(executable)) != WINDOWS_NODE_SHA256:
        raise ReleaseE2EFailure("El binario Node de Windows no coincide con el SHA256 oficial fijado.")


def _regular_file(path: Path, label: str) -> Path:
    try:
        if path.is_symlink() or not path.is_file():
            raise ReleaseE2EFailure(f"Falta {label} local o no es un archivo regular.")
        return path.resolve(strict=True)
    except OSError as exc:
        raise ReleaseE2EFailure(f"No se pudo resolver {label}.") from exc


def _json(path: Path, label: str) -> dict:
    path = _regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseE2EFailure(f"{label} no contiene JSON válido.") from exc
    if not isinstance(value, dict):
        raise ReleaseE2EFailure(f"{label} debe ser un objeto JSON.")
    return value


def validate_toolchain(root: Path = ROOT, *, version_runner=subprocess.run) -> tuple[Path, Path, str]:
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise ReleaseE2EFailure("No se pudo resolver el checkout.") from exc
    e2e = root / "tests/cuaderno/e2e"
    _regular_tree(e2e, root, "El directorio E2E")
    if _is_link(e2e) or not e2e.is_dir() or e2e.resolve(strict=True).parent != root / "tests/cuaderno":
        raise ReleaseE2EFailure("El directorio E2E no pertenece al checkout esperado.")

    tool_paths = [
        e2e / "package.json", e2e / "package-lock.json",
        e2e / "node_modules/@playwright/test/package.json",
        e2e / "node_modules/playwright/package.json",
        e2e / "node_modules/playwright-core/package.json",
        e2e / "node_modules/playwright/cli.js",
    ]
    for path in tool_paths:
        _regular_tree(path, root, str(path.relative_to(root)))

    package = _json(e2e / "package.json", "package.json E2E")
    lock = _json(e2e / "package-lock.json", "package-lock.json E2E")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or lock.get("lockfileVersion") != 3:
        raise ReleaseE2EFailure("El lockfile E2E no tiene el formato fijado.")
    dev = package.get("devDependencies")
    root_dev = packages.get("", {}).get("devDependencies") if isinstance(packages.get(""), dict) else None
    pin = dev.get("@playwright/test") if isinstance(dev, dict) else None
    if not isinstance(pin, str) or not re.fullmatch(r"\d+\.\d+\.\d+", pin) or root_dev != dev:
        raise ReleaseE2EFailure("package.json y package-lock no fijan exactamente las mismas dependencias E2E.")

    test_lock = packages.get("node_modules/@playwright/test")
    runner_lock = packages.get("node_modules/playwright")
    core_lock = packages.get("node_modules/playwright-core")
    if not all(isinstance(item, dict) for item in (test_lock, runner_lock, core_lock)):
        raise ReleaseE2EFailure("El lockfile no contiene toda la cadena local de Playwright.")
    if (
        test_lock.get("version") != pin
        or test_lock.get("dependencies", {}).get("playwright") != pin
        or runner_lock.get("version") != pin
        or runner_lock.get("dependencies", {}).get("playwright-core") != pin
        or core_lock.get("version") != pin
    ):
        raise ReleaseE2EFailure("Las versiones de Playwright divergen dentro del lockfile.")

    installed_test = _json(e2e / "node_modules/@playwright/test/package.json", "@playwright/test instalado")
    installed_runner = _json(e2e / "node_modules/playwright/package.json", "playwright instalado")
    installed_core = _json(e2e / "node_modules/playwright-core/package.json", "playwright-core instalado")
    if (
        installed_test.get("version") != pin
        or installed_runner.get("version") != pin
        or installed_core.get("version") != pin
    ):
        raise ReleaseE2EFailure("La instalación local de Playwright diverge del pin exacto.")
    cli = _regular_file(e2e / "node_modules/playwright/cli.js", "CLI local de Playwright")
    node = node_executable()
    _validate_node(node, version_runner=version_runner)
    try:
        completed = version_runner(
            [node, str(cli), "--version"], cwd=e2e, check=False,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseE2EFailure("No se pudo verificar la versión del CLI local de Playwright.") from exc
    if completed.returncode != 0 or completed.stdout.strip() != f"Version {pin}":
        raise ReleaseE2EFailure("El CLI ejecutable de Playwright diverge del pin exacto.")
    return e2e, cli, node


def inspect_preview(*, inspect_runner=subprocess.run) -> list[dict]:
    try:
        completed = inspect_runner(
            ["docker", "inspect", CONTAINER], check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseE2EFailure("No se pudo inspeccionar el preview Docker.") from exc
    if completed.returncode != 0:
        raise ReleaseE2EFailure("No existe el preview Docker cuaderno-release-web.")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseE2EFailure("docker inspect devolvió JSON inválido.") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ReleaseE2EFailure("docker inspect no identificó exactamente un preview.")
    return value


def validate_preview(value: list[dict], candidate_image: str) -> None:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_image):
        raise ReleaseE2EFailure("CUADERNO_CANDIDATE_IMAGE no es un ID sha256 exacto.")
    preview = value[0]
    if preview.get("Image") != candidate_image or preview.get("Config", {}).get("Image") != candidate_image:
        raise ReleaseE2EFailure("La imagen del preview no coincide exactamente con el candidato.")
    state = preview.get("State", {})
    if state.get("Running") is not True or state.get("Health", {}).get("Status") != "healthy":
        raise ReleaseE2EFailure("El preview candidato no está ejecutándose y healthy.")
    host_bindings = preview.get("HostConfig", {}).get("PortBindings")
    live_bindings = preview.get("NetworkSettings", {}).get("Ports")
    if host_bindings != EXPECTED_BINDINGS or live_bindings != EXPECTED_BINDINGS:
        raise ReleaseE2EFailure(
            "El preview debe publicar exclusivamente 80/tcp como 127.0.0.1:18081.",
        )


def _candidate_image() -> str:
    value = os.environ.get("CUADERNO_CANDIDATE_IMAGE", "")
    if not value:
        raise ReleaseE2EFailure("Falta CUADERNO_CANDIDATE_IMAGE del contexto candidato.")
    return value


def preflight(*, root: Path = ROOT, inspect_runner=subprocess.run, version_runner=subprocess.run) -> None:
    validate_toolchain(root, version_runner=version_runner)
    candidate = _candidate_image()
    validate_preview(inspect_preview(inspect_runner=inspect_runner), candidate)


def run_process(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: int,
    process_factory=subprocess.Popen, cleanup_runner=subprocess.run,
) -> tuple[int, str]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = process_factory(
        argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", start_new_session=os.name != "nt",
        creationflags=creationflags,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, output or ""
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        if os.name == "nt":
            try:
                cleanup = cleanup_runner(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
                )
            except (OSError, subprocess.SubprocessError) as cleanup_exc:
                return 125, f"{partial}\nTIMEOUT: no se pudo eliminar el árbol propio: {cleanup_exc}\n"
            if cleanup.returncode != 0:
                return 125, f"{partial}\nTIMEOUT: taskkill del árbol propio devolvió {cleanup.returncode}\n"
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError as cleanup_exc:
                return 125, f"{partial}\nTIMEOUT: no se pudo terminar el grupo propio: {cleanup_exc}\n"
        try:
            tail, _ = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                return 125, f"{partial}\nTIMEOUT: el árbol propio no terminó tras taskkill\n"
            try:
                os.killpg(process.pid, signal.SIGKILL)
                tail, _ = process.communicate(timeout=30)
            except (OSError, subprocess.TimeoutExpired) as cleanup_exc:
                return 125, f"{partial}\nTIMEOUT: no se pudo eliminar el grupo propio: {cleanup_exc}\n"
        return 124, f"{partial}{tail or ''}\nTIMEOUT tras {timeout}s\n"


def run(
    *, root: Path = ROOT, runner=run_process, inspect_runner=subprocess.run,
    version_runner=subprocess.run, run_id: str | None = None,
) -> int:
    try:
        root = root.resolve(strict=True)
        e2e, cli, node = validate_toolchain(root, version_runner=version_runner)
        candidate = _candidate_image()
        validate_preview(inspect_preview(inspect_runner=inspect_runner), candidate)
        evidence = root / ".cuaderno-runs"
        _regular_tree(evidence, root, ".cuaderno-runs")
        if _is_link(evidence) or not evidence.is_dir() or not evidence.resolve(strict=True).is_relative_to(root):
            raise ReleaseE2EFailure(".cuaderno-runs debe ser un directorio regular del checkout.")
        run_id = run_id or uuid.uuid4().hex
        output_root = evidence / f"e2e-final-{run_id}"
        if output_root.parent != evidence or output_root.exists():
            raise ReleaseE2EFailure("El directorio exclusivo del run ya existe o no está confinado.")
        results = output_root / "test-results"
        report = output_root / "playwright-report"
        results.mkdir(parents=True)
        report.mkdir()
    except (OSError, ReleaseE2EFailure) as exc:
        print(f"RELEASE E2E ERROR: {exc}", file=sys.stderr)
        return 125

    environment = {
        **os.environ,
        "BASE_URL": PREFIX_BASE_URL if os.environ.get("CUADERNO_E2E_PREFIX") == "1" else BASE_URL,
        "CI": "1",
        "CUADERNO_E2E_OUTPUT_DIR": str(results),
        "CUADERNO_E2E_HTML_REPORT": str(report),
    }
    browser_code = 125
    launch_failure: str | None = None
    postflight_failure: ReleaseE2EFailure | None = None
    try:
        browser_code, output = runner(
            [node, str(cli), "test", "--retries=0"],
            cwd=e2e, env=environment, timeout=TIMEOUT_SECONDS,
        )
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
    except OSError as exc:
        launch_failure = f"no se pudo ejecutar Playwright: {exc}"
    finally:
        try:
            validate_preview(inspect_preview(inspect_runner=inspect_runner), candidate)
        except ReleaseE2EFailure as exc:
            postflight_failure = exc
    if postflight_failure is not None:
        print(
            f"RELEASE E2E ERROR: deriva del preview después del navegador: {postflight_failure}",
            file=sys.stderr,
        )
        return 125
    if launch_failure:
        print(f"RELEASE E2E ERROR: {launch_failure}", file=sys.stderr)
    return browser_code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", help="Valida runner y preview sin abrir navegadores.")
    args = parser.parse_args(argv)
    try:
        if args.preflight:
            preflight()
            print("RELEASE E2E PREFLIGHT OK")
            return 0
        return run()
    except ReleaseE2EFailure as exc:
        print(f"RELEASE E2E ERROR: {exc}", file=sys.stderr)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
