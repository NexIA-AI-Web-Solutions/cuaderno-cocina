"""Remove unused npm/corepack build tooling from the pinned image dependency.

pytubefix executes bin/node through nodejs_wheel.executable. It never installs
npm packages. The frontend uses a separate, pinned Node build stage.
"""
from importlib import metadata
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess


def prune_build_tools(root: Path) -> dict:
    if root.name != "nodejs_wheel" or not stat.S_ISDIR(root.lstat().st_mode) or root.is_symlink():
        raise ValueError("Unexpected Node wheel module root")
    root = root.resolve(strict=True)
    node = root / "bin/node"
    if node.is_symlink() or not node.is_file() or not node.resolve().is_relative_to(root):
        raise ValueError("Missing confined Node interpreter")
    before = hashlib.sha256(node.read_bytes()).hexdigest()
    targets = [root / relative for relative in (
        "lib/node_modules", "include", "bin/npm", "bin/npx", "bin/corepack",
    )]
    # Validate every destination before deleting any of this disposable build tree.
    for target in targets:
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ValueError("Build tool path escaped the Node wheel")
    removed = []
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(target.relative_to(root).as_posix())
        elif target.exists():
            target.unlink()
            removed.append(target.relative_to(root).as_posix())
    if hashlib.sha256(node.read_bytes()).hexdigest() != before:
        raise ValueError("Node interpreter changed during build tool pruning")
    return {"node_sha256": before, "removed": removed}


def main():
    distribution = metadata.distribution("nodejs-wheel-binaries")
    if distribution.version != "24.19.0":
        raise ValueError("Unexpected Node wheel dependency version")
    root = Path(distribution.locate_file("nodejs_wheel"))
    record = prune_build_tools(root)
    version = subprocess.check_output([str(root / "bin/node"), "--version"], text=True).strip()
    if version != "v24.19.0":
        raise ValueError("Unexpected retained Node interpreter version")
    result = subprocess.check_output([
        str(root / "bin/node"), "--eval",
        "console.log(JSON.stringify([2+3,require('node:crypto').createHash('sha256').update('cuaderno').digest('hex')]))",
    ], text=True).strip()
    if json.loads(result) != [5, hashlib.sha256(b"cuaderno").hexdigest()]:
        raise ValueError("Retained Node interpreter failed execution check")
    print("NODE_RUNTIME_PRUNED " + json.dumps({**record, "version": version}, sort_keys=True))


if __name__ == "__main__":
    main()
