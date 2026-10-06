"""Run release checks inside the immutable image used by the local preview."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[2]
IMAGE_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
DB_RE = re.compile(r"cuaderno_test_[a-z0-9_]{1,45}\Z")
TIMEOUT_MINIMUM = 3600
TIMEOUT_MAXIMUM = 7200
BAKED_SCRIPT = "/opt/recipes/release-tools/release_runtime_check.py"
SCHEMA_REFERENCE = Path("/release-reference/openapi.json")
TEST_CONSTRAINTS = Path("/release-tests/python-test.constraints.txt")
OVERLAY_LAUNCHER = """\
import runpy
import sys

overlay = sys.argv.pop(1)
kind = sys.argv.pop(1)
target = sys.argv.pop(1)
sys.path.append(overlay)
sys.argv[0] = target
if kind == "module":
    runpy.run_module(target, run_name="__main__", alter_sys=True)
elif kind == "path":
    runpy.run_path(target, run_name="__main__")
else:
    raise SystemExit("overlay launcher kind invalid")
"""
DECLARED_ARTIFACTS = frozenset({
    "runtime_application", "sbom_python", "sbom_frontend", "frontend_provenance", "version_info", "security_python_backports", "security_alpine_backports", "security_node_runtime", "security_tempfile_backport",
})

RUNTIME_CHECKS = frozenset({
    "runtime-python-lock", "runtime-pip-check", "migrations-final", "schema-final",
    "frontend-provenance", "sbom-python", "sbom-frontend",
})
TEST_CHECKS = frozenset({
    "native-regression-final", "integration-final", "security-final", "performance-final",
})
ALL_CHECKS = RUNTIME_CHECKS | TEST_CHECKS

TEST_ARGUMENTS = {
    "native-regression-final": ["pytest", "-o", "addopts=", "-vv", "-o", "faulthandler_timeout=60",
                                "/opt/recipes/cookbook/tests"],
    "integration-final": ["django", "cuaderno.tests"],
    "security-final": [
        "django", "cuaderno.tests.test_native_security", "cuaderno.tests.test_middleware_roles",
        "cuaderno.tests.test_release_correctness", "cuaderno.tests.test_exchange_portable",
        "cuaderno.tests.test_import_hardening", "cuaderno.tests.test_food_visibility",
    ],
    "performance-final": ["django", "cuaderno.tests.test_performance"],
}


class RuntimeCheckFailure(ValueError):
    pass


def _candidate_validator():
    """Import host-only candidate probing lazily; --inside has no such dependency."""
    try:
        from . import candidate_context
    except ImportError:
        import candidate_context
    return candidate_context.same_candidate


def strict_json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RuntimeCheckFailure(f"Clave JSON duplicada: {key}")
            result[key] = value
        return result
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda item: (_ for _ in ()).throw(RuntimeCheckFailure(item)))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeCheckFailure("El contexto candidato no es JSON estricto.") from exc
    if not isinstance(value, dict):
        raise RuntimeCheckFailure("El contexto candidato debe ser un objeto.")
    return value


def _safe_run(argv: list[str], *, root: Path, timeout: int = 60) -> str:
    try:
        result = subprocess.run(argv, cwd=root, check=False, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                errors="strict", timeout=timeout)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise RuntimeCheckFailure(f"No se pudo consultar {argv[0]}.") from exc
    if result.returncode:
        raise RuntimeCheckFailure(f"{argv[0]} no pudo verificar el preview.")
    return (result.stdout or "").strip()


def inspect_preview(root: Path, container: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container):
        raise RuntimeCheckFailure("Nombre de contenedor preview inválido.")
    image = _safe_run(["docker", "inspect", "--format", "{{.Image}}", container], root=root)
    networks = _safe_run([
        "docker", "inspect", "--format",
        "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{println}}{{end}}", container,
    ], root=root).splitlines()
    networks = [item.strip() for item in networks if item.strip()]
    if IMAGE_RE.fullmatch(image) is None or len(networks) != 1:
        raise RuntimeCheckFailure("El preview debe exponer una imagen inmutable y una red privada única.")
    return image, networks[0]


def verify_declarations(context: dict) -> None:
    try:
        image = context["environment"]["image"]
        labels, artifacts, manifest = image["labels"], image["artifacts"], image["release_manifest"]
    except (KeyError, TypeError) as exc:
        raise RuntimeCheckFailure("El contexto no contiene declaraciones de imagen.") from exc
    source = context.get("source_identity")
    if (not isinstance(source, str) or set(artifacts) != DECLARED_ARTIFACTS
            or any(SHA_RE.fullmatch(str(value)) is None for value in artifacts.values())):
        raise RuntimeCheckFailure("Falta identidad o hash de artefacto en el contexto.")
    if (labels.get("io.cuaderno.source-identity") != source
            or manifest != {"schema_version": 1, "source_identity": source, "artifacts": artifacts}):
        raise RuntimeCheckFailure("La declaración de fuente/SBOM/procedencia no coincide con los artefactos.")
    optional_labels = {
        "io.cuaderno.sbom-python-sha256": artifacts.get("sbom_python"),
        "io.cuaderno.sbom-frontend-sha256": artifacts.get("sbom_frontend"),
        "io.cuaderno.frontend-provenance-sha256": artifacts.get("frontend_provenance"),
    }
    if any(key in labels and labels[key] != value for key, value in optional_labels.items()):
        raise RuntimeCheckFailure("Una etiqueta opcional de artefacto contradice el manifiesto de release.")


def read_local_environment(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeCheckFailure("Falta el archivo local de entorno regular.")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        key, separator, value = raw.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or "\x00" in value:
            raise RuntimeCheckFailure("El archivo local de entorno contiene una línea inválida.")
        if key in values:
            raise RuntimeCheckFailure("El archivo local de entorno contiene claves duplicadas.")
        values[key] = value
    for key in ("CUADERNO_LOCAL_DB_PASSWORD", "CUADERNO_LOCAL_SECRET_KEY"):
        if len(values.get(key, "")) < 24:
            raise RuntimeCheckFailure(f"Falta {key} válido.")
    return values


def test_database(check: str) -> str:
    compact = check.removesuffix("-final").replace("-", "_")[:28]
    name = f"cuaderno_test_{compact}_{uuid.uuid4().hex[:12]}"
    if DB_RE.fullmatch(name) is None:
        raise RuntimeCheckFailure("No se pudo crear un namespace de BD de prueba seguro.")
    return name


def _mount(source: Path, target: str) -> list[str]:
    if source.is_symlink() or not source.exists() or not source.resolve().is_relative_to(ROOT):
        raise RuntimeCheckFailure(f"Fixture de pruebas inválido: {source.name}")
    return ["--mount", f"type=bind,source={source.resolve()},target={target},readonly"]


def _contracts_mount() -> list[str]:
    source = ROOT / "tests/cuaderno/contracts"
    try:
        if source.resolve(strict=True) != source or not source.is_dir():
            raise RuntimeCheckFailure("El directorio de contratos no es canónico y regular.")
        for name in ("costing-cases.json", "stock-cases.json"):
            fixture = source / name
            metadata = fixture.lstat()
            if (fixture.is_symlink() or getattr(fixture, "is_junction", lambda: False)()
                    or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size == 0):
                raise RuntimeCheckFailure("Los contratos requieren archivos regulares sin enlaces.")
    except (OSError, RuntimeError) as error:
        raise RuntimeCheckFailure("No se pudieron verificar los contratos canónicos de prueba.") from error
    return _mount(source, "/opt/recipes/tests/cuaderno/contracts")


def docker_argv(check: str, context: dict, network: str, env_file: Path,
                dev_requirements: Path, test_constraints: Path, container: str) -> list[str]:
    if check not in ALL_CHECKS:
        raise RuntimeCheckFailure(f"Check de runtime desconocido: {check}")
    image = context.get("image_id")
    if not isinstance(image, str) or IMAGE_RE.fullmatch(image) is None:
        raise RuntimeCheckFailure("Image ID candidato inválido.")
    argv = [
        "docker", "run", "--rm", "--name", container, "--network", network,
        "--env-file", str(env_file), "--entrypoint", "/opt/recipes/venv/bin/python",
    ]
    if check in TEST_CHECKS:
        # Overlay only test sources, at the import paths Django/pytest actually resolve.
        # Application modules and the production virtualenv remain the immutable image bytes.
        argv += _mount(ROOT / "cuaderno/tests", "/opt/recipes/cuaderno/tests")
        argv += _mount(ROOT / "cookbook/tests", "/opt/recipes/cookbook/tests")
        argv += _contracts_mount()
        argv += _mount(ROOT / "pytest.ini", "/opt/recipes/pytest.ini")
        argv += ["--mount", f"type=bind,source={dev_requirements.resolve()},target=/release-tests/dev-requirements.txt,readonly"]
        argv += _mount(test_constraints, TEST_CONSTRAINTS.as_posix())
    if check in {"schema-final", "security-final"}:
        argv += _mount(ROOT / "tooling/cuaderno/openapi.json", SCHEMA_REFERENCE.as_posix())
    return argv + [image, BAKED_SCRIPT, "--inside", check]


def run_container(argv: list[str], *, root: Path, timeout: int, container: str) -> tuple[int, str]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(argv, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace",
                               start_new_session=os.name != "nt", creationflags=creationflags)
    try:
        output, _ = process.communicate(timeout=timeout)
        result = process.returncode, output or ""
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        subprocess.run(["docker", "rm", "-f", container], cwd=root, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        tail, _ = process.communicate()
        result = 124, f"{partial}{tail or ''}\nTIMEOUT tras {timeout}s\n"
    subprocess.run(["docker", "rm", "-f", container], cwd=root, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    return result


def _dev_requirements(root: Path) -> str:
    lines = []
    for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if re.fullmatch(r"pytest(?:-[a-z0-9]+)*(?:===|==)\s*[^\s]+", line, re.I):
            lines.append(line.replace("== ", "=="))
    if not {line.split("=")[0].lower() for line in lines} >= {"pytest", "pytest-django"}:
        raise RuntimeCheckFailure("No se encontraron pins de test pytest completos.")
    return "\n".join(lines) + "\n"


def execute(check: str, context_path: Path, *, root: Path = ROOT, preview: str = "cuaderno-release-web",
            local_env: Path | None = None, timeout: int = TIMEOUT_MAXIMUM,
            context_validator=None, preview_inspector=inspect_preview,
            process_runner=run_container, sdk_runner=subprocess.run,
            upgrade_runner=subprocess.run) -> tuple[int, str]:
    root = root.resolve(strict=True)
    if check not in ALL_CHECKS:
        raise RuntimeCheckFailure(f"Check de runtime desconocido: {check}")
    if not TIMEOUT_MINIMUM <= timeout <= TIMEOUT_MAXIMUM:
        raise RuntimeCheckFailure("El timeout debe estar entre 3600 y 7200 segundos.")
    if os.environ.get("CUADERNO_ENV", "").lower() not in {"local", "test", "development"}:
        raise RuntimeCheckFailure("Los checks de runtime solo operan en local/test/development.")
    if context_validator is None:
        context_validator = _candidate_validator()
    context_path = context_path if context_path.is_absolute() else root / context_path
    if (context_path.is_symlink() or not context_path.is_file()
            or context_path.parent.resolve() != (root / ".cuaderno-runs").resolve()):
        raise RuntimeCheckFailure("El contexto debe ser un archivo regular directo de .cuaderno-runs.")
    context = strict_json(context_path)
    context_validator(context, root)
    verify_declarations(context)
    preview_image, network = preview_inspector(root, preview)
    if preview_image != context.get("image_id"):
        raise RuntimeCheckFailure("El preview no ejecuta la imagen candidata exacta.")
    values = read_local_environment(local_env or root / "data/cuaderno/local/compose.env")
    database = test_database(check) if check in TEST_CHECKS else "cuaderno_demo"
    environment = {
        "SECRET_KEY": values["CUADERNO_LOCAL_SECRET_KEY"],
        "DB_ENGINE": "django.db.backends.postgresql", "POSTGRES_HOST": "cuaderno-release-db",
        "POSTGRES_PORT": "5432", "POSTGRES_DB": "cuaderno_demo", "POSTGRES_USER": "cuaderno_demo",
        "POSTGRES_PASSWORD": values["CUADERNO_LOCAL_DB_PASSWORD"],
        "DJANGO_SETTINGS_MODULE": "recipes.test_settings", "TEST_POSTGRES_DB": database,
        "TEST_DB_OPTIONS": "{'options': '-c jit=off'}", "CUADERNO_ENV": "test",
        "PYTHONDONTWRITEBYTECODE": "1", "CUADERNO_SOURCE_IDENTITY": context["source_identity"],
    }
    container = f"cuaderno-release-check-{uuid.uuid4().hex[:16]}"
    with tempfile.TemporaryDirectory(prefix="cuaderno-release-check-") as temporary:
        temporary_path = Path(temporary)
        env_file = temporary_path / "runtime.env"
        env_file.write_text("".join(f"{key}={value}\n" for key, value in environment.items()), encoding="utf-8")
        os.chmod(env_file, 0o600)
        dev_requirements = temporary_path / "dev-requirements.txt"
        dev_requirements.write_text(_dev_requirements(root), encoding="utf-8")
        # This public pins-only file is bound directly into the non-root runtime,
        # whose UID differs from the host owner. Keep secrets and staging private.
        os.chmod(dev_requirements, 0o444)
        argv = docker_argv(
            check, context, network, env_file, dev_requirements,
            root / "tooling/cuaderno/python-test.constraints.txt", container,
        )
        code, output = process_runner(argv, root=root, timeout=timeout, container=container)
    if check == "schema-final" and code == 0:
        sdk = sdk_runner(
            [sys.executable, str(root / "scripts/generate_api_client.py"),
             "--schema", str(root / "tooling/cuaderno/openapi.json"), "--check"],
            cwd=root, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=600,
        )
        output += sdk.stdout or ""
        code = sdk.returncode
    if check == "migrations-final" and code == 0:
        upgrade_environment = {
            **os.environ,
            "CUADERNO_CANDIDATE_IMAGE": context["image_id"],
            "CUADERNO_SOURCE_IDENTITY": context["source_identity"],
            "CUADERNO_CANDIDATE_CONTEXT": str(context_path),
        }
        try:
            upgraded = upgrade_runner(
                [sys.executable, str(root / "scripts/cuaderno/upgrade_smoke.py")],
                cwd=root, env=upgrade_environment, check=False, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                timeout=TIMEOUT_MAXIMUM,
            )
            output += upgraded.stdout or ""
            code = upgraded.returncode
        except subprocess.TimeoutExpired as exc:
            partial = exc.output or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            output += partial + f"\nUPGRADE TIMEOUT tras {TIMEOUT_MAXIMUM}s\n"
            code = 124
        except OSError as exc:
            output += f"\nUPGRADE RUNNER ERROR: {type(exc).__name__}\n"
            code = 125
    context_validator(context, root)
    secrets = [value for key, value in {**os.environ, **values}.items()
               if re.search(r"PASSWORD|SECRET|TOKEN|API_KEY", key) and len(value) >= 6]
    for secret in secrets:
        if secret:
            output = output.replace(secret, "[REDACTED]")
    return code, output


def _run_inside(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode


def _validate_json_artifact(path: str, *, kind: str) -> int:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"),
                           parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return 1
    if not isinstance(value, dict):
        return 1
    if kind == "provenance":
        rollup, final_assets = value.get("rollup"), value.get("final_assets")
        if value.get("schema_version") != 1 or not isinstance(rollup, dict) or set(rollup) != {"main", "service_worker"}:
            return 1
        if not isinstance(final_assets, list) or not final_assets:
            return 1
        for lane in rollup.values():
            if (not isinstance(lane, dict) or not isinstance(lane.get("chunks"), list)
                    or not isinstance(lane.get("assets"), list) or lane.get("unresolved") != []):
                return 1
        rows = final_assets
    elif kind == "cyclonedx":
        if (value.get("bomFormat") != "CycloneDX" or value.get("specVersion") != "1.6"
                or value.get("version") != 1 or not isinstance(value.get("components"), list)
                or not value["components"]):
            return 1
        rows = value["components"]
    else:
        return 1
    return 0 if all(isinstance(row, dict) for row in rows) else 1


def _schema_contract(python: str) -> int:
    with tempfile.TemporaryDirectory() as temporary:
        generated = Path(temporary) / "openapi.json"
        result = _run_inside([
            python, "manage.py", "spectacular", "--validate", "--fail-on-warn",
            "--format", "openapi-json", "--file", str(generated),
        ])
        if result:
            return result
        try:
            actual = json.loads(generated.read_text(encoding="utf-8"),
                                parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
            expected = json.loads(SCHEMA_REFERENCE.read_text(encoding="utf-8"),
                                  parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return 1
        return 0 if actual == expected else 1


def overlay_command(python: str, overlay: str, kind: str, target: str,
                    arguments: list[str]) -> list[str]:
    if kind not in {"module", "path"}:
        raise RuntimeCheckFailure("Tipo de launcher overlay inválido.")
    return [python, "-c", OVERLAY_LAUNCHER, overlay, kind, target, *arguments]


def inside(check: str) -> int:
    """Entry point copied into the candidate image by the release Dockerfile."""
    python = "/opt/recipes/venv/bin/python"
    if check == "runtime-python-lock":
        return _run_inside([python, "/opt/recipes/release-tools/python_lock.py", "--constraints",
                            "/opt/recipes/PYTHON-PRODUCTION.constraints.txt", "--installed"])
    if check == "runtime-pip-check":
        return _run_inside(["/opt/recipes/venv/bin/pip", "check"]) or _run_inside([
            python, "-c", "import xmlsec, lxml.etree, ldap, PIL._imaging; print('RUNTIME_NATIVE_IMPORTS_OK')",
        ])
    if check == "migrations-final":
        first = _run_inside([python, "manage.py", "migrate", "--check", "--noinput"])
        return first or _run_inside([python, "manage.py", "makemigrations", "--check", "--dry-run"])
    if check == "schema-final":
        return _schema_contract(python)
    if check == "frontend-provenance":
        return _run_inside([
            python, "/opt/recipes/release-tools/frontend_assets.py",
            "--root", "/opt/recipes/cookbook/static/vue3",
            "--report", "/opt/recipes/cookbook/static/vue3/cuaderno-build-provenance.json",
        ])
    if check == "sbom-python":
        return _run_inside([python, "/opt/recipes/release-tools/python_lock.py", "--constraints",
                            "/opt/recipes/PYTHON-PRODUCTION.constraints.txt", "--requirements",
                            "/opt/recipes/requirements.txt", "--sbom", "/opt/recipes/SBOM.python.cdx.json"])
    if check == "sbom-frontend":
        return _validate_json_artifact("/opt/recipes/SBOM.frontend.cdx.json", kind="cyclonedx")
    if check in TEST_CHECKS:
        if _run_inside(["/opt/recipes/venv/bin/pip", "check"]):
            return 1
        if check == "security-final":
            if _schema_contract(python):
                return 1
        overlay = f"/tmp/cuaderno-release-test-overlay-{uuid.uuid4().hex}"
        if _run_inside([
            python, "-m", "pip", "install", "--target", overlay,
            "--disable-pip-version-check", "--no-cache-dir",
            "-c", "/opt/recipes/PYTHON-PRODUCTION.constraints.txt",
            "-c", TEST_CONSTRAINTS.as_posix(), "-r", "/release-tests/dev-requirements.txt",
        ]):
            return 1
        args = TEST_ARGUMENTS[check]
        if args[0] == "pytest":
            return _run_inside(overlay_command(python, overlay, "module", "pytest", args[1:]))
        return _run_inside(overlay_command(
            python, overlay, "path", "/opt/recipes/manage.py",
            ["test", *args[1:], "--noinput", "--verbosity", "2"],
        ))
    raise RuntimeCheckFailure(f"Check interno desconocido: {check}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", nargs="?", choices=sorted(ALL_CHECKS))
    parser.add_argument("--context", type=Path)
    parser.add_argument("--preview", default="cuaderno-release-web")
    parser.add_argument("--local-env", type=Path)
    parser.add_argument("--timeout", type=int, default=TIMEOUT_MAXIMUM)
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        print("\n".join(sorted(ALL_CHECKS)))
        return 0
    if not args.check:
        parser.error("Indica un check o --list.")
    try:
        if args.inside:
            return inside(args.check)
        raw_context = args.context or (Path(os.environ["CUADERNO_CANDIDATE_CONTEXT"])
                                       if "CUADERNO_CANDIDATE_CONTEXT" in os.environ else None)
        if raw_context is None:
            raise RuntimeCheckFailure("Falta --context o CUADERNO_CANDIDATE_CONTEXT.")
        code, output = execute(args.check, raw_context, preview=args.preview,
                               local_env=args.local_env, timeout=args.timeout)
        print(output, end="" if output.endswith("\n") else "\n")
        return code
    except (ValueError, OSError, KeyError) as exc:
        print(f"ERROR release runtime: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
