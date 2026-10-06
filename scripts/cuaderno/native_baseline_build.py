"""Build and verify native pinned source using only an exact candidate's runtime in CI."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
PIN = "7e1c427a0e17858ddc41bd198c79ccad77d3bd69"
IMAGE_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
DIRECTORIES = ("cookbook", "recipes", "http.d")
FILES = ("manage.py", "boot.sh", "plugin.py", "requirements.txt", "LICENSE.md")
KINDS = (*DIRECTORIES, *FILES)

# Runs inside either immutable image. No packages, source or browser assets are installed.
DEPENDENCY_PROBE = r'''
import hashlib, importlib.metadata, json, os, pathlib, stat, subprocess, sys
assert os.getuid() != 0, 'native/runtime probes must use a non-root runtime user'
venv = pathlib.Path('/opt/recipes/venv')
assert venv.is_dir() and not venv.is_symlink()
entries = {}
for path in sorted(venv.rglob('*')):
    name = path.relative_to(venv).as_posix()
    if path.is_symlink():
        entries[name] = {'link': os.readlink(path)}
    elif path.is_file():
        entries[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    else:
        assert path.is_dir(), 'special dependency file'
check = subprocess.run([sys.executable, '-m', 'pip', 'check'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
assert check.returncode == 0, 'inherited runtime dependencies failed pip check'
dependencies = {
    'venv_sha256': hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    'interpreter_sha256': hashlib.sha256(pathlib.Path(sys.executable).resolve().read_bytes()).hexdigest(),
    'python': sys.version,
    'distributions': sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions()),
    'pip_check': True,
}
result = {'dependencies': dependencies}
'''
NATIVE_PROBE = r'''
import importlib.util
root = pathlib.Path('/opt/recipes')
assert not (root / 'cuaderno').exists(), 'Cuaderno source must be absent'
assert importlib.util.find_spec('cuaderno') is None, 'Cuaderno package must be absent'
files = {}
for directory in ('cookbook', 'recipes', 'http.d'):
    path = root / directory
    assert path.is_dir() and not path.is_symlink()
    for source in sorted(path.rglob('*')):
        assert not source.is_symlink(), 'linked native source'
        if source.is_file():
            files[source.relative_to(root).as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
        else:
            assert source.is_dir(), 'special native source'
for name in ('manage.py', 'boot.sh', 'plugin.py', 'requirements.txt', 'LICENSE.md'):
    source = root / name
    assert source.is_file() and not source.is_symlink()
    files[name] = hashlib.sha256(source.read_bytes()).hexdigest()
assert stat.S_IMODE((root / 'boot.sh').stat().st_mode) == 0o755
os.environ['DJANGO_SETTINGS_MODULE'] = 'recipes.settings'
os.environ['DISABLE_EXTERNAL_CONNECTORS'] = '1'
from django.conf import settings
assert all(app.split('.')[0] != 'cuaderno' for app in settings.INSTALLED_APPS)
import django
# Older upstream sources may ignore this environment option. Do not start their
# connector daemon just to inspect bytes in a read-only, disconnected container.
connectors_disabled = getattr(settings, 'DISABLE_EXTERNAL_CONNECTORS', False) is True
if connectors_disabled:
    django.setup()
result.update({'files': files, 'cuaderno_installed': False, 'django': django.get_version(),
               'external_connectors_disabled': connectors_disabled, 'django_setup': connectors_disabled})
'''


def _run(argv: list[str], *, root: Path, process_runner=None) -> bytes:
    runner = subprocess.run if process_runner is None else process_runner
    result = runner(argv, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1200, check=False)
    if result.returncode:
        # Do not dump arbitrary subprocess output or environment into CI logs.
        raise RuntimeError(f"Falló {argv[0]} {argv[1]} (exit={result.returncode}).")
    return result.stdout.encode() if isinstance(result.stdout, str) else result.stdout


def _strict_json(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Clave duplicada en la prueba nativa.")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("JSON no finito.")))
    if not isinstance(value, dict):
        raise ValueError("La prueba nativa debe ser un objeto JSON.")
    return value


def source_files(root: Path, *, process_runner=None) -> dict[str, bytes]:
    commit = _run(["git", "rev-parse", "--verify", f"{PIN}^{{commit}}"], root=root,
                  process_runner=process_runner).decode().strip()
    if commit != PIN:
        raise ValueError("El commit nativo no coincide con el pin exacto; se necesita historia Git completa.")
    archive = _run(["git", "archive", "--format=tar", PIN, *KINDS], root=root,
                   process_runner=process_runner)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
        for member in source:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name or ":" in member.name
                    or name.as_posix() != member.name.rstrip("/") or
                    not (member.name in FILES or name.parts and name.parts[0] in DIRECTORIES)):
                raise ValueError("Ruta no admitida en el archivo del pin nativo.")
            if member.isdir():
                continue
            if not member.isfile() or member.name in files:
                raise ValueError("El pin nativo contiene enlaces, archivos especiales o duplicados.")
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError("No se pudo leer el archivo nativo.")
            files[member.name] = stream.read()
    if any(name not in files for name in FILES) or any(
            not any(name.startswith(directory + "/") for name in files) for directory in DIRECTORIES):
        raise ValueError("Faltan archivos canónicos del pin nativo.")
    return files


def source_manifest(files: dict[str, bytes]) -> dict:
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    return {"files": hashes, "sha256": hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def _inspect(image: str, *, root: Path, process_runner=None) -> dict:
    info = _strict_json(_run(["docker", "image", "inspect", image, "--format", "{{json .}}"],
                             root=root, process_runner=process_runner))
    if info.get("Id") != image:
        raise ValueError("La imagen nativa/runtime no resuelve a su ImageID exacto.")
    user = info.get("Config", {}).get("User", "").strip().lower().split(":", 1)[0]
    if user in ("", "0", "root"):
        raise ValueError("La imagen nativa/runtime debe declarar usuario no-root.")
    layers = info.get("RootFS", {}).get("Layers")
    if not isinstance(layers, list) or not layers or any(not IMAGE_RE.fullmatch(layer) for layer in layers):
        raise ValueError("No se pudo verificar la ascendencia de capas de la imagen.")
    return info


def _probe(image: str, *, native=False, root: Path, process_runner=None) -> dict:
    marker = b"NATIVE_BASELINE_PROBE="
    script = DEPENDENCY_PROBE + (NATIVE_PROBE if native else "") + "\nprint('NATIVE_BASELINE_PROBE=' + json.dumps(result, sort_keys=True))\n"
    output = _run([
        "docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
        "--label", "io.cuaderno.native-baseline=probe", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "DISABLE_EXTERNAL_CONNECTORS=1", "--entrypoint", "/opt/recipes/venv/bin/python", image, "-c", script,
    ], root=root, process_runner=process_runner)
    # Native settings print normal startup notices. Only our unique result line is JSON.
    records = [line[len(marker):] for line in output.splitlines() if line.startswith(marker)]
    if len(records) != 1:
        raise ValueError("La inspección nativa no devolvió una prueba única verificable.")
    return _strict_json(records[0])


def proof_path(path: Path, *, root: Path, new=False) -> Path:
    if not path.is_absolute():
        path = root / path
    evidence = root / ".cuaderno-runs"
    if evidence.is_symlink() or not evidence.is_dir() or path.is_symlink():
        raise ValueError("La prueba nativa debe estar en .cuaderno-runs sin enlaces.")
    if path.parent.resolve() != evidence.resolve() or (new and path.exists()):
        raise ValueError("La prueba nativa debe ser un archivo directo nuevo de .cuaderno-runs.")
    if not new and (not path.is_file() or path.stat().st_size > 8 * 1024 * 1024):
        raise ValueError("No existe una prueba nativa regular de tamaño admitido.")
    return path


def verify_proof(image: str, path: Path, *, parent_image: str, root: Path = ROOT, process_runner=None) -> dict:
    if not IMAGE_RE.fullmatch(image) or not IMAGE_RE.fullmatch(parent_image) or image == parent_image:
        raise ValueError("La base nativa exige ImageIDs inmutables distintos y prueba verificable.")
    path = proof_path(path, root=root)
    proof = _strict_json(path.read_bytes())
    expected = source_manifest(source_files(root, process_runner=process_runner))
    if (proof.get("schema_version") != 1 or proof.get("kind") != "cuaderno-native-pin-baseline" or
            proof.get("source_pin") != PIN or proof.get("image_id") != image or
            proof.get("runtime_parent_image_id") != parent_image or proof.get("source") != expected or
            proof.get("cuaderno_installed") is not False):
        raise ValueError("La prueba nativa no coincide con imagen, pin y archivos canónicos.")
    parent = _inspect(parent_image, root=root, process_runner=process_runner)
    native = _inspect(image, root=root, process_runner=process_runner)
    parent_layers = parent["RootFS"]["Layers"]
    native_layers = native["RootFS"]["Layers"]
    labels = native.get("Config", {}).get("Labels", {})
    if (native_layers[:len(parent_layers)] != parent_layers or len(native_layers) <= len(parent_layers) or
            labels.get("io.cuaderno.native-source-pin") != PIN or
            labels.get("io.cuaderno.native-runtime-parent") != parent_image or
            labels.get("io.cuaderno.source-identity") != PIN):
        raise ValueError("La imagen no demuestra fuente nativa sobre el runtime candidato exacto.")
    parent_probe = _probe(parent_image, root=root, process_runner=process_runner)
    native_probe = _probe(image, native=True, root=root, process_runner=process_runner)
    if native_probe.get("external_connectors_disabled") is not True or native_probe.get("django_setup") is not True:
        raise ValueError("El pin nativo no permite desactivar conectores antes de django.setup; no se inicia su daemon.")
    dependencies = parent_probe.get("dependencies")
    if (not isinstance(dependencies, dict) or dependencies.get("pip_check") is not True or
            native_probe.get("dependencies") != dependencies or proof.get("dependencies") != dependencies or
            native_probe.get("files") != expected["files"] or native_probe.get("cuaderno_installed") is not False):
        raise ValueError("Los bytes/dependencias cargados no demuestran el baseline nativo intacto.")
    return proof


def build(candidate_image: str, path: Path, *, root: Path = ROOT, environ=None, process_runner=None) -> dict:
    environ = os.environ if environ is None else environ
    if environ.get("CUADERNO_ENV") != "test" or environ.get("CI") != "true":
        raise ValueError("Construcción de base nativa permitida solo en CI con CUADERNO_ENV=test.")
    if not IMAGE_RE.fullmatch(candidate_image):
        raise ValueError("El parent candidato debe ser un ImageID exacto.")
    evidence = root / ".cuaderno-runs"
    if evidence.is_symlink():
        raise ValueError(".cuaderno-runs no puede ser un enlace.")
    evidence.mkdir(exist_ok=True)
    path = proof_path(path, root=root, new=True)
    files = source_files(root, process_runner=process_runner)
    source = source_manifest(files)
    _inspect(candidate_image, root=root, process_runner=process_runner)
    dependencies = _probe(candidate_image, root=root, process_runner=process_runner)["dependencies"]
    suffix = uuid.uuid4().hex[:12]
    context = evidence / f"native-baseline-{suffix}"
    context.mkdir(mode=0o700)
    for name, data in files.items():
        destination = context / "native" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    # A unique local tag lets BuildKit resolve local parent bytes without pulling a registry image.
    # Both before and after the build its ImageID must remain the exact supplied candidate.
    parent_tag = f"cuaderno-native-parent:{suffix}"
    _run(["docker", "tag", candidate_image, parent_tag], root=root, process_runner=process_runner)
    def check_parent_tag():
        actual = _run(["docker", "image", "inspect", parent_tag, "--format", "{{.Id}}"],
                      root=root, process_runner=process_runner).decode().strip()
        if actual != candidate_image:
            raise ValueError("El tag aislado del parent ya no identifica al candidato exacto.")
    check_parent_tag()
    dockerfile = f'''FROM {parent_tag}
USER 0
RUN rm -rf /opt/recipes/cookbook /opt/recipes/recipes /opt/recipes/cuaderno /opt/recipes/http.d /opt/recipes/release-tools \\
    /opt/recipes/RELEASE-MANIFEST.json /opt/recipes/runtime-application-manifest.json /opt/recipes/SBOM.frontend.cdx.json
COPY native/ /opt/recipes/
RUN chmod 0755 /opt/recipes/boot.sh
LABEL io.cuaderno.native-source-pin="{PIN}" io.cuaderno.native-runtime-parent="{candidate_image}" io.cuaderno.source-identity="{PIN}"
ENV DJANGO_SETTINGS_MODULE=recipes.settings PYTHONDONTWRITEBYTECODE=1 DISABLE_EXTERNAL_CONNECTORS=1
WORKDIR /opt/recipes
USER 10001:10001
HEALTHCHECK NONE
ENTRYPOINT ["/opt/recipes/venv/bin/python"]
CMD ["manage.py", "check"]
'''
    (context / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    iid_file = context / "image.id"
    native_tag = f"cuaderno-native-baseline:{suffix}"
    _run(["docker", "build", "--network=none", "--pull=false", "--no-cache", "--iidfile", str(iid_file),
          "--tag", native_tag,
          "-f", str(context / "Dockerfile"), str(context)], root=root, process_runner=process_runner)
    check_parent_tag()
    build_iid = iid_file.read_text().strip()
    image = _run(["docker", "image", "inspect", native_tag, "--format", "{{.Id}}"],
                 root=root, process_runner=process_runner).decode().strip()
    if not IMAGE_RE.fullmatch(build_iid) or not IMAGE_RE.fullmatch(image) or image == candidate_image:
        raise ValueError("La imagen construida no es una base nativa independiente.")
    proof = {"schema_version": 1, "kind": "cuaderno-native-pin-baseline", "source_pin": PIN,
             "image_id": image, "runtime_parent_image_id": candidate_image, "source": source,
             "dependencies": dependencies, "cuaderno_installed": False,
             "retained_tag": native_tag, "build_iid": build_iid}
    # Publish the proof only after verifying actual source and dependency bytes from the loaded image.
    temporary_proof = evidence / f"native-proof-{suffix}.json"
    temporary_proof.write_text(json.dumps(proof, sort_keys=True) + "\n", encoding="utf-8")
    try:
        verify_proof(image, temporary_proof, parent_image=candidate_image, root=root, process_runner=process_runner)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(proof, sort_keys=True) + "\n")
    finally:
        temporary_proof.unlink(missing_ok=True)
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-image", default=os.environ.get("CUADERNO_CANDIDATE_IMAGE"))
    parser.add_argument("--proof", type=Path, default=Path(".cuaderno-runs/native-baseline.json"))
    args = parser.parse_args()
    try:
        if args.candidate_image is None:
            raise ValueError("Falta --candidate-image exacto.")
        proof = build(args.candidate_image, args.proof)
        print(json.dumps({"image_id": proof["image_id"], "source_pin": PIN, "proof": str(args.proof)}, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
