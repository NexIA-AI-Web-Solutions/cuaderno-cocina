#!/usr/bin/env python3
"""Review retained Grype findings against exact, runtime-proven remediations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
import uuid

try:
    from . import (bind_system_node, candidate_context, image_archive_audit, image_audit,
                   patch_runtime_security, scanner_db_provenance)
except ImportError:
    import bind_system_node
    import candidate_context
    import image_archive_audit
    import image_audit
    import patch_runtime_security
    import scanner_db_provenance


ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r"[0-9a-f]{64}\Z")
PYTHON_RELEASE_CVES = frozenset({
    "CVE-2026-82049", "CVE-2026-15310", "CVE-2026-19672",
    "CVE-2026-15806", "CVE-2026-17084", "CVE-2026-87910",
})
PYTHON_RELEASE = {
    "release_url": "https://www.python.org/downloads/release/python-31316/",
    "source_url": "https://www.python.org/ftp/python/3.13.16/Python-3.13.16.tar.xz",
    "source_sha256": "f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d",
    "tag_commit": "3b55c23ff4a6aa32f77be661802a3978d7324f88",
    "license": "PSF-2.0",
    "license_url": "https://github.com/python/cpython/blob/v3.13.16/LICENSE",
}
ALPINE_COMMIT = "e63efda2ffc3f7389eda3adbf5f569961d9b0d7a"
ALPINE_IMAGE = "sha256:85fe1e81d6758c208f3e1eed4338a1997e19d4be002d4dd32d3100c9a8c010a0"
ALPINE_PACKAGES = {
    "busybox": ("1.37.0-r31", "CVE-2025-60876"),
    "busybox-binsh": ("1.37.0-r31", "CVE-2025-60876"),
    "ssl_client": ("1.37.0-r31", "CVE-2025-60876"),
    "zlib": ("1.3.2-r1", "CVE-2026-85091"),
}
ALPINE_RUNTIME_FILES = ("/bin/busybox", "/usr/bin/ssl_client", "/usr/lib/libz.so.1.3.2")
PROOF_KINDS = frozenset({"python-release", "poplib-backport", "alpine-backports"})
ASSESSMENT_POLICY = "reviewed-no-unresolved"
PYTHON_CONSTRAINTS = {
    "CVE-2025-15367": ("< 3.15.0a6 (unknown)", "3.15.0a6"),
    "CVE-2026-15310": ("< 3.15.0rc2 (unknown)", "3.15.0rc2"),
    "CVE-2026-15806": ("< 3.15.0rc2 (unknown)", "3.15.0rc2"),
    "CVE-2026-17084": ("< 3.15.0rc2 (unknown)", "3.15.0rc2"),
    "CVE-2026-19672": ("none (unknown)", ""),
    "CVE-2026-82049": ("< 3.14.0b1 (unknown)", "3.14.0b1"),
    "CVE-2026-87910": ("none (unknown)", ""),
}


class AssessmentFailure(ValueError):
    pass


def _strict(path: Path, label: str) -> tuple[dict, bytes]:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise AssessmentFailure(f"{label} contiene una clave duplicada.")
            value[key] = item
        return value
    try:
        before = path.stat()
        if before.st_size > 64 * 1024 * 1024:
            raise AssessmentFailure(f"{label} supera el límite de 64 MiB.")
        raw = path.read_bytes()
        after = path.stat()
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or len(raw) != before.st_size):
            raise AssessmentFailure(f"{label} cambió mientras se leía.")
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise AssessmentFailure(f"{label} no es JSON estricto.") from exc
    if not isinstance(value, dict):
        raise AssessmentFailure(f"{label} debe ser un objeto JSON.")
    return value, raw


def _strict_runtime(raw: str) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(key)
            value[key] = item
        return value
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AssessmentFailure("La prueba runtime no devolvió JSON estricto.") from exc
    if not isinstance(value, dict):
        raise AssessmentFailure("La prueba runtime no devolvió un objeto JSON.")
    return value


def _strict_json_text(raw: str, label: str):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise AssessmentFailure(f"{label} contiene una clave duplicada.")
            value[key] = item
        return value
    try:
        return json.loads(
            raw, object_pairs_hook=unique,
            parse_constant=lambda item: (_ for _ in ()).throw(
                AssessmentFailure(f"{label} contiene una constante JSON inválida: {item}")),
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise AssessmentFailure(f"{label} no es JSON estricto.") from exc


def _regular(path: Path, root: Path, label: str, *, direct=False) -> Path:
    requested = path if path.is_absolute() else root / path
    try:
        image_audit._reject_link_ancestors(requested.absolute(), root)
    except image_audit.ImageAuditFailure as exc:
        raise AssessmentFailure(f"{label} atraviesa un enlace.") from exc
    if requested.is_symlink() or bool(getattr(requested, "is_junction", lambda: False)()):
        raise AssessmentFailure(f"{label} no puede ser un enlace.")
    try:
        resolved = requested.resolve(strict=True)
    except OSError as exc:
        raise AssessmentFailure(f"No existe {label}.") from exc
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise AssessmentFailure(f"{label} sale del checkout.")
    if direct and resolved.parent != (root / ".cuaderno-runs").resolve(strict=True):
        raise AssessmentFailure(f"{label} debe estar directamente en .cuaderno-runs.")
    return resolved


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _image_artifact_hash(context: dict, name: str) -> str:
    try:
        value = context["environment"]["image"]["artifacts"][name]
    except (KeyError, TypeError) as exc:
        raise AssessmentFailure(f"El contexto no liga el artefacto runtime {name}.") from exc
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise AssessmentFailure(f"Hash de artefacto runtime inválido: {name}")
    return value


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def match_fingerprint(match: dict) -> dict:
    try:
        vulnerability, artifact = match["vulnerability"], match["artifact"]
        locations = sorted(
            ({"path": item["path"], "layerID": item.get("layerID")}
             for item in artifact["locations"]),
            key=lambda item: (item["path"], item["layerID"] or ""),
        )
        value = {
            "vulnerability_id": vulnerability["id"],
            "namespace": vulnerability["namespace"],
            "artifact": {key: artifact[key] for key in ("name", "version", "type", "purl")},
            "locations": locations,
            "match_details": match["matchDetails"],
            "raw_match_sha256": hashlib.sha256(_canonical(match)).hexdigest(),
        }
    except (KeyError, TypeError) as exc:
        raise AssessmentFailure("Un hallazgo no contiene la huella completa requerida.") from exc
    if (not all(isinstance(value[key], str) and value[key] for key in ("vulnerability_id", "namespace"))
            or not locations or any(not isinstance(item["path"], str) or not item["path"] for item in locations)
            or not isinstance(value["match_details"], list) or not value["match_details"]):
        raise AssessmentFailure("Un hallazgo contiene una huella vacía o inválida.")
    value["sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def _classify(fingerprint: dict) -> str:
    cve = fingerprint["vulnerability_id"]
    artifact = fingerprint["artifact"]
    if (fingerprint["namespace"] == "nvd:cpe" and artifact == {
            "name": "python", "version": "3.13.16", "type": "binary",
            "purl": "pkg:generic/python@3.13.16",
            } and {row["path"] for row in fingerprint["locations"]} == {
                "/usr/local/bin/python3.13", "/usr/local/lib/libpython3.13.so.1.0",
            }):
        _validate_python_details(fingerprint)
        if cve in PYTHON_RELEASE_CVES:
            return "python-release"
        if cve == patch_runtime_security.CVE:
            return "poplib-backport"
    package = artifact.get("name")
    expected = ALPINE_PACKAGES.get(package)
    upstream = "&upstream=busybox" if package in {"busybox-binsh", "ssl_client"} else ""
    purl = (f"pkg:apk/alpine/{package}@{expected[0]}?arch=x86_64&distro=alpine-3.23.6{upstream}"
            if expected else None)
    if (expected and cve == expected[1] and fingerprint["namespace"] == "nvd:cpe"
            and artifact == {"name": package, "version": expected[0], "type": "apk", "purl": purl}
            and {row["path"] for row in fingerprint["locations"]} == {"/lib/apk/db/installed"}):
        _validate_apk_details(fingerprint)
        return "alpine-backports"
    raise AssessmentFailure(f"Hallazgo sin prueba permitida exacta: {cve} {artifact.get('name')} {artifact.get('version')}")


def _validate_python_details(fingerprint: dict) -> None:
    cve = fingerprint["vulnerability_id"]
    constraint, suggested = PYTHON_CONSTRAINTS[cve]
    expected = []
    for vendor in ("python", "python_software_foundation"):
        row = {
            "type": "cpe-match", "matcher": "stock-matcher",
            "searchedBy": {"namespace": "nvd:cpe",
                           "cpes": [f"cpe:2.3:a:{vendor}:python:3.13.16:*:*:*:*:*:*:*"],
                           "package": {"name": "python", "version": "3.13.16"}},
            "found": {"vulnerabilityID": cve, "versionConstraint": constraint,
                      "cpes": [f"cpe:2.3:a:{vendor}:python:*:*:*:*:*:*:*:*"]},
        }
        if suggested:
            row["fix"] = {"suggestedVersion": suggested}
        expected.append(row)
    if fingerprint["match_details"] != expected:
        raise AssessmentFailure(f"Los matchDetails Python fueron alterados: {cve}")


def _validate_apk_details(fingerprint: dict) -> None:
    artifact, cve = fingerprint["artifact"], fingerprint["vulnerability_id"]
    vendor = "busybox" if artifact["name"] != "zlib" else "zlib"
    constraint = "<= 1.37.0 (unknown)" if vendor == "busybox" else ">= 1.3.1.2, <= 1.3.2 (unknown)"
    expected = [{
        "type": "cpe-match", "matcher": "apk-matcher",
        "searchedBy": {"namespace": "nvd:cpe",
                       "cpes": [f"cpe:2.3:a:{vendor}:{vendor}:{artifact['version'].split('-r')[0]}:*:*:*:*:*:*:*"],
                       "package": {"name": artifact["name"], "version": artifact["version"]}},
        "found": {"vulnerabilityID": cve, "versionConstraint": constraint,
                  "cpes": [f"cpe:2.3:a:{vendor}:{vendor}:*:*:*:*:*:*:*:*"]},
    }]
    if fingerprint["match_details"] != expected:
        raise AssessmentFailure(f"Los matchDetails APK fueron alterados: {cve} {artifact['name']}")


def _validate_proofs(proof_paths: list[Path], root: Path, fingerprints: dict[str, dict]) -> dict:
    if len(proof_paths) != 3:
        raise AssessmentFailure("Se requieren exactamente tres artefactos de prueba.")
    proofs = {}
    covered = set()
    for supplied in proof_paths:
        path = _regular(supplied, root, "un artefacto de prueba", direct=True)
        value, raw = _strict(path, f"La prueba {path.name}")
        if set(value) != {"schema_version", "kind", "metadata", "fingerprints"} or value["schema_version"] != 1:
            raise AssessmentFailure("Un artefacto de prueba no tiene el contrato exacto.")
        kind, rows = value["kind"], value["fingerprints"]
        if kind not in PROOF_KINDS or kind in proofs or not isinstance(rows, list):
            raise AssessmentFailure("Tipo de prueba desconocido o duplicado.")
        if len(rows) != len(set(rows)) or any(not isinstance(item, str) or SHA.fullmatch(item) is None for item in rows):
            raise AssessmentFailure("Una prueba contiene huellas duplicadas o inválidas.")
        for item in rows:
            if item in covered or item not in fingerprints or _classify(fingerprints[item]) != kind:
                raise AssessmentFailure("Una prueba cubre una huella desconocida, duplicada o de otra política.")
            covered.add(item)
        metadata = value["metadata"]
        if kind == "python-release" and metadata != {**PYTHON_RELEASE, "cves": sorted(PYTHON_RELEASE_CVES)}:
            raise AssessmentFailure("La prueba oficial de Python no coincide con sus fuentes primarias fijadas.")
        if kind == "poplib-backport" and metadata != {
            "cve": patch_runtime_security.CVE, "upstream_commit": patch_runtime_security.UPSTREAM_COMMIT,
            "original_sha256": patch_runtime_security.ORIGINAL_SHA256,
            "patched_sha256": patch_runtime_security.PATCHED_SHA256,
            "original_url": patch_runtime_security.ORIGINAL_URL,
            "patched_url": patch_runtime_security.PATCHED_URL,
            "commit_url": patch_runtime_security.COMMIT_URL,
            "license_url": patch_runtime_security.LICENSE_URL,
        }:
            raise AssessmentFailure("La prueba poplib no coincide con el backport fijado.")
        if kind == "alpine-backports":
            if not _valid_alpine_metadata(metadata):
                raise AssessmentFailure("La prueba Alpine no coincide con paquetes, fuentes y parches fijados.")
        proofs[kind] = {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
                        "metadata": metadata, "fingerprints": rows}
    if covered != set(fingerprints):
        raise AssessmentFailure("Hay hallazgos sin cobertura exacta.")
    return proofs


def _valid_alpine_metadata(value) -> bool:
    if not isinstance(value, dict) or set(value) != {
            "alpine_aports_commit", "alpine_image", "architecture", "source_date_epoch",
            "source_inputs_sha256", "packages", "patches", "runtime_files", "license_urls"}:
        return False
    packages = value.get("packages")
    return (
        value["alpine_aports_commit"] == ALPINE_COMMIT
        and value["alpine_image"] == ALPINE_IMAGE
        and value["architecture"] == "x86_64" and value["source_date_epoch"] == 1790981383
        and isinstance(value["source_inputs_sha256"], str) and SHA.fullmatch(value["source_inputs_sha256"])
        and value["license_urls"] == {
            "busybox": "https://git.busybox.net/busybox/tree/LICENSE",
            "zlib": "https://zlib.net/zlib_license.html",
        }
        and isinstance(packages, dict) and set(packages) == set(ALPINE_PACKAGES)
        and all(isinstance(packages[name], dict) and set(packages[name]) == {"version", "apk_sha256"}
                and packages[name]["version"] == expected[0]
                and isinstance(packages[name]["apk_sha256"], str) and SHA.fullmatch(packages[name]["apk_sha256"])
                for name, expected in ALPINE_PACKAGES.items())
        and isinstance(value["runtime_files"], dict)
        and set(value["runtime_files"]) == set(ALPINE_RUNTIME_FILES)
        and all(isinstance(digest, str) and SHA.fullmatch(digest)
                for digest in value["runtime_files"].values())
        and value["patches"] == {
            "CVE-2025-60876": ["3c8c5b48f53ceb2641bb60c5c43b2a623e72246f2b7c0a87c1367136f455a936"],
            "CVE-2026-85091": [
                "110ff14375733173d8aa54574473424fbd7dfe4b81f1ca34a759c6fe14b15b14",
                "96040ee84d0d187905283912dbd3f7b66ac2033976a2ceefe9b8cca63143d9c2",
                "6475806cdb6383788a03e7af5617188ef2692803889cded1fcb014825923d16c",
                "a786b2b08412686008c7fe1247e90701cebde564037806bd9935f84907737cc4",
            ],
        }
    )


def _valid_node_provenance(value, alpine: dict) -> bool:
    wheel_root = "/opt/recipes/venv/lib/python3.13/site-packages/nodejs_wheel"
    license_path = ("/opt/recipes/venv/lib/python3.13/site-packages/"
                    "nodejs_wheel_binaries-24.19.0.dist-info/licenses/LICENSE")
    if not isinstance(value, dict) or set(value) != {"schema_version", "status", "wheel", "runtime", "package"}:
        return False
    runtime, wheel = value.get("runtime"), value.get("wheel")
    expected_package = {
        "name": "nodejs", "version": "24.18.1-r0",
        "apk_url": bind_system_node.APK_URL, "apk_sha256": bind_system_node.APK_SHA256,
        "apk_size": bind_system_node.APK_SIZE, "aports_commit": bind_system_node.APORTS_COMMIT,
        "apkbuild_url": bind_system_node.APKBUILD_URL,
        "apkbuild_sha256": bind_system_node.APKBUILD_SHA256,
        "source_url": bind_system_node.SOURCE_URL, "license": bind_system_node.LICENSE,
        "license_url": bind_system_node.LICENSE_URL, "shared_zlib": True,
    }
    expected_wheel = {
        "distribution": bind_system_node.WHEEL_DISTRIBUTION,
        "version": bind_system_node.WHEEL_VERSION, "root": wheel_root,
        "node_path": f"{wheel_root}/bin/node",
        "original_node_sha256": bind_system_node.WHEEL_NODE_SHA256,
        "executable_sha256": bind_system_node.WHEEL_EXECUTABLE_SHA256,
        "license_path": license_path, "license_sha256": bind_system_node.WHEEL_LICENSE_SHA256,
    }
    if (value.get("schema_version") != 1 or value.get("status") != "bound"
            or wheel != expected_wheel or value.get("package") != expected_package
            or not isinstance(runtime, dict)
            or set(runtime) != {"path", "sha256", "version", "zlib_version", "needed", "zlib"}):
        return False
    needed = runtime.get("needed")
    return (
        runtime["path"] == "/usr/bin/node"
        and runtime["sha256"] == bind_system_node.SYSTEM_NODE_SHA256
        and runtime["version"] == bind_system_node.SYSTEM_NODE_VERSION
        and isinstance(runtime["zlib_version"], str) and runtime["zlib_version"]
        and isinstance(needed, list) and len(needed) == len(set(needed))
        and needed.count("libz.so.1") == 1 and all(isinstance(item, str) and item for item in needed)
        and runtime["zlib"] == {"link": "/usr/lib/libz.so.1",
                                "path": bind_system_node.ZLIB_REAL_PATH,
                                "sha256": alpine["runtime_files"][bind_system_node.ZLIB_REAL_PATH]}
    )


RUNTIME_SCRIPT = r'''import hashlib,importlib.util,json,os,socket,subprocess,sys,threading
wheel_root="/opt/recipes/venv/lib/python3.13/site-packages/nodejs_wheel"
wheel_node=wheel_root+"/bin/node"; executable=wheel_root+"/executable.py"; license=wheel_root.rsplit("/",1)[0]+"/nodejs_wheel_binaries-24.19.0.dist-info/licenses/LICENSE"
def filehash(path):
 with open(path,"rb") as stream: return hashlib.file_digest(stream,"sha256").hexdigest()
executable_sha=filehash(executable); license_sha=filehash(license); system_node_sha=filehash("/usr/bin/node"); zlib_sha=filehash("/usr/lib/libz.so.1.3.2"); poplib_sha=filehash("/usr/local/lib/python3.13/poplib.py")
if executable_sha!="f2b9cf47a430c13d35a354e691e6815ca88b70307110a765f2fa4a40d4bb726c" or license_sha!="a998d00cf0e67e81e0f2e6c9aeca449608d956961cf5ab68c7604a412e64c505" or system_node_sha!="2b77a918ccc44e1acccd9ecfb5a3a93f9b8cd7d8da52a1493e6fde5ef5098f7e" or poplib_sha!="a6ffff188814b56d95b043c31d9e0dfee51ac6d6e92afe74ab070cb6136b076f" or not os.path.islink(wheel_node) or os.readlink(wheel_node)!="/usr/bin/node" or not os.path.isfile("/usr/bin/node") or os.path.islink("/usr/bin/node"): raise ValueError("untrusted language runtime")
spec=importlib.util.spec_from_file_location("_cuaderno_node_wrapper",executable)
node_wrapper=importlib.util.module_from_spec(spec); spec.loader.exec_module(node_wrapper)
pop_spec=importlib.util.spec_from_file_location("_cuaderno_poplib","/usr/local/lib/python3.13/poplib.py")
poplib=importlib.util.module_from_spec(pop_spec); pop_spec.loader.exec_module(poplib)
class S:
 def __init__(self): self.sent=[]
 def sendall(self,v): self.sent.append(v)
p=poplib.POP3.__new__(poplib.POP3); p._debugging=0; p.sock=S(); rejected=[]
p._putcmd("USER safe")
for name,value in (("CR","X\rY"),("LF","X\nY"),("NUL","X\x00Y"),("DEL","X\x7fY")):
 try: p._putcmd(value)
 except ValueError: rejected.append(name)
def read(path):
 def unique(pairs):
  value={}
  for key,item in pairs:
   if key in value: raise ValueError("duplicate JSON key")
   value[key]=item
  return value
 raw=open(path,"rb").read(); return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda item:(_ for _ in ()).throw(ValueError(item))),hashlib.sha256(raw).hexdigest()
py,pysha=read("/opt/recipes/SECURITY.python-backports.json")
al,alsha=read("/opt/recipes/SECURITY.alpine-backports.json")
nd,ndsha=read("/opt/recipes/SECURITY.node-runtime.json")
if al.get("runtime_files",{}).get("/usr/lib/libz.so.1.3.2")!=zlib_sha: raise ValueError("untrusted zlib runtime")
versions={n:subprocess.check_output(["/sbin/apk","info","-e",n],text=True).strip() for n in ("busybox","busybox-binsh","ssl_client","zlib")}
runtime_files={path:hashlib.sha256(open(path,"rb").read()).hexdigest() for path in ("/bin/busybox","/usr/bin/ssl_client","/usr/lib/libz.so.1.3.2")}
bb_rejected=[]
for value in (" bad","\tbad","\rbad","\nbad"):
 q=subprocess.run(["/bin/busybox","wget","-T","1","-O","-","http://127.0.0.1:1/"+value],capture_output=True,text=True)
 if q.returncode and "Unencoded control character" in q.stderr: bb_rejected.append(value.encode().hex())
s=socket.socket(); s.bind(("127.0.0.1",0)); s.listen(1); port=s.getsockname()[1]
def serve():
 c,_=s.accept(); c.recv(4096); c.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok"); c.close(); s.close()
t=threading.Thread(target=serve,daemon=True); t.start()
normal=subprocess.run(["/bin/busybox","wget","-q","-O","-",f"http://127.0.0.1:{port}/"],capture_output=True,text=True,timeout=5)
t.join(5)
js="console.log(JSON.stringify([2+3,require('node:crypto').createHash('sha256').update('cuaderno').digest('hex'),process.versions.zlib]))"
direct=json.loads(subprocess.check_output(["/usr/bin/node","--eval",js],text=True))
wrapped=node_wrapper.node(["--eval",js],return_completed_process=True,capture_output=True,text=True,timeout=15)
ldd=subprocess.check_output(["ldd","/usr/bin/node"],text=True)
node_runtime={"wheel_node_is_link":os.path.islink(wheel_node),"wheel_node_target":os.readlink(wheel_node) if os.path.islink(wheel_node) else None,"system_node_is_regular":os.path.isfile("/usr/bin/node") and not os.path.islink("/usr/bin/node"),"system_node_sha256":system_node_sha,"executable_sha256":executable_sha,"license_sha256":license_sha,"zlib_link_target":os.readlink("/usr/lib/libz.so.1") if os.path.islink("/usr/lib/libz.so.1") else None,"zlib_sha256":zlib_sha,"ldd":ldd,"direct":direct,"wrapper":{"returncode":wrapped.returncode,"stdout":wrapped.stdout,"stderr":wrapped.stderr}}
print(json.dumps({"schema_version":1,"python_version":".".join(map(str,sys.version_info[:3])),"poplib_sha256":poplib_sha,"poplib_rejected":rejected,"poplib_sent":[x.hex() for x in p.sock.sent],"apk_versions":versions,"runtime_files":runtime_files,"busybox_rejected":bb_rejected,"busybox_normal":{"returncode":normal.returncode,"stdout":normal.stdout,"stderr":normal.stderr,"server_finished":not t.is_alive()},"python_provenance":py,"python_provenance_sha256":pysha,"alpine_provenance":al,"alpine_provenance_sha256":alsha,"node_provenance":nd,"node_provenance_sha256":ndsha,"node_runtime":node_runtime},sort_keys=True,separators=(",",":")))'''


def docker_runtime_probe(context: dict, *, root: Path, runner=subprocess.run) -> dict:
    image = context["image_id"]
    try:
        inspect = runner(["docker", "image", "inspect", image], cwd=root, check=False,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="strict", timeout=60)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise AssessmentFailure("No se pudo inspeccionar la imagen runtime.") from exc
    try:
        rows = _strict_json_text(inspect.stdout, "Docker inspect") if inspect.returncode == 0 else None
        info = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
    except AssessmentFailure:
        raise
    if (not isinstance(info, dict) or info.get("Id") != image
            or (info.get("Config", {}).get("Labels") or {}).get("io.cuaderno.source-identity") != context["source_identity"]):
        raise AssessmentFailure("La imagen runtime no coincide con el contexto y su etiqueta de fuente.")
    name = f"cuaderno-security-proof-{uuid.uuid4().hex[:12]}"
    command = ["docker", "run", "--pull", "never", "--rm", "--name", name,
               "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--user", "10001:10001",
               "--entrypoint", "python", image, "-I", "-S", "-c", RUNTIME_SCRIPT]
    try:
        result = runner(command, cwd=root, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding="utf-8", errors="strict", timeout=120)
    except subprocess.TimeoutExpired as exc:
        try:
            runner(["docker", "rm", "-f", name], cwd=root, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
        raise AssessmentFailure("La prueba runtime agotó su tiempo.") from exc
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise AssessmentFailure("No se pudo ejecutar la prueba runtime aislada.") from exc
    if result.returncode != 0:
        raise AssessmentFailure("La prueba runtime aislada falló.")
    return _strict_runtime(result.stdout)


def assess(*, context_path: Path, archive: Path, report_path: Path, summary_path: Path,
           proof_paths: list[Path], output_path: Path, root: Path = ROOT,
           context_validator=candidate_context.same_candidate, runtime_probe=docker_runtime_probe,
           database_verifier=scanner_db_provenance.verify) -> dict:
    root = root.resolve(strict=True)
    context_file = _regular(context_path, root, "el contexto candidato", direct=True)
    context, _ = _strict(context_file, "El contexto candidato")
    context_validator(context, root)
    archive = _regular(archive, root, "la imagen retenida")
    report_path = _regular(report_path, root, "el informe Grype")
    summary_path = _regular(summary_path, root, "el resumen Grype")
    if report_path.parent != summary_path.parent or report_path.parent.parent != archive.parent:
        raise AssessmentFailure("Informe, resumen y archivo no pertenecen al mismo scan retenido.")
    archive_sha = _sha(archive)
    binding = image_archive_audit._archive_binding(
        archive, image_id=context["image_id"], source_ref=context["source_identity"])
    report, report_raw = _strict(report_path, "El informe Grype")
    summary, summary_raw = _strict(summary_path, "El resumen Grype")
    reported_input = report.get("source", {}).get("target", {}).get("userInput")
    if reported_input != image_archive_audit.CONTAINER_ARCHIVE_INPUT:
        raise AssessmentFailure("El informe no conserva la entrada aislada exacta del archivo retenido.")
    matches, ignored, severities = image_archive_audit._validate_archive_report(
        report, binding=binding, source_input=reported_input)
    if ignored != [] or not matches:
        raise AssessmentFailure("El informe debe conservar hallazgos y ignoredMatches vacío.")
    tool_root = root / "data/cuaderno/tooling/grype-linux-0.119.0"
    db_root = root / "data/cuaderno/tooling/grype-db"
    db_paths = SimpleNamespace(root=root, tool=tool_root / "grype",
        zip_archive=tool_root / "grype_0.119.0_linux_amd64.tar.gz", db_root=db_root,
        database=db_root / "6/vulnerability.db", db_stamp=db_root / "6/import.json")
    receipt_sha = os.environ.get("CUADERNO_SCANNER_DB_RECEIPT_SHA256")
    try:
        receipt = database_verifier(db_paths, receipt_sha, image_archive_audit.LINUX_GRYPE_SHA256,
                                    image_archive_audit.LINUX_ARCHIVE_SHA256)
    except image_audit.ImageAuditFailure as exc:
        raise AssessmentFailure("La provisión de DB no conserva su identidad verificada.") from exc
    database_provision = {
        "receipt_sha256": receipt_sha,
        "installed_database_sha256": receipt["installed_database_sha256"],
        "import_metadata_sha256": receipt["import_metadata_sha256"],
        "raw_database_sha256": receipt["raw_database_sha256"],
        "archive_sha256": receipt["archive_sha256"],
    }
    expected_summary = {
        "status": "findings", "scanner_exit": 2, "image_id": context["image_id"],
        "source_commit": context["source_identity"], "matches": len(matches), "ignored_matches": 0,
        "severity_counts": severities, "archive_sha256": archive_sha, "archive_binding": binding,
        "report_sha256": hashlib.sha256(report_raw).hexdigest(),
        "grype": {"version": image_audit.GRYPE_VERSION, "git_commit": image_audit.GRYPE_COMMIT,
                  "sha256": image_archive_audit.LINUX_GRYPE_SHA256, "platform": "linux_amd64"},
        "database": receipt["import_metadata"],
        "database_provision": database_provision,
        "paths": {"archive": archive.relative_to(root).as_posix(),
                  "report": report_path.relative_to(root).as_posix(),
                  "summary": summary_path.relative_to(root).as_posix()},
    }
    if set(summary) != set(expected_summary) or summary != expected_summary:
        raise AssessmentFailure("El resumen no coincide con el informe, archivo o candidato retenido.")
    fingerprints = {}
    raw_matches = []
    for match in matches:
        fingerprint = match_fingerprint(match)
        key = fingerprint["sha256"]
        if key in fingerprints:
            raise AssessmentFailure("El informe contiene una huella de hallazgo duplicada.")
        _classify(fingerprint)
        fingerprints[key] = fingerprint
        raw_matches.append(match)
    proofs = _validate_proofs(proof_paths, root, fingerprints)
    source_inputs = _regular(root / "docker/runtime-security/source-inputs.json", root,
                             "el manifiesto de fuentes Alpine")
    alpine = proofs["alpine-backports"]["metadata"]
    if alpine["source_inputs_sha256"] != _sha(source_inputs):
        raise AssessmentFailure("La prueba Alpine no coincide con source-inputs.json del candidato.")
    runtime = runtime_probe(context, root=root)
    if (not isinstance(runtime, dict) or runtime.get("schema_version") != 1
            or runtime.get("python_version") != "3.13.16"
            or runtime.get("poplib_sha256") != patch_runtime_security.PATCHED_SHA256
            or runtime.get("poplib_rejected") != ["CR", "LF", "NUL", "DEL"]
            or runtime.get("poplib_sent") != ["5553455220736166650d0a"]
            or runtime.get("apk_versions") != {name: value[0] for name, value in ALPINE_PACKAGES.items()}
            or runtime.get("runtime_files") != alpine["runtime_files"]
            or runtime.get("busybox_rejected") != ["20626164", "09626164", "0d626164", "0a626164"]
            or runtime.get("busybox_normal") != {
                "returncode": 0, "stdout": "ok", "stderr": "", "server_finished": True,
            }):
        raise AssessmentFailure("La prueba runtime no demuestra versiones y comportamiento exactos.")
    python_provenance = {
        "status": "patched", "cve": patch_runtime_security.CVE, "python": "3.13.16",
        "path": "/usr/local/lib/python3.13/poplib.py",
        "original_sha256": patch_runtime_security.ORIGINAL_SHA256,
        "patched_sha256": patch_runtime_security.PATCHED_SHA256,
        "upstream_commit": patch_runtime_security.UPSTREAM_COMMIT,
        "sources": {"original": patch_runtime_security.ORIGINAL_URL,
                    "patched": patch_runtime_security.PATCHED_URL,
                    "commit": patch_runtime_security.COMMIT_URL,
                    "license": patch_runtime_security.LICENSE_URL},
    }
    if (runtime.get("python_provenance") != python_provenance
            or runtime.get("python_provenance_sha256") != _image_artifact_hash(context, "security_python_backports")):
        raise AssessmentFailure("La procedencia Python empacada no coincide con el backport revisado.")
    if (runtime.get("alpine_provenance") != {"schema_version": 1, **{k: v for k, v in alpine.items() if k != "license_urls"}, "verified": True}
            or runtime.get("alpine_provenance_sha256") != _image_artifact_hash(context, "security_alpine_backports")):
        raise AssessmentFailure("La procedencia Alpine empacada no coincide con la prueba revisada.")
    node_provenance, node_runtime = runtime.get("node_provenance"), runtime.get("node_runtime")
    if (not _valid_node_provenance(node_provenance, alpine)
            or runtime.get("node_provenance_sha256") != _image_artifact_hash(context, "security_node_runtime")):
        raise AssessmentFailure("La procedencia Node empacada no coincide con el runtime fijado.")
    expected_js = [5, hashlib.sha256(b"cuaderno").hexdigest(),
                   node_provenance["runtime"]["zlib_version"]]
    try:
        wrapper_value = json.loads(node_runtime["wrapper"]["stdout"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AssessmentFailure("El wrapper Node no devolvió una prueba JSON válida.") from exc
    if (set(node_runtime) != {"wheel_node_is_link", "wheel_node_target", "system_node_is_regular",
                             "system_node_sha256", "executable_sha256", "license_sha256",
                             "zlib_link_target", "zlib_sha256", "ldd", "direct", "wrapper"}
            or node_runtime["wheel_node_is_link"] is not True
            or node_runtime["wheel_node_target"] != "/usr/bin/node"
            or node_runtime["system_node_is_regular"] is not True
            or node_runtime["system_node_sha256"] != bind_system_node.SYSTEM_NODE_SHA256
            or node_runtime["executable_sha256"] != bind_system_node.WHEEL_EXECUTABLE_SHA256
            or node_runtime["license_sha256"] != bind_system_node.WHEEL_LICENSE_SHA256
            or node_runtime["zlib_link_target"] != "libz.so.1.3.2"
            or node_runtime["zlib_sha256"] != alpine["runtime_files"][bind_system_node.ZLIB_REAL_PATH]
            or re.search(r"^\s*libz\.so\.1\s+=>\s+/usr/lib/libz\.so\.1\s+\(",
                         node_runtime["ldd"], re.MULTILINE) is None
            or node_runtime["direct"] != expected_js
            or node_runtime["wrapper"] != {"returncode": 0,
                                            "stdout": json.dumps(expected_js, separators=(",", ":")) + "\n",
                                            "stderr": ""}
            or wrapper_value != expected_js):
        raise AssessmentFailure("La prueba runtime Node no demuestra enlace, zlib, crypto y wrapper exactos.")
    stable = {archive: archive_sha, report_path: hashlib.sha256(report_raw).hexdigest(),
              summary_path: hashlib.sha256(summary_raw).hexdigest(),
              **{root / value["path"]: value["sha256"] for value in proofs.values()}}
    if any(_sha(path) != digest for path, digest in stable.items()):
        raise AssessmentFailure("Una entrada retenida cambió durante la evaluación.")
    try:
        database_verifier(db_paths, receipt_sha, image_archive_audit.LINUX_GRYPE_SHA256,
                          image_archive_audit.LINUX_ARCHIVE_SHA256)
    except image_audit.ImageAuditFailure as exc:
        raise AssessmentFailure("La identidad de DB cambió durante la evaluación.") from exc
    context_validator(context, root)
    output = output_path if output_path.is_absolute() else root / output_path
    evidence = (root / ".cuaderno-runs").resolve(strict=True)
    if output.exists() or output.is_symlink() or output.parent.resolve(strict=True) != evidence:
        raise AssessmentFailure("La salida debe ser nueva, regular y directa en .cuaderno-runs.")
    result = {
        "schema_version": 1, "status": ASSESSMENT_POLICY, "raw_scanner_status": "findings",
        "raw_scanner_exit": 2, "candidate_id": context["candidate_id"], "image_id": context["image_id"],
        "source_identity": context["source_identity"], "archive_sha256": archive_sha,
        "raw_report_sha256": hashlib.sha256(report_raw).hexdigest(),
        "raw_summary_sha256": hashlib.sha256(summary_raw).hexdigest(), "archive_binding": binding,
        "assessor_sha256": _sha(Path(__file__).resolve()), "policy": ASSESSMENT_POLICY,
        "proofs": proofs, "fingerprints": [fingerprints[key] for key in sorted(fingerprints)],
        "raw_matches": raw_matches, "ignored_matches": [], "runtime_proof": runtime,
        "database_provision": database_provision,
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
        stream.flush(); os.fsync(stream.fileno())
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--raw-report", required=True, type=Path)
    parser.add_argument("--raw-summary", required=True, type=Path)
    parser.add_argument("--proof", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = assess(context_path=args.context, archive=args.archive, report_path=args.raw_report,
                        summary_path=args.raw_summary, proof_paths=args.proof,
                        output_path=args.output)
        print("CUADERNO_IMAGE_SECURITY_ASSESSMENT " + json.dumps({
            "status": result["status"], "output": str(args.output),
            "matches": len(result["raw_matches"]),
        }, sort_keys=True))
        return 0
    except (AssessmentFailure, candidate_context.CandidateFailure, image_audit.ImageAuditFailure,
            OSError, subprocess.SubprocessError, UnicodeError, KeyError, TypeError) as exc:
        print(f"CUADERNO_IMAGE_SECURITY_ASSESSMENT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
