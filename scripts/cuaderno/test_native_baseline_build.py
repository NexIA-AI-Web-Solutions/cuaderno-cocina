from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from scripts.cuaderno import native_baseline_build as subject

PARENT = 'sha256:' + '7' * 64
NATIVE = 'sha256:' + '9' * 64
LAYER = 'sha256:' + '1' * 64
SOURCE = {**{name: b'pinned native bytes\n' for name in subject.FILES},
          'cookbook/models.py': b'native cookbook\n', 'recipes/settings.py': b'native settings\n',
          'http.d/Recipes.conf.template': b'native nginx\n'}
DEPENDENCIES = {'venv_sha256': 'a' * 64, 'interpreter_sha256': 'b' * 64, 'python': '3.13',
                'distributions': [['Django', '6.0']], 'pip_check': True}


def archive(files=SOURCE, extra=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tar:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
        if extra is not None:
            tar.addfile(extra)
    return stream.getvalue()


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.pin = subject.PIN
        self.source_archive = archive()
        self.native_files = subject.source_manifest(SOURCE)['files']
        self.native_dependencies = DEPENDENCIES
        self.native_installed = False
        self.native_user = '10001:10001'
        self.native_layers = [LAYER, 'sha256:' + '2' * 64]
        self.native_pin = subject.PIN
        self.parent_tag_id = PARENT
        self.probe_duplicate_marker = False
        self.build_iid = NATIVE
        self.connectors_disabled = True

    def __call__(self, argv, **kwargs):
        argv = list(argv)
        self.calls.append(argv)
        output = b''
        if argv[:2] == ['git', 'rev-parse']:
            output = self.pin.encode()
        elif argv[:2] == ['git', 'archive']:
            output = self.source_archive
        elif argv[:3] == ['docker', 'image', 'inspect']:
            image = argv[3]
            if image.startswith('cuaderno-native-baseline:'):
                output = NATIVE.encode()
            elif image.startswith('cuaderno-native-parent:'):
                output = self.parent_tag_id.encode()
            else:
                labels = {} if image == PARENT else {
                    'io.cuaderno.native-source-pin': self.native_pin,
                    'io.cuaderno.native-runtime-parent': PARENT,
                    'io.cuaderno.source-identity': self.native_pin,
                }
                output = json.dumps({'Id': image, 'RootFS': {'Layers': [LAYER] if image == PARENT else self.native_layers},
                                     'Config': {'Labels': labels, 'User': self.native_user}}).encode()
        elif argv[:2] == ['docker', 'run']:
            output = b'Running django-vite in production mode (no HMR)\nNATIVE_BASELINE_PROBE=' + json.dumps({'dependencies': DEPENDENCIES} if PARENT in argv else {
                'dependencies': self.native_dependencies, 'files': self.native_files,
                'cuaderno_installed': self.native_installed, 'django': '6.0',
                'external_connectors_disabled': self.connectors_disabled, 'django_setup': self.connectors_disabled,
            }).encode()
            if self.probe_duplicate_marker:
                output += b'\nNATIVE_BASELINE_PROBE={}\n'
        elif argv[:2] == ['docker', 'build']:
            Path(argv[argv.index('--iidfile') + 1]).write_text(self.build_iid)
        return SimpleNamespace(stdout=output, returncode=0)


class NativeBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / '.cuaderno-runs').mkdir()
        self.path = self.root / '.cuaderno-runs/native.json'
        self.proof = {'schema_version': 1, 'kind': 'cuaderno-native-pin-baseline', 'source_pin': subject.PIN,
                      'image_id': NATIVE, 'runtime_parent_image_id': PARENT, 'source': subject.source_manifest(SOURCE),
                      'dependencies': DEPENDENCIES, 'cuaderno_installed': False}
        self.path.write_text(json.dumps(self.proof))

    def verify(self, runner):
        return subject.verify_proof(NATIVE, self.path, parent_image=PARENT, root=self.root, process_runner=runner)

    def test_accepts_exact_pin_loaded_source_and_candidate_dependency_bytes(self):
        runner = FakeRunner()
        self.assertEqual(self.verify(runner), self.proof)
        self.assertIn(['git', 'archive', '--format=tar', subject.PIN, *subject.KINDS], runner.calls)
        probes = [argv for argv in runner.calls if argv[:2] == ['docker', 'run']]
        self.assertEqual(len(probes), 2)
        for command in probes:
            self.assertIn('--read-only', command)
            self.assertEqual(command[command.index('--network') + 1], 'none')
        self.assertIn("assert all(app.split('.')[0] != 'cuaderno'", probes[-1][-1])
        self.assertIn("django.setup()", probes[-1][-1])

    def test_rejects_source_pin_and_manifest_tampering_before_image_probes(self):
        for field, value in [('source_pin', 'b' * 40), ('source', {'files': {}, 'sha256': 'a' * 64}),
                             ('runtime_parent_image_id', 'sha256:' + '8' * 64)]:
            proof = {**self.proof, field: value}
            self.path.write_text(json.dumps(proof))
            runner = FakeRunner()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'prueba nativa'):
                self.verify(runner)
            self.assertFalse(any(argv[0] == 'docker' for argv in runner.calls))

    def test_rejects_loaded_cuaderno_source_even_with_native_labels(self):
        runner = FakeRunner()
        runner.native_files = {**runner.native_files, 'recipes/settings.py': 'e' * 64}
        with self.assertRaisesRegex(ValueError, 'bytes/dependencias'):
            self.verify(runner)
        runner = FakeRunner()
        runner.native_installed = True
        with self.assertRaisesRegex(ValueError, 'bytes/dependencias'):
            self.verify(runner)

    def test_rejects_different_runtime_dependencies_and_non_native_layer_ancestry(self):
        runner = FakeRunner()
        runner.native_dependencies = {**DEPENDENCIES, 'venv_sha256': 'c' * 64}
        with self.assertRaisesRegex(ValueError, 'bytes/dependencias'):
            self.verify(runner)
        runner = FakeRunner()
        runner.native_layers = ['sha256:' + 'f' * 64]
        with self.assertRaisesRegex(ValueError, 'runtime candidato'):
            self.verify(runner)

    def test_rejects_root_runtime_identity_even_if_source_hashes_match(self):
        runner = FakeRunner()
        runner.native_user = 'root'
        with self.assertRaisesRegex(ValueError, 'root'):
            self.verify(runner)

    def test_missing_git_pin_and_unsafe_archive_entries_never_build(self):
        runner = FakeRunner()
        runner.pin = 'f' * 40
        with self.assertRaisesRegex(ValueError, 'pin exacto'):
            subject.source_files(self.root, process_runner=runner)
        for name, kind in [('cookbook/link', tarfile.SYMTYPE), ('../escape', tarfile.REGTYPE)]:
            extra = tarfile.TarInfo(name)
            extra.type = kind
            extra.linkname = '/other'
            runner = FakeRunner()
            runner.source_archive = archive(extra=extra)
            with self.subTest(name=name), self.assertRaises(ValueError):
                subject.source_files(self.root, process_runner=runner)
            self.assertFalse(any(argv[0] == 'docker' for argv in runner.calls))

    def test_build_only_in_ci_test_from_immutable_candidate(self):
        for environ, image in [({'CUADERNO_ENV': 'production', 'CI': 'true'}, PARENT),
                               ({'CUADERNO_ENV': 'test'}, PARENT),
                               ({'CUADERNO_ENV': 'test', 'CI': 'true'}, 'candidate:latest')]:
            runner = FakeRunner()
            with self.subTest(environ=environ), self.assertRaises(ValueError):
                subject.build(image, self.root / '.cuaderno-runs/new.json', root=self.root,
                              environ=environ, process_runner=runner)
            self.assertEqual(runner.calls, [])

    def test_builder_replaces_source_without_dependency_downloads_and_publishes_verified_proof(self):
        runner = FakeRunner()
        destination = self.root / '.cuaderno-runs/built.json'
        proof = subject.build(PARENT, destination, root=self.root,
                              environ={'CUADERNO_ENV': 'test', 'CI': 'true'}, process_runner=runner)
        self.assertEqual(proof['image_id'], NATIVE)
        self.assertEqual(json.loads(destination.read_text()), proof)
        command = next(argv for argv in runner.calls if argv[:2] == ['docker', 'build'])
        self.assertIn('--network=none', command)
        self.assertIn('--pull=false', command)
        dockerfile = Path(command[command.index('-f') + 1]).read_text()
        self.assertIn('/opt/recipes/cuaderno', dockerfile)
        self.assertIn('COPY native/ /opt/recipes/', dockerfile)
        self.assertIn('USER 10001:10001', dockerfile)
        self.assertNotIn('pip install', dockerfile)
        self.assertNotIn('yarn', dockerfile)
        self.assertFalse(any(argv[:2] in (['git', 'fetch'], ['docker', 'pull']) for argv in runner.calls))

    def test_invalid_built_source_does_not_publish_proof(self):
        runner = FakeRunner()
        runner.native_files = {}
        destination = self.root / '.cuaderno-runs/built.json'
        with self.assertRaisesRegex(ValueError, 'bytes/dependencias'):
            subject.build(PARENT, destination, root=self.root,
                          environ={'CUADERNO_ENV': 'test', 'CI': 'true'}, process_runner=runner)
        self.assertFalse(destination.exists())

    def test_uses_loaded_tag_image_identity_when_builder_iid_is_a_different_manifest(self):
        runner = FakeRunner()
        runner.build_iid = 'sha256:' + '4' * 64
        destination = self.root / '.cuaderno-runs/built.json'
        proof = subject.build(PARENT, destination, root=self.root,
                              environ={'CUADERNO_ENV': 'test', 'CI': 'true'}, process_runner=runner)
        self.assertEqual(proof['image_id'], NATIVE)
        self.assertEqual(proof['build_iid'], runner.build_iid)
        command = next(argv for argv in runner.calls if argv[:2] == ['docker', 'build'])
        self.assertEqual(command[command.index('--tag') + 1], proof['retained_tag'])

    def test_native_connector_setting_is_checked_before_django_setup_and_proof_acceptance(self):
        self.assertIn("if connectors_disabled:\n    django.setup()", subject.NATIVE_PROBE)
        runner = FakeRunner()
        runner.connectors_disabled = False
        with self.assertRaisesRegex(ValueError, 'conectores'):
            self.verify(runner)

    def test_rogue_duplicate_marker_prevents_verification_and_proof_publication(self):
        runner = FakeRunner()
        runner.probe_duplicate_marker = True
        with self.assertRaisesRegex(ValueError, 'prueba única'):
            self.verify(runner)
        destination = self.root / '.cuaderno-runs/built.json'
        with self.assertRaisesRegex(ValueError, 'prueba única'):
            subject.build(PARENT, destination, root=self.root,
                          environ={'CUADERNO_ENV': 'test', 'CI': 'true'}, process_runner=runner)
        self.assertFalse(destination.exists())
        self.assertFalse(any(argv[:2] == ['docker', 'build'] for argv in runner.calls))

    def test_upgrade_uses_verified_native_pin_for_real_fixture_phases_without_historical_image(self):
        from scripts.cuaderno import upgrade_smoke
        suffix = 'abcdef123456'
        retained = 'cuaderno-cocina:upgrade-' + suffix
        class UpgradeRunner(FakeRunner):
            def __call__(self, argv, **kwargs):
                if not kwargs.get('text'):
                    return super().__call__(argv, **kwargs)
                argv = list(argv)
                self.calls.append(argv)
                stdout = ''
                if argv[:3] == ['docker', 'image', 'inspect']:
                    stdout = '10001:10001' if argv[-1] == '{{.Config.User}}' else PARENT
                return SimpleNamespace(stdout=stdout + '\n', returncode=0)
        runner = UpgradeRunner()
        source = 'a' * 40 + '+worktree.' + 'b' * 64
        context = self.root / '.cuaderno-runs/candidate.json'
        context.write_text(json.dumps({'image_id': PARENT, 'source_identity': source}))
        environ = {'CUADERNO_ENV': 'test', 'CUADERNO_CANDIDATE_IMAGE': PARENT,
                   'CUADERNO_SOURCE_IDENTITY': source, 'CUADERNO_CANDIDATE_CONTEXT': str(context),
                   'CUADERNO_NATIVE_BASELINE_IMAGE': NATIVE, 'CUADERNO_NATIVE_BASELINE_PROOF': str(self.path)}
        uuids = [SimpleNamespace(hex='password-secret'), SimpleNamespace(hex=suffix)]
        with patch.object(upgrade_smoke, 'ROOT', self.root), patch.object(upgrade_smoke.uuid, 'uuid4', side_effect=uuids):
            self.assertEqual(upgrade_smoke.main(environ=environ, process_runner=runner,
                                               context_validator=lambda *_: None), 0)
        pin_commands = [argv for argv in runner.calls if any('cuaderno-upgrade-' + suffix + '-pin' in part for part in argv)
                        and argv[1] in ('run', 'create')]
        self.assertEqual(len(pin_commands), 3)
        for argv in pin_commands:
            self.assertIn(NATIVE, argv)
        self.assertFalse(any(upgrade_smoke.PIN_IMAGE in argv or upgrade_smoke.PIN_IMAGE_ID in argv for argv in runner.calls))
        verified_probe_index = max(i for i, argv in enumerate(runner.calls) if subject.NATIVE_PROBE in argv[-1])
        create_network_index = next(i for i, argv in enumerate(runner.calls) if argv[:3] == ['docker', 'network', 'create'])
        self.assertLess(verified_probe_index, create_network_index)
        self.assertIn(retained, next(argv for argv in runner.calls if argv[:2] == ['docker', 'create'] and '-release' in argv[3]))

    def test_proof_outside_evidence_and_symlinks_are_rejected(self):
        runner = FakeRunner()
        outside = self.root / 'outside.json'
        outside.write_text(json.dumps(self.proof))
        with self.assertRaisesRegex(ValueError, '.cuaderno-runs'):
            subject.verify_proof(NATIVE, outside, parent_image=PARENT, root=self.root, process_runner=runner)
        linked = self.root / '.cuaderno-runs/link.json'
        linked.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'enlaces'):
            subject.verify_proof(NATIVE, linked, parent_image=PARENT, root=self.root, process_runner=runner)
        self.assertEqual(runner.calls, [])


if __name__ == '__main__':
    unittest.main()
