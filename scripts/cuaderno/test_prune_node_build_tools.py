"""Only the image's unused package managers and headers may be removed."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


class PruneNodeBuildToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "nodejs_wheel"
        for relative, content in (
            ("bin/node", b"preserve interpreter"), ("bin/npm", b"npm launcher"),
            ("bin/npx", b"npx launcher"), ("bin/corepack", b"corepack launcher"),
            ("lib/node_modules/npm/package.json", b"unused npm"),
            ("lib/node_modules/corepack/package.json", b"unused corepack"),
            ("include/node/node.h", b"build header"), ("executable.py", b"preserve Python wrapper"),
            ("share/doc/node/LICENSE", b"preserve upstream license"),
        ):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        location = Path(__file__).with_name("prune_node_build_tools.py")
        spec = importlib.util.spec_from_file_location("node_prune", location)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_pruning_preserves_interpreter_wrapper_and_license(self):
        node_before = (self.root / "bin/node").read_bytes()
        self.module.prune_build_tools(self.root)
        self.assertEqual((self.root / "bin/node").read_bytes(), node_before)
        self.assertEqual((self.root / "executable.py").read_bytes(), b"preserve Python wrapper")
        self.assertEqual((self.root / "share/doc/node/LICENSE").read_bytes(), b"preserve upstream license")
        for target in ("lib/node_modules", "include", "bin/npm", "bin/npx", "bin/corepack"):
            self.assertFalse((self.root / target).exists(), target)
        self.module.prune_build_tools(self.root)
        self.assertEqual((self.root / "bin/node").read_bytes(), node_before)

    def test_wrong_module_root_is_rejected_before_writes(self):
        other = self.root.rename(self.root.with_name("different_module"))
        with self.assertRaises(ValueError):
            self.module.prune_build_tools(other)
        self.assertTrue((other / "lib/node_modules/npm/package.json").is_file())

    def test_missing_interpreter_is_rejected_before_writes(self):
        (self.root / "bin/node").unlink()
        with self.assertRaises(ValueError):
            self.module.prune_build_tools(self.root)
        self.assertTrue((self.root / "lib/node_modules/npm/package.json").is_file())


if __name__ == "__main__":
    unittest.main()
