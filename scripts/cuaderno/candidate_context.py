"""Capture and revalidate one clean source/image/environment release candidate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
if __package__:
    from . import runtime_application, frontend_assets
else:
    import runtime_application
    import frontend_assets


ROOT = Path(__file__).resolve().parents[2]
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
IMAGE_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
INPUTS = (
    "deploy/cuaderno/compose.production.yml", "deploy/cuaderno/Dockerfile",
    "deploy/cuaderno/Dockerfile.dockerignore",
    "tooling/cuaderno/python-production.constraints.txt", "vue3/yarn.lock",
    "tooling/cuaderno/python-test.constraints.txt",
    "vue3/package-lock.json", "yarn.lock",
)
IMAGE_ARTIFACTS = {
    "runtime_application": "/opt/recipes/runtime-application-manifest.json",
    "sbom_python": "/opt/recipes/SBOM.python.cdx.json",
    "sbom_frontend": "/opt/recipes/SBOM.frontend.cdx.json",
    "frontend_provenance": "/opt/recipes/cookbook/static/vue3/cuaderno-build-provenance.json",
    "version_info": "/opt/recipes/cookbook/version_info.py",
    "security_python_backports": "/opt/recipes/SECURITY.python-backports.json",
    "security_alpine_backports": "/opt/recipes/SECURITY.alpine-backports.json",
    "security_node_runtime": "/opt/recipes/SECURITY.node-runtime.json",
    "security_tempfile_backport": "/opt/recipes/SECURITY.tempfile-backport.json",
}
RELEASE_MANIFEST = "/opt/recipes/RELEASE-MANIFEST.json"


class CandidateFailure(ValueError):
    pass


def _run(runner, argv, *, cwd: Path) -> str:
    try:
        result = runner(argv, cwd=cwd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding="utf-8", errors="strict", timeout=60)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise CandidateFailure(f"No se pudo ejecutar {argv[0]}.") from exc
    if result.returncode:
        raise CandidateFailure(f"{argv[0]} no pudo verificar el candidato.")
    return (result.stdout or "").strip()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_manifest(root: Path, runner=subprocess.run) -> dict:
    root = root.resolve(strict=True)
    raw = _run(runner, ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root)
    files = {}
    for name in sorted(set(raw.split("\0")) - {""}):
        path = root / name
        if not path.resolve().is_relative_to(root):
            raise CandidateFailure("Una fuente enlazada sale del checkout.")
        if path.is_file():
            files[name] = sha256(path)
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"files": files, "sha256": digest}


def source_identity(root: Path, runner=subprocess.run, *, require_clean: bool = True) -> dict:
    root = root.resolve(strict=True)
    commit = _run(runner, ["git", "rev-parse", "HEAD"], cwd=root)
    if COMMIT_RE.fullmatch(commit) is None:
        raise CandidateFailure("HEAD no es un commit completo.")
    status = _run(runner, ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root)
    if require_clean and status:
        raise CandidateFailure("El checkout debe estar limpio para identificar un candidato.")
    source = source_manifest(root, runner)
    return {"git_commit": commit, "source_sha256": source["sha256"],
            "source_identity": f"{commit}+worktree.{source['sha256']}"}


def probe_image(root: Path, image_ref: str, runner=subprocess.run) -> dict:
    raw = _run(runner, ["docker", "image", "inspect", image_ref], cwd=root)
    try:
        rows = json.loads(raw)
        info = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
    except json.JSONDecodeError as exc:
        raise CandidateFailure("Docker devolvió metadata de imagen inválida.") from exc
    image_id = info.get("Id") if isinstance(info, dict) else None
    if not isinstance(image_id, str) or IMAGE_RE.fullmatch(image_id) is None:
        raise CandidateFailure("La referencia no resuelve a un Image ID inmutable.")
    labels = info.get("Config", {}).get("Labels") or {}
    allowed_labels = {
        "org.opencontainers.image.created", "org.opencontainers.image.revision",
        "org.opencontainers.image.source", "org.opencontainers.image.version",
        "io.cuaderno.source-identity", "io.cuaderno.sbom-python-sha256",
        "io.cuaderno.sbom-frontend-sha256", "io.cuaderno.frontend-provenance-sha256",
    }
    relevant_labels = {key: value for key, value in labels.items() if key in allowed_labels}
    container = f"cuaderno-candidate-inspect-{uuid.uuid4().hex[:12]}"
    _run(runner, ["docker", "create", "--name", container, image_id], cwd=root)
    artifacts = {}
    try:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, remote in IMAGE_ARTIFACTS.items():
                destination = directory / name
                _run(runner, ["docker", "cp", f"{container}:{remote}", str(destination)], cwd=root)
                if destination.is_symlink() or not destination.is_file():
                    raise CandidateFailure(f"La imagen no contiene {name} como archivo regular.")
                artifacts[name] = sha256(destination)
            try:
                runtime_source = json.loads((directory / "runtime_application").read_text(encoding="utf-8"),
                                            object_pairs_hook=_unique_pairs)
            except (OSError, ValueError) as exc:
                raise CandidateFailure("El manifiesto de aplicación runtime no es JSON estricto.") from exc
            manifest_path = directory / "release_manifest"
            _run(runner, ["docker", "cp", f"{container}:{RELEASE_MANIFEST}", str(manifest_path)], cwd=root)
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise CandidateFailure("La imagen no contiene un manifiesto de release regular.")
            try:
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs,
                    parse_constant=lambda item: (_ for _ in ()).throw(
                        CandidateFailure(f"Constante JSON inválida en manifiesto: {item}")),
                )
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise CandidateFailure("El manifiesto de release no es JSON estricto.") from exc
            if (not isinstance(manifest, dict)
                    or set(manifest) != {"schema_version", "source_identity", "artifacts"}
                    or manifest.get("schema_version") != 1
                    or manifest.get("artifacts") != artifacts):
                raise CandidateFailure("El manifiesto de release no coincide con los artefactos de imagen.")
            expected_version = ('TANDOOR_VERSION = "2.6.15-cuaderno"\n'
                                f'TANDOOR_REF = "{manifest["source_identity"]}"\n'
                                'VERSION_INFO = []\n').encode()
            if (directory / "version_info").read_bytes() != expected_version:
                raise CandidateFailure("La versión empacada no declara la fuente exacta del candidato.")
            assets = directory / "frontend-assets"
            assets.mkdir()
            _run(runner, ["docker", "cp", f"{container}:/opt/recipes/cookbook/static/vue3/.", str(assets)], cwd=root)
            try:
                frontend_assets.verify(assets)
            except (OSError, ValueError) as exc:
                raise CandidateFailure("Los assets frontend no coinciden con su procedencia empacada.") from exc
    finally:
        _run(runner, ["docker", "rm", container], cwd=root)
    return {
        "image_id": image_id, "os": info.get("Os"), "architecture": info.get("Architecture"),
        "layers": info.get("RootFS", {}).get("Layers"), "labels": relevant_labels,
        "artifacts": artifacts, "release_manifest": manifest, "runtime_application": runtime_source,
    }


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CandidateFailure(f"Clave duplicada en manifiesto de release: {key}")
        result[key] = value
    return result


def capture(root: Path, image_ref: str, *, runner=subprocess.run, image_probe=probe_image) -> dict:
    root = root.resolve(strict=True)
    source = source_identity(root, runner)
    files = {}
    for relative in INPUTS:
        path = root / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise CandidateFailure(f"Falta input regular del candidato: {relative}")
        files[relative] = sha256(path)
    registry = root / "tooling/cuaderno/commands.json"
    registry_sha = sha256(registry)
    image = image_probe(root, image_ref, runner)
    if not isinstance(image, dict) or IMAGE_RE.fullmatch(str(image.get("image_id"))) is None:
        raise CandidateFailure("La sonda de imagen no devolvió una identidad válida.")
    manifest = image.get("release_manifest")
    try:
        expected_runtime = runtime_application.build(root, checkout=True)
    except (OSError, ValueError) as exc:
        raise CandidateFailure("No se pudo verificar la fuente de aplicación runtime.") from exc
    if image.get("runtime_application") != expected_runtime:
        raise CandidateFailure("Los bytes de aplicación de la imagen no coinciden con el checkout.")
    if (not isinstance(manifest, dict) or manifest.get("source_identity") != source["source_identity"]
            or image.get("labels", {}).get("io.cuaderno.source-identity") != source["source_identity"]):
        raise CandidateFailure("La imagen no declara la identidad exacta de sus fuentes.")
    environment_payload = {"inputs": files, "image": image}
    environment = hashlib.sha256(json.dumps(environment_payload, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": 1, "candidate_id": str(uuid.uuid4()), **source,
        "image_id": image["image_id"], "environment_fingerprint": environment,
        "commands_registry_sha256": registry_sha, "environment": environment_payload,
    }


def same_candidate(expected: dict, root: Path, *, runner=subprocess.run, image_probe=probe_image) -> dict:
    required = {"schema_version", "candidate_id", "git_commit", "source_sha256", "source_identity",
                "image_id", "environment_fingerprint", "commands_registry_sha256", "environment"}
    if not isinstance(expected, dict) or set(expected) != required or expected.get("schema_version") != 1:
        raise CandidateFailure("Contexto candidato inválido.")
    try:
        uuid.UUID(expected["candidate_id"])
    except (AttributeError, TypeError, ValueError) as exc:
        raise CandidateFailure("candidate_id no es un UUID válido.") from exc
    current = capture(root, expected["image_id"], runner=runner, image_probe=image_probe)
    current["candidate_id"] = expected["candidate_id"]
    if current != expected:
        raise CandidateFailure("La fuente, imagen, entorno o registro han derivado.")
    return current
