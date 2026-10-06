"""Byte-bound product/component evidence for two retained Grype CPE matches."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

try:
    from . import image_audit
except ImportError:
    import image_audit


SOURCE_PINS = {
    'ada-cve.json': '907fc10c929382febdf42d6d86d8ce972c333a1bfe701650f4eb059a07c63060',
    'ada-APKBUILD': '64feedf6a627f24988d0d54ed1ed5e4a4c2b8fb298d2ba7f65386ed521a9b080',
    'nghttp2-APKBUILD': '617e1bb3ac747d847c8b46d13d205daf5f0a05491cfaffedf7a09f154e353f40',
    'nghttp2-commit.json': 'f8bb567e2a5eeff431354ee94b53a38ea5ad731f3ac32669b5fa952a4beb8e09',
}
PACKAGES = {
    'ada-libs': {
        'version': '3.3.0-r0', 'upstream': 'ada',
        'url': 'https://ada-url.github.io/ada',
        'aports_commit': 'd279ef8c31170898285e2a989f62909992bff448',
        'installed_block_sha256': '2ec0795617a342cef631dd0e80d6440886f76cffccc313dbd34e538949a7b395',
        'apk_url': 'https://dl-cdn.alpinelinux.org/alpine/v3.23/main/x86_64/ada-libs-3.3.0-r0.apk',
        'apk_sha256': '5afb61331b184c47e91d0637ecb706aaf30e9270e845a6c0417235bdec2009c1',
        'library': '/usr/lib/libada.so.3.3.0',
        'library_sha256': 'f7179a8fabac8058773bc11bb85521871821b9f653dd723a27f0f356a4f278bb',
    },
    'nghttp2-libs': {
        'version': '1.69.0-r0', 'upstream': 'nghttp2', 'url': 'https://nghttp2.org',
        'aports_commit': '40d265063c14143f5ef8a35c216b9e6392d120a7',
        'installed_block_sha256': 'db29bce005aa2f8ff56bb704aab7931630a2eb890cda24e8ea70de14c06e1b6f',
        'apk_url': 'https://dl-cdn.alpinelinux.org/alpine/v3.23/main/x86_64/nghttp2-libs-1.69.0-r0.apk',
        'apk_sha256': 'e52a5325b8720449ed4f123a33202794361b6b164c127abdb4b3c057467e7a41',
        'library': '/usr/lib/libnghttp2.so.14.29.4',
        'library_sha256': '61f33569051345681ae150ac573e50abce43d3c17853f6185dd5a7f78648d5a9',
    },
}
PROXY_PATHS = tuple(directory + '/nghttpx' for directory in
                    ('/bin', '/sbin', '/usr/bin', '/usr/sbin', '/usr/local/bin', '/usr/local/sbin'))
METADATA = {
    'source_sha256': SOURCE_PINS,
    'packages': PACKAGES,
    'decisions': {
        'CVE-2024-9410': {
            'kind': 'different-product', 'affected_vendor': 'Ada Support',
            'affected_product': 'Ada.cx Sentry Component',
            'record_url': 'https://cveawg.mitre.org/api/cve/CVE-2024-9410',
            'installed_project': 'https://github.com/ada-url/ada',
        },
        'CVE-2026-58055': {
            'kind': 'affected-proxy-absent',
            'fix_commit': 'ab28105c4a0197da24f8bfc414bc116055249e1e',
            'fix_url': 'https://github.com/nghttp2/nghttp2/commit/ab28105c4a0197da24f8bfc414bc116055249e1e',
            'fix_api_sha256': 'f8bb567e2a5eeff431354ee94b53a38ea5ad731f3ac32669b5fa952a4beb8e09',
            'changed_files': ['src/shrpx_downstream.cc', 'src/shrpx_downstream.h',
                              'src/shrpx_http2_upstream.cc', 'src/shrpx_http3_upstream.cc',
                              'src/shrpx_http_downstream_connection.cc',
                              'src/shrpx_http_downstream_connection.h', 'src/shrpx_https_upstream.cc'],
            'absent_paths': list(PROXY_PATHS),
        },
    },
}


def _primary_bytes(path: Path, root: Path) -> bytes:
    image_audit._reject_link_ancestors(path, root)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 0 < before.st_size <= 64 * 1024):
        raise ValueError('La fuente de alcance debe ser regular, acotada y sin hardlinks.')
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
                value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                         | getattr(os, 'O_CLOEXEC', 0))
    try:
        if identity(os.fstat(descriptor)) != identity(before):
            raise ValueError('La fuente de alcance cambió al abrirse.')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(64 * 1024 + 1)
        if (len(raw) != before.st_size or identity(os.fstat(descriptor)) != identity(before)
                or identity(path.lstat()) != identity(before)):
            raise ValueError('La fuente de alcance cambió durante su lectura.')
        return raw
    finally:
        os.close(descriptor)


def metadata(root: Path) -> dict:
    """Require the frozen primary record and official subpackage definitions."""
    directory = root / 'tooling/cuaderno/component-scope'
    documents = {}
    for name, digest in SOURCE_PINS.items():
        path = directory / name
        raw = _primary_bytes(path, root)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Una fuente primaria del alcance no conserva sus bytes fijados.')
        if name.endswith('.json'):
            documents[name] = image_audit._strict_json_bytes(raw, 'La fuente primaria de alcance')
    record = documents['ada-cve.json']
    affected = record['containers']['cna']['affected']
    if (record['cveMetadata']['cveId'] != 'CVE-2024-9410' or len(affected) != 1
            or affected[0]['vendor'] != 'Ada Support' or affected[0]['product'] != 'Ada.cx Sentry Component'):
        raise ValueError('El aviso Ada no conserva la identidad del producto afectado.')
    commit = documents['nghttp2-commit.json']
    decision = METADATA['decisions']['CVE-2026-58055']
    if (commit['sha'] != decision['fix_commit']
            or [row['filename'] for row in commit['files']] != decision['changed_files']):
        raise ValueError('El cambio upstream no conserva el alcance exclusivo del proxy.')
    return json.loads(json.dumps(METADATA))


def expected_runtime() -> dict:
    return {
        'package_blocks': {name: row['installed_block_sha256'] for name, row in PACKAGES.items()},
        'library_files': {row['library']: row['library_sha256'] for row in PACKAGES.values()},
        'nghttpx_absent_paths': list(PROXY_PATHS),
        'nghttpx_package_files_absent': True,
        'proxy_packages_absent': True,
    }
