"""Run registry checks and emit evidence bound to one candidate context."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

try:
    from . import candidate_context
except ImportError:
    import candidate_context


ROOT = Path(__file__).resolve().parents[2]


class CandidateCheckFailure(ValueError):
    pass


def strict_json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CandidateCheckFailure(f"Clave JSON duplicada: {key}")
            result[key] = value
        return result
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda item: (_ for _ in ()).throw(CandidateCheckFailure(item)))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateCheckFailure(f"JSON inválido: {path.name}") from exc
    if not isinstance(value, dict):
        raise CandidateCheckFailure("El JSON debe ser un objeto.")
    return value


def command(root: Path, name: str) -> tuple[list[str], Path, int, bool]:
    registry = strict_json(root / "tooling/cuaderno/commands.json")
    entry = registry.get("commands", {}).get(name)
    if registry.get("schema_version") != 1 or not isinstance(entry, dict) or entry.get("verified") is not True:
        raise CandidateCheckFailure(f"Comando no verificado: {name}")
    argv, cwd_raw, timeout = entry.get("argv"), entry.get("cwd", "."), entry.get("timeout_seconds", 600)
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise CandidateCheckFailure("argv no es explícito.")
    cwd_relative = Path(cwd_raw)
    cwd = (root / cwd_relative).resolve()
    if cwd_relative.is_absolute() or ".." in cwd_relative.parts or not cwd.is_relative_to(root) or not cwd.is_dir():
        raise CandidateCheckFailure("cwd sale del checkout.")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 7200:
        raise CandidateCheckFailure("Timeout fuera de 1..7200 segundos.")
    return argv, cwd, timeout, bool(entry.get("isolated_mutations"))


def run_process(argv: list[str], cwd: Path, timeout: int, environment: dict[str, str]) -> tuple[int, str]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        argv, cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", start_new_session=os.name != "nt",
        creationflags=creationflags,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, output
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        tail, _ = process.communicate()
        return 124, f"{partial}{tail or ''}\nTIMEOUT tras {timeout}s\n"


def redact(text: str) -> str:
    for key, value in os.environ.items():
        if len(value) >= 6 and re.search(r"SECRET|PASSWORD|TOKEN|API_KEY", key, re.I):
            text = text.replace(value, "[REDACTED]")
    return text


def evidence_root(root: Path) -> Path:
    output = root / ".cuaderno-runs"
    if output.is_symlink() or bool(getattr(output, "is_junction", lambda: False)()):
        raise CandidateCheckFailure("El directorio de evidencia es un enlace.")
    output.mkdir(mode=0o700, exist_ok=True)
    resolved = output.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(root):
        raise CandidateCheckFailure("Directorio de evidencia fuera del checkout.")
    return resolved


def confined_context(root: Path, path: Path, *, must_exist: bool) -> Path:
    directory = evidence_root(root)
    path = path if path.is_absolute() else root / path
    if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
        raise CandidateCheckFailure("El contexto candidato no puede ser un enlace.")
    parent = path.parent.resolve(strict=True)
    if parent != directory:
        raise CandidateCheckFailure("El contexto candidato debe estar directamente en .cuaderno-runs.")
    if must_exist and not path.is_file():
        raise CandidateCheckFailure("No existe el contexto candidato.")
    if not must_exist and path.exists():
        raise CandidateCheckFailure("La ruta del contexto debe ser nueva.")
    return path


def write_evidence(root: Path, name: str, record: dict, output: str) -> Path:
    directory = evidence_root(root)
    rid = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{re.sub('[^A-Za-z0-9_-]', '_', name)}-{uuid.uuid4().hex[:12]}"
    log_name, record_name = f"{rid}.log", f"{rid}.json"
    log_path, record_path = directory / log_name, directory / record_name
    safe = redact(output).encode()
    with log_path.open("xb") as stream:
        stream.write(safe)
        stream.flush()
        os.fsync(stream.fileno())
    record.update({"log": log_name, "log_sha256": hashlib.sha256(safe).hexdigest(), "log_bytes": len(safe)})
    raw = (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    with record_path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return record_path


def execute(name: str, context_path: Path, *, root: Path = ROOT, allow_isolated_mutations: bool = False,
            process_runner=run_process,
            context_validator=candidate_context.same_candidate) -> tuple[int, Path]:
    root = root.resolve(strict=True)
    context_path = confined_context(root, context_path, must_exist=True)
    context = strict_json(context_path)
    argv, cwd, timeout, mutations = command(root, name)
    environment_name = os.environ.get("CUADERNO_ENV", "").lower()
    if environment_name in {"prod", "production"}:
        raise CandidateCheckFailure("El runner candidato no opera contra producción.")
    if mutations and (not allow_isolated_mutations or environment_name not in {"local", "test", "development"}):
        raise CandidateCheckFailure("Un check mutable exige entorno local/test/development y autorización explícita.")
    started = time.monotonic()
    failure = None
    output = ""
    try:
        context_validator(context, root)
        env = {**os.environ, "CUADERNO_CANDIDATE_IMAGE": context["image_id"],
               "CUADERNO_SOURCE_IDENTITY": context["source_identity"],
               "CUADERNO_CANDIDATE_CONTEXT": str(context_path)}
        code, output = process_runner(argv, cwd, timeout, env)
        context_validator(context, root)
    except (candidate_context.CandidateFailure, CandidateCheckFailure, OSError) as exc:
        code, failure = 125, str(exc)
        output += f"\nCANDIDATE DRIFT: {exc}\n"
    record = {
        "schema_version": 1, "command": name, "argv": [redact(item) for item in argv],
        "cwd": str(cwd.relative_to(root)), "utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 3), "exit_code": code,
        "passed": code == 0 and failure is None, "failure": failure,
        **{key: context[key] for key in ("candidate_id", "git_commit", "source_sha256", "source_identity",
                                         "image_id", "environment_fingerprint", "commands_registry_sha256")},
    }
    return code, write_evidence(root, name, record, output)


def bootstrap(name: str, image_ref: str, context_path: Path, *, root: Path = ROOT,
              process_runner=run_process, context_capture=candidate_context.capture) -> tuple[int, Path | None]:
    root = root.resolve(strict=True)
    context_path = confined_context(root, context_path, must_exist=False)
    argv, cwd, timeout, mutations = command(root, name)
    if not mutations:
        raise CandidateCheckFailure("El bootstrap de imagen debe declarar mutaciones aisladas.")
    if os.environ.get("CUADERNO_ENV", "").lower() not in {"local", "test", "development"}:
        raise CandidateCheckFailure("El bootstrap solo opera en un entorno aislado autorizado.")
    before = candidate_context.source_identity(root)
    registry_before = candidate_context.sha256(root / "tooling/cuaderno/commands.json")
    env = {**os.environ, "CUADERNO_SOURCE_IDENTITY": before["source_identity"]}
    code, output = process_runner(argv, cwd, timeout, env)
    after = candidate_context.source_identity(root)
    if before != after or registry_before != candidate_context.sha256(root / "tooling/cuaderno/commands.json"):
        code, output = 125, output + "\nCANDIDATE DRIFT durante build\n"
    if code != 0:
        record = {"schema_version": 1, "command": name, "passed": False, "exit_code": code,
                  "argv": [redact(item) for item in argv], "cwd": str(cwd.relative_to(root)),
                  "utc": datetime.now(timezone.utc).isoformat(), "failure": "build o deriva",
                  **before, "image_ref": image_ref, "commands_registry_sha256": registry_before}
        return code, write_evidence(root, name, record, output)
    context = context_capture(root, image_ref)
    with context_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(context, sort_keys=True, indent=2) + "\n")
    record = {"schema_version": 1, "command": name, "passed": True, "exit_code": 0,
              "argv": [redact(item) for item in argv], "cwd": str(cwd.relative_to(root)),
              "utc": datetime.now(timezone.utc).isoformat(), "failure": None,
              **{key: context[key] for key in ("candidate_id", "git_commit", "source_sha256", "source_identity",
                                               "image_id", "environment_fingerprint", "commands_registry_sha256")}}
    return 0, write_evidence(root, name, record, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--allow-isolated-mutations", action="store_true")
    parser.add_argument("--bootstrap-image")
    args = parser.parse_args()
    try:
        if args.bootstrap_image:
            code, path = bootstrap(args.name, args.bootstrap_image, args.context)
        else:
            code, path = execute(args.name, args.context,
                                 allow_isolated_mutations=args.allow_isolated_mutations)
        if path is not None:
            print(f"Evidencia: {path.relative_to(ROOT)}")
        return code
    except CandidateCheckFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
