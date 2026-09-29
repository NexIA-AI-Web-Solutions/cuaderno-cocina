#!/usr/bin/env python3
"""Apply the upstream PKCE timing fix to the pinned oauthlib 3.3.1 wheel.

Provenance: oauthlib/oauthlib commit 40b0ab56da3682c2484a4b78bbff309f8025d950,
distributed under oauthlib's BSD-3-Clause license. This deliberately patches
only the installed 3.3.1 file whose complete bytes match the published wheel.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import stat
import sys
import tempfile
from pathlib import Path

TARGET_VERSION = "3.3.1"
TARGET_RELATIVE_PATH = Path("oauthlib/oauth2/rfc6749/grant_types/authorization_code.py")
ORIGINAL_SHA256 = "0d6931601c4e88a078fb3ccf5f052c035ad6a4bb2171efb9c218e088a7272dc6"
PATCHED_SHA256 = "53f308e800db1005c58fe17e7310ad695a62947363f725de8259f387fa841114"
ADVISORY_URL = "https://github.com/advisories/GHSA-xpv3-w29h-x7cv"
UPSTREAM_COMMIT_URL = (
    "https://github.com/oauthlib/oauthlib/commit/"
    "40b0ab56da3682c2484a4b78bbff309f8025d950"
)

_IMPORT_BEFORE = b"import hashlib\n"
_IMPORT_AFTER = b"import hashlib\nimport hmac\n"
_S256_BEFORE = (
    b"    return base64.urlsafe_b64encode(\n"
    b"        hashlib.sha256(verifier.encode()).digest()\n"
    b"    ).decode().rstrip('=') == challenge"
)
_S256_AFTER = (
    b"    expected = base64.urlsafe_b64encode(\n"
    b"        hashlib.sha256(verifier.encode()).digest()\n"
    b"    ).decode().rstrip('=')\n"
    b"    return hmac.compare_digest(expected, challenge)"
)
_PLAIN_BEFORE = b"    return verifier == challenge"
_PLAIN_AFTER = b"    return hmac.compare_digest(verifier, challenge)"


class PatchError(RuntimeError):
    """The installed dependency is not the exact supported patch target."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def require_supported_version(version: str) -> None:
    if version != TARGET_VERSION:
        raise PatchError(
            f"oauthlib version {version!r} is not supported; expected exactly {TARGET_VERSION}"
        )


def _replace_once(source: bytes, before: bytes, after: bytes, label: str) -> bytes:
    occurrences = source.count(before)
    if occurrences != 1:
        raise PatchError(f"unexpected {label} occurrence count: {occurrences}")
    return source.replace(before, after, 1)


def build_patched_source(source: bytes) -> bytes:
    """Return the exact upstream backport, rejecting all noncanonical input."""
    actual = _sha256(source)
    if actual != ORIGINAL_SHA256:
        raise PatchError(
            "oauthlib source does not match the 3.3.1 wheel: "
            f"expected {ORIGINAL_SHA256}, got {actual}"
        )
    patched = _replace_once(source, _IMPORT_BEFORE, _IMPORT_AFTER, "hashlib import")
    patched = _replace_once(patched, _S256_BEFORE, _S256_AFTER, "S256 comparison")
    patched = _replace_once(patched, _PLAIN_BEFORE, _PLAIN_AFTER, "plain comparison")
    actual_patched = _sha256(patched)
    if actual_patched != PATCHED_SHA256:
        raise PatchError(
            f"internal patched hash mismatch: expected {PATCHED_SHA256}, got {actual_patched}"
        )
    return patched


def _installed_target() -> tuple[str, Path]:
    try:
        version = importlib.metadata.version("oauthlib")
        distribution = importlib.metadata.distribution("oauthlib")
    except importlib.metadata.PackageNotFoundError as exc:
        raise PatchError("oauthlib is not installed") from exc
    require_supported_version(version)
    target = Path(distribution.locate_file(TARGET_RELATIVE_PATH)).resolve()
    if not target.is_file():
        raise PatchError(f"oauthlib target file is missing: {target}")
    return version, target


def _atomic_write(target: Path, content: bytes) -> None:
    original_mode = stat.S_IMODE(target.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, original_mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def patch_installed_oauthlib() -> tuple[str, str, Path]:
    version, target = _installed_target()
    source = target.read_bytes()
    current_sha256 = _sha256(source)
    if current_sha256 == PATCHED_SHA256:
        return "already-patched", version, target
    if current_sha256 != ORIGINAL_SHA256:
        raise PatchError(
            "refusing to modify unrecognized oauthlib bytes: "
            f"expected {ORIGINAL_SHA256} or {PATCHED_SHA256}, got {current_sha256}"
        )
    patched = build_patched_source(source)
    _atomic_write(target, patched)
    written_sha256 = _sha256(target.read_bytes())
    if written_sha256 != PATCHED_SHA256:
        raise PatchError(
            f"post-write verification failed: expected {PATCHED_SHA256}, got {written_sha256}"
        )
    return "patched", version, target


def main() -> int:
    try:
        status, version, _target = patch_installed_oauthlib()
    except (OSError, PatchError) as exc:
        print(f"oauthlib_patch error={exc}", file=sys.stderr)
        return 1
    print(
        f"oauthlib_patch status={status} version={version} "
        f"original_sha256={ORIGINAL_SHA256} post_sha256={PATCHED_SHA256} "
        f"advisory={ADVISORY_URL} upstream_commit={UPSTREAM_COMMIT_URL} "
        "source_license=BSD-3-Clause"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
