import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from scripts.cuaderno.verify_loaded_image import verify


class LoadedImageTests(unittest.TestCase):
    def setUp(self):
        self.config = 'sha256:' + 'a' * 64
        self.manifest = 'sha256:' + 'b' * 64
        self.source = 'c' * 40 + '+worktree.' + 'd' * 64
        self.binding = {'config_digest': self.config, 'manifest_digest': self.manifest,
                        'chain': [self.manifest, self.config]}

    def inspect(self, args, **_kwargs):
        reference = args[-1]
        if reference == self.config:
            return SimpleNamespace(returncode=1, stdout='')
        return SimpleNamespace(returncode=0, stdout=json.dumps([{
            'Id': self.manifest, 'Config': {'Labels': {'io.cuaderno.source-identity': self.source}},
        }]))

    def test_containerd_manifest_is_accepted_only_from_verified_archive_chain(self):
        result = verify(Path('archive'), self.config, self.source, inspector=self.inspect,
                        binder=lambda *_args, **_kwargs: self.binding)
        self.assertEqual(result['local_image_id'], self.manifest)
        self.assertEqual(result['archive_image_id'], self.config)

    def test_wrong_source_and_unrelated_id_are_rejected(self):
        for key, value in [('Id', 'sha256:' + 'e' * 64), ('Config', {'Labels': {'io.cuaderno.source-identity': 'other'}})]:
            def inspector(_args, **_kwargs):
                info = {'Id': self.config, 'Config': {'Labels': {'io.cuaderno.source-identity': self.source}}}
                info[key] = value
                return SimpleNamespace(returncode=0, stdout=json.dumps([info]))
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(Path('archive'), self.config, self.source, inspector=inspector,
                       binder=lambda *_args, **_kwargs: self.binding)
