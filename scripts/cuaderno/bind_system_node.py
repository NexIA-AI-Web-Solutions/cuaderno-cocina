#!/usr/bin/env python3
"""Bind nodejs-wheel-binaries' Python wrapper to the pinned Alpine Node."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata, util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid


WHEEL_DISTRIBUTION = "nodejs-wheel-binaries"
WHEEL_VERSION = "24.19.0"
WHEEL_NODE_SHA256 = "af8b92d1e04816119ae1636ed627527ab92960404b88bde5799efddc4b7a9f8d"
WHEEL_EXECUTABLE_SHA256 = "f2b9cf47a430c13d35a354e691e6815ca88b70307110a765f2fa4a40d4bb726c"
WHEEL_LICENSE_SHA256 = "a998d00cf0e67e81e0f2e6c9aeca449608d956961cf5ab68c7604a412e64c505"
WHEEL_LICENSE_RELATIVE = Path("nodejs_wheel_binaries-24.19.0.dist-info/licenses/LICENSE")
SYSTEM_NODE = Path("/usr/bin/node")
SYSTEM_NODE_SHA256 = "2b77a918ccc44e1acccd9ecfb5a3a93f9b8cd7d8da52a1493e6fde5ef5098f7e"
SYSTEM_NODE_VERSION = "v24.18.1"
ALPINE_PROVENANCE = Path("/opt/recipes/SECURITY.alpine-backports.json")
ZLIB_LINK = Path("/usr/lib/libz.so.1")
ZLIB_REAL_PATH = "/usr/lib/libz.so.1.3.2"
ALPINE_PACKAGE = "nodejs-24.18.1-r0"
APK_URL = "https://dl-cdn.alpinelinux.org/alpine/v3.23/main/x86_64/nodejs-24.18.1-r0.apk"
APK_SHA256 = "3c78c9bc8a1d52cc18e79f94120d69ae7705dab1d77054dfa040a064bf344b87"
APK_SIZE = 19_753_406
APORTS_COMMIT = "e63efda2ffc3f7389eda3adbf5f569961d9b0d7a"
APKBUILD_URL = (
    "https://gitlab.alpinelinux.org/alpine/aports/-/raw/"
    f"{APORTS_COMMIT}/main/nodejs/APKBUILD"
)
APKBUILD_SHA256 = "550ea60c17ddec5f9648bd2dcf38b9749518c66ec525f5238f02479395053849"
SOURCE_URL = "https://nodejs.org/dist/v24.18.1/node-v24.18.1.tar.gz"
LICENSE = "MIT"
LICENSE_URL = "https://github.com/nodejs/node/blob/v24.18.1/LICENSE"
JS_CHECK = (
    "console.log(JSON.stringify([2+3,require('node:crypto').createHash('sha256')"
    ".update('cuaderno').digest('hex'),process.versions.zlib]))"
)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class BindFailure(ValueError):
    pass


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _exact_link(path: Path, target: Path) -> bool:
    raw = os.readlink(path)
    if raw == str(target):
        return True
    return (os.environ.get("CUADERNO_NODE_BIND_TEST") == "1"
            and path.resolve(strict=True) == target.resolve(strict=True))


def _regular_directory(path: Path, label: str) -> Path:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise BindFailure(f"No existe {label}.") from exc
    if not stat.S_ISDIR(mode) or path.is_symlink():
        raise BindFailure(f"{label} debe ser un directorio real, no un enlace.")
    return path.resolve(strict=True)


def _run(runner, command: list[str], *, label: str) -> str:
    try:
        result = runner(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding="utf-8", errors="strict", timeout=30)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise BindFailure(f"No se pudo comprobar {label}.") from exc
    if result.returncode:
        raise BindFailure(f"Falló la comprobación de {label}.")
    return (result.stdout or "").strip()


def _strict_json(path: Path) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise BindFailure("La procedencia Alpine contiene una clave duplicada.")
            value[key] = item
        return value
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise BindFailure("La procedencia Alpine debe ser un archivo regular acotado.")
        value = json.loads(path.read_bytes(), object_pairs_hook=unique,
                           parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise BindFailure("La procedencia Alpine no es JSON estricto.") from exc
    expected = {"schema_version", "alpine_aports_commit", "alpine_image", "architecture",
                "source_date_epoch", "source_inputs_sha256", "packages", "patches",
                "runtime_files", "verified"}
    if not isinstance(value, dict) or set(value) != expected or value.get("schema_version") != 1:
        raise BindFailure("La procedencia Alpine no tiene el contrato exacto.")
    return value


def _validate_zlib(provenance_path: Path, zlib_link: Path, *, runner) -> dict:
    if ((provenance_path != ALPINE_PROVENANCE or zlib_link != ZLIB_LINK)
            and os.environ.get("CUADERNO_NODE_BIND_TEST") != "1"):
        raise BindFailure("Las rutas de procedencia y zlib deben ser las runtime fijadas.")
    provenance = _strict_json(provenance_path)
    runtime_files = provenance.get("runtime_files")
    if not isinstance(runtime_files, dict) or set(runtime_files) != {
            "/bin/busybox", "/usr/bin/ssl_client", ZLIB_REAL_PATH}:
        raise BindFailure("La procedencia Alpine no liga el conjunto exacto de binarios runtime.")
    expected = runtime_files.get(ZLIB_REAL_PATH)
    if not isinstance(expected, str) or HEX64.fullmatch(expected) is None:
        raise BindFailure("La procedencia Alpine no liga el hash de zlib.")
    if not zlib_link.is_symlink():
        raise BindFailure("libz.so.1 debe ser el enlace del paquete Alpine.")
    try:
        real = zlib_link.resolve(strict=True)
        mode = real.lstat().st_mode
    except OSError as exc:
        raise BindFailure("No se pudo resolver libz.so.1.") from exc
    if not stat.S_ISREG(mode) or _sha256(real) != expected:
        raise BindFailure("La zlib cargada no coincide con la procedencia Alpine.")
    ldd = _run(runner, ["ldd", str(SYSTEM_NODE)], label="la resolución runtime de zlib")
    expected_line = re.compile(rf"^\s*libz\.so\.1\s+=>\s+{re.escape(str(zlib_link))}\s+\(", re.MULTILINE)
    if expected_line.search(ldd) is None:
        raise BindFailure("El cargador no resuelve Node contra la zlib Alpine fijada.")
    return {"link": str(zlib_link), "path": ZLIB_REAL_PATH, "sha256": expected}


def _validate_system_node(system_node: Path, *, runner) -> dict:
    try:
        mode = system_node.lstat().st_mode
    except OSError as exc:
        raise BindFailure("No existe el Node de Alpine fijado.") from exc
    if system_node != SYSTEM_NODE and os.environ.get("CUADERNO_NODE_BIND_TEST") != "1":
        raise BindFailure("El Node del sistema debe ser /usr/bin/node.")
    if not stat.S_ISREG(mode) or system_node.is_symlink():
        raise BindFailure("El Node de Alpine debe ser un archivo regular, no un enlace.")
    digest = _sha256(system_node)
    if digest != SYSTEM_NODE_SHA256:
        raise BindFailure("El binario Node de Alpine no coincide con el SHA-256 fijado.")
    version = _run(runner, [str(system_node), "--version"], label="la versión de Node")
    if version != SYSTEM_NODE_VERSION:
        raise BindFailure("La versión de Node de Alpine no coincide.")
    owner = _run(runner, ["apk", "info", "--who-owns", str(system_node)], label="el propietario APK")
    if owner != f"{system_node} is owned by {ALPINE_PACKAGE}":
        raise BindFailure("El binario Node no pertenece al APK fijado.")
    _run(runner, ["apk", "info", "-e", f"nodejs=24.18.1-r0"], label="el paquete Node")
    needed = _run(runner, ["scanelf", "-n", "-q", str(system_node)], label="el enlace ELF de Node")
    libraries = set(re.split(r"[\s,\[\]]+", needed))
    if "libz.so.1" not in libraries or len(re.findall(r"(?<![\w.])libz\.so\.1(?![\w.])", needed)) != 1:
        raise BindFailure("Node no declara el enlace dinámico requerido con libz.so.1.")
    if _run(runner, ["scanelf", "-r", "-q", str(system_node)], label="RPATH/RUNPATH de Node"):
        raise BindFailure("Node no puede declarar RPATH ni RUNPATH privados.")
    raw = _run(runner, [str(system_node), "--eval", JS_CHECK], label="Node y crypto")
    try:
        runtime = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BindFailure("Node devolvió una prueba funcional inválida.") from exc
    if (not isinstance(runtime, list) or len(runtime) != 3 or runtime[:2] != [5, hashlib.sha256(b"cuaderno").hexdigest()]
            or not isinstance(runtime[2], str) or not runtime[2]):
        raise BindFailure("Node no superó la prueba funcional y de crypto.")
    return {"sha256": digest, "version": version, "zlib_version": runtime[2],
            "needed": sorted(item for item in libraries if item)}


def _probe_wrapper(root: Path) -> None:
    executable = root / "executable.py"
    if executable.is_symlink() or not executable.is_file():
        raise BindFailure("Falta el wrapper Python regular de nodejs-wheel-binaries.")
    spec = util.spec_from_file_location("_cuaderno_nodejs_wheel_executable", executable)
    if spec is None or spec.loader is None:
        raise BindFailure("No se pudo cargar el wrapper Python de Node.")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.ROOT_DIR).resolve() != root:
        raise BindFailure("El wrapper Python no resuelve el ROOT_DIR esperado.")
    result = module.node(["--eval", JS_CHECK], return_completed_process=True,
                         capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=30)
    if result.returncode:
        raise BindFailure("El wrapper Python no pudo ejecutar el Node enlazado.")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BindFailure("El wrapper Python devolvió una prueba inválida.") from exc
    if value[:2] != [5, hashlib.sha256(b"cuaderno").hexdigest()]:
        raise BindFailure("El wrapper Python no conserva Node y crypto.")


def bind_system_node(root: Path, *, wheel_version: str, system_node: Path = SYSTEM_NODE,
                     wheel_license: Path | None = None,
                     alpine_provenance: Path = ALPINE_PROVENANCE, zlib_link: Path = ZLIB_LINK,
                     runner=subprocess.run, wrapper_probe=_probe_wrapper) -> dict:
    if wheel_version != WHEEL_VERSION:
        raise BindFailure("La distribución nodejs-wheel-binaries no coincide con 24.19.0.")
    root = Path(root)
    if root.name != "nodejs_wheel":
        raise BindFailure("El ROOT_DIR no corresponde a nodejs_wheel.")
    root = _regular_directory(root, "ROOT_DIR")
    bin_dir = _regular_directory(root / "bin", "ROOT_DIR/bin")
    if bin_dir.parent != root:
        raise BindFailure("ROOT_DIR/bin sale del paquete Python.")
    executable = root / "executable.py"
    if (executable.is_symlink() or not executable.is_file()
            or executable.resolve(strict=True).parent != root
            or _sha256(executable) != WHEEL_EXECUTABLE_SHA256):
        raise BindFailure("El wrapper executable.py no coincide con la rueda fijada.")
    license_path = Path(wheel_license) if wheel_license is not None else root.parent / WHEEL_LICENSE_RELATIVE
    expected_license = root.parent / WHEEL_LICENSE_RELATIVE
    if (license_path.is_symlink() or not license_path.is_file()
            or license_path.resolve(strict=True) != expected_license.resolve(strict=True)
            or _sha256(license_path) != WHEEL_LICENSE_SHA256):
        raise BindFailure("Debe conservarse la licencia exacta de nodejs-wheel-binaries.")
    system = _validate_system_node(Path(system_node), runner=runner)
    zlib = _validate_zlib(Path(alpine_provenance), Path(zlib_link), runner=runner)
    node = bin_dir / "node"
    if node.is_symlink():
        if not _exact_link(node, SYSTEM_NODE) or system_node != SYSTEM_NODE:
            raise BindFailure("El enlace Node existente no apunta exactamente a /usr/bin/node.")
        wrapper_probe(root)
        status = "already-bound"
    else:
        try:
            mode = node.lstat().st_mode
        except OSError as exc:
            raise BindFailure("Falta el binario Node original de la rueda.") from exc
        if not stat.S_ISREG(mode) or _sha256(node) != WHEEL_NODE_SHA256:
            raise BindFailure("El binario Node original no coincide con la rueda fijada.")
        token = uuid.uuid4().hex
        backup, link = bin_dir / f".node-original-{token}", bin_dir / f".node-link-{token}"
        try:
            os.link(node, backup)
            os.symlink(str(SYSTEM_NODE), link)
            os.replace(link, node)
            wrapper_probe(root)
            backup.unlink()
        except Exception as exc:
            if backup.exists():
                try:
                    os.replace(backup, node)
                except OSError as rollback:
                    raise BindFailure("Falló el enlace y no pudo restaurarse el binario original.") from rollback
            try:
                link.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(exc, BindFailure):
                raise
            raise BindFailure("No se pudo enlazar Node atómicamente; se restauró el original.") from exc
        status = "bound"
    if not node.is_symlink() or not _exact_link(node, SYSTEM_NODE):
        raise BindFailure("La verificación final del enlace Node falló.")
    return {
        "schema_version": 1, "status": status,
        "wheel": {"distribution": WHEEL_DISTRIBUTION, "version": WHEEL_VERSION,
                  "root": str(root), "node_path": str(node),
                  "original_node_sha256": WHEEL_NODE_SHA256,
                  "executable_sha256": WHEEL_EXECUTABLE_SHA256,
                  "license_path": str(license_path), "license_sha256": WHEEL_LICENSE_SHA256},
        "runtime": {"path": str(SYSTEM_NODE), **system, "zlib": zlib},
        "package": {"name": "nodejs", "version": "24.18.1-r0", "apk_url": APK_URL,
                    "apk_sha256": APK_SHA256, "apk_size": APK_SIZE,
                    "aports_commit": APORTS_COMMIT, "apkbuild_url": APKBUILD_URL,
                    "apkbuild_sha256": APKBUILD_SHA256, "source_url": SOURCE_URL,
                    "license": LICENSE, "license_url": LICENSE_URL,
                    "shared_zlib": True},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output = args.output
        if (not output.is_absolute() or output.is_symlink() or output.exists()
                or not output.parent.is_dir() or output.parent.is_symlink()
                or output.parent.resolve(strict=True) != output.parent):
            raise BindFailure("La salida debe ser una ruta absoluta nueva con padre real.")
        distribution = metadata.distribution(WHEEL_DISTRIBUTION)
        root = Path(distribution.locate_file("nodejs_wheel"))
        wheel_license = Path(distribution.locate_file(WHEEL_LICENSE_RELATIVE))
        result = bind_system_node(root, wheel_version=distribution.version, wheel_license=wheel_license)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
        print("CUADERNO_NODE_RUNTIME " + json.dumps(result, sort_keys=True))
        return 0
    except (BindFailure, metadata.PackageNotFoundError, OSError, subprocess.SubprocessError) as exc:
        print(f"CUADERNO_NODE_RUNTIME ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
