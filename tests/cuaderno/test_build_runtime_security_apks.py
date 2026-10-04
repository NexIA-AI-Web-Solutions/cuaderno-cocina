import importlib.util
from pathlib import Path
import shutil

import pytest


MODULE_PATH = Path(__file__).parents[2] / "scripts/cuaderno/build_runtime_security_apks.py"
SPEC = importlib.util.spec_from_file_location("build_runtime_security_apks", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(module)


def test_checked_inputs_reject_tampered_patch(tmp_path):
    source = Path(__file__).parents[2] / "docker/runtime-security"
    target = tmp_path / "runtime-security"
    shutil.copytree(source, target)
    module.load_inputs(target)
    patch = target / "aports/main/zlib/df84af25dc1942490e1d1c899a07619152a46148.patch"
    patch.write_bytes(patch.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        module.load_inputs(target)


def test_build_uses_pinned_linux_export_and_validates_artifacts(tmp_path):
    repo = Path(__file__).parents[2]
    output = repo / ".cuaderno-runs/test-runtime-security-export"
    if output.exists():
        shutil.rmtree(output)
    calls = []

    def runner(command, *, cwd, check):
        calls.append((command, cwd, check))
        package_dir = output / "packages/local/x86_64"
        package_dir.mkdir(parents=True)
        for name, version in module.EXPECTED_PACKAGES.items():
            (package_dir / f"{name}-{version}.apk").write_bytes(name.encode())
        for package in ("busybox", "zlib"):
            path = output / f"corresponding-source/aports/main/{package}"
            path.mkdir(parents=True)
            (path / "APKBUILD").write_text(package)
        source_manifest = output / "corresponding-source/source-inputs.json"
        source_manifest.write_text("{}\n")
        (output / "SHA256SUMS").write_text("checked\n")
        packages = {
            name: {"version": version, "apk_sha256": module.sha256(package_dir / f"{name}-{version}.apk")}
            for name, version in module.EXPECTED_PACKAGES.items()
        }
        (output / "SECURITY.alpine-backports.json").write_text(__import__("json").dumps({
            "packages": packages, "source_inputs_sha256": module.sha256(source_manifest),
            "runtime_files": {path: "0" * 64 for path in (
                "/bin/busybox", "/usr/bin/ssl_client", "/usr/lib/libz.so.1.3.2"
            )},
        }))

    try:
        result = module.build(repo, output, runner=runner)
        command, cwd, check = calls[0]
        assert command[:7] == ["docker", "buildx", "build", "--platform", "linux/amd64", "--target", "export"]
        assert cwd == repo and check is True
        assert set(result) == set(module.EXPECTED_PACKAGES)
    finally:
        if output.exists():
            shutil.rmtree(output)


def test_output_must_be_isolated_under_run_directory(tmp_path):
    repo = Path(__file__).parents[2]
    with pytest.raises(ValueError, match="below .cuaderno-runs"):
        module.build(repo, tmp_path / "outside", runner=lambda *a, **k: None)


def test_recipes_keep_distro_patch_stack_and_append_security_fixes():
    root = Path(__file__).parents[2] / "docker/runtime-security/aports/main"
    busybox = (root / "busybox/APKBUILD").read_text(encoding="utf-8")
    source_block = busybox.split('source="', 1)[1].split('"', 1)[0]
    distro_patches = [line.strip() for line in source_block.splitlines() if line.strip().endswith(".patch")]
    assert len(distro_patches) == 45
    assert distro_patches[-1] == "CVE-2025-60876.patch"
    assert "pkgrel=31" in busybox and "1.37.0-r31:" in busybox

    zlib = (root / "zlib/APKBUILD").read_text(encoding="utf-8")
    expected = [
        "df84af25dc1942490e1d1c899a07619152a46148.patch",
        "7235b0a581227c56a79a43ff828f8ef6794194c8.patch",
        "813dac5dcb5902ed241e9b0d38abd2d847a335a9.patch",
        "d81c2d7eb705c62294ba03299255672078e89115.patch",
    ]
    positions = [zlib.index(name) for name in expected]
    assert positions == sorted(positions)
    assert "pkgrel=1" in zlib and "1.3.2-r1:" in zlib
