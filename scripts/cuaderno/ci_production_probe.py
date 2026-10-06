"""One-day external diagnostic of the exact retained 225 production image; not G7."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import uuid

try:
    from . import candidate_context, ci_release_gate, image_archive_audit
except ImportError:
    import candidate_context
    import ci_release_gate
    import image_archive_audit

ROOT = Path(__file__).resolve().parents[2]
BASE = '2257385ca4a486ad6bd726b644a960a800588177'
SOURCE = BASE + '+worktree.3cfe7f24da68728580e13b32fb8302ec0aa660f5247ad4638efb8f62219c3df8'
IMAGE = 'sha256:6b2a0e524fb59fe120424beebfd96cc16b55cf9400613e0af1591cbc36de80aa'
ARCHIVE_SHA = 'b230bfd19b2f1db3a07202db81ee4aaa04bd806e72b62e42c7e402472f719d22'
GATE_SHA = 'bf9bb66bb588b53187470f94227243f638350afaa461fbfed1eea7c69cf29933'
ALLOWED_CHANGES = {'.github/workflows/cuaderno-production-probe.yml',
                   'scripts/cuaderno/ci_production_probe.py', 'scripts/cuaderno/ci_release_gate.py'}
ARTIFACTS = {
    'frontend_provenance': '3525da09201409faff1504533b4ef2141df96db132b04617db970de2e14850bf',
    'runtime_application': '7e733143a690c5296de4fc533be86f110a9f4440aa1fc526854abbb7d966687c',
    'sbom_frontend': 'b0097683f8526a35dd1fc7cf658a4f524b84b941a2eac3da77862e562d7758e9',
    'sbom_python': '96a053f14f18856ad03df0539e92fbcb5a7b3c712a1d8ea2b01dacbbc7525ee9',
    'security_alpine_backports': 'dc9eecdca7a63291a8cdd11d0d1f8cc30cd92d9839536a13950d763eb8f7150d',
    'security_node_runtime': '247a31fcdf35022701f129aaf3fd976d6bebf700a0871b7c5cb07080606c3884',
    'security_python_backports': 'd84b11bd95f86354ac91c07a759d558e97c0d4a2663f5736cdc338bbd7c0de09',
    'version_info': '8f1ceeb77972a01e517d92da4547e397dc900ee02ec49a2b1040d07933befa7d',
}


def command(argv, *, timeout=60):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, check=False, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Diagnostic command failed; output retained only inside the process.')
    return result.stdout


def digest(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular diagnostic input.')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_source():
    if (os.environ.get('CI') not in {'true', '1'} or os.environ.get('CUADERNO_ENV') != 'test'
            or os.environ.get('GITHUB_REPOSITORY') != 'NexIA-AI-Web-Solutions/cuaderno-cocina'
            or os.environ.get('GITHUB_REF') != 'refs/heads/cuaderno-production-probe-20261006'
            or datetime.now(timezone.utc).date().isoformat() != '2026-10-06'):
        raise ValueError('Probe is limited to its authorized disposable CI branch and date.')
    command(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'])
    changed = set(command(['git', 'diff', '--name-only', BASE, '--']).decode().splitlines())
    untracked = set(command(['git', 'ls-files', '--others', '--exclude-standard']).decode().splitlines())
    if (changed | untracked) - ALLOWED_CHANGES:
        raise ValueError('Runtime source differs from the exact diagnostic baseline.')
    if digest(ROOT / 'scripts/cuaderno/ci_release_gate.py') != GATE_SHA:
        raise ValueError('Diagnostic instrumentation differs from its reviewed bytes.')


def verify_runner():
    available = next(int(line.split()[1]) * 1024 for line in
                     Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    if available <= 5 * 1024 ** 3 or shutil.disk_usage(ROOT).free <= 20 * 1024 ** 3:
        raise ValueError('Disposable runner lacks the required memory or disk headroom.')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 18082))
    if command(['docker', 'container', 'ls', '--all', '--quiet']).strip():
        raise ValueError('Probe requires a runner with no existing containers.')
    if command(['docker', 'volume', 'ls', '--quiet']).strip():
        raise ValueError('Probe requires a runner with no existing volumes.')
    networks = set(command(['docker', 'network', 'ls', '--format', '{{.Name}}']).decode().splitlines())
    if networks - {'bridge', 'host', 'none'}:
        raise ValueError('Probe requires a runner with no existing project networks.')


def verify_artifacts():
    directory = ROOT / '.cuaderno-runs'
    archive = directory / 'candidate-image.tar.gz'
    if (digest(archive) != ARCHIVE_SHA
            or (directory / 'candidate-image.tar.gz.sha256').read_text().split()[0] != ARCHIVE_SHA
            or (directory / 'candidate-image-id.txt').read_text().strip() != IMAGE
            or (directory / 'candidate-source-identity.txt').read_text().strip() != SOURCE):
        raise ValueError('Retained archive identity does not match its independent pins.')
    context, _ = image_archive_audit.shared._read_json_file(
        directory / 'ci-context.json', limit=4 * 1024 * 1024, label='Diagnostic CI context')
    image = context.get('environment', {}).get('image', {})
    if (context.get('schema_version') != 1
            or context.get('git_commit') != BASE or context.get('image_id') != IMAGE
            or context.get('source_identity') != SOURCE
            or context.get('source_sha256') != SOURCE.split('+worktree.')[1]
            or image.get('image_id') != IMAGE or image.get('os') != 'linux'
            or image.get('architecture') != 'amd64'
            or image.get('labels', {}).get('io.cuaderno.source-identity') != SOURCE
            or image.get('artifacts') != ARTIFACTS
            or image.get('release_manifest') != {
                'schema_version': 1, 'source_identity': SOURCE, 'artifacts': ARTIFACTS}):
        raise ValueError('Retained image/context artifact binding does not match the pinned candidate.')
    binding = image_archive_audit._archive_binding(archive, image_id=IMAGE, source_ref=SOURCE)
    if binding['config_digest'] != IMAGE:
        raise ValueError('Archive config digest does not match the pinned runner ImageID.')
    return archive


def read_stopped_file(container, remote):
    copier = subprocess.Popen(['docker', 'cp', container + ':' + remote, '-'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    output = bytearray()
    try:
        while chunk := copier.stdout.read(1024 * 1024):
            output.extend(chunk)
            if len(output) > 64 * 1024 * 1024:
                raise ValueError('Image artifact exceeds the bounded diagnostic copy.')
        copier.stdout.close()
        if copier.wait(timeout=10) != 0:
            raise RuntimeError('Could not copy the stopped image artifact.')
    finally:
        copier.stdout.close()
        try:
            copier.wait(timeout=10)
        except subprocess.TimeoutExpired:
            copier.terminate()
            try:
                copier.wait(timeout=5)
            except subprocess.TimeoutExpired:
                copier.kill()
                copier.wait(timeout=5)
    with tarfile.open(fileobj=io.BytesIO(output), mode='r:', ignore_zeros=True) as archive:
        members = archive.getmembers()
        if (len(members) != 1 or not members[0].isfile() or members[0].issparse()
                or members[0].size > 64 * 1024 * 1024
                or members[0].name != Path(remote).name):
            raise ValueError('Image copy must contain one exact regular artifact.')
        with archive.extractfile(members[0]) as stream:
            return stream.read()


def verify_loaded_artifact_bytes():
    name = 'cuaderno-production-inspect-' + uuid.uuid4().hex[:12]
    label_key = 'io.cuaderno.production-probe'
    try:
        command(['docker', 'create', '--name', name, '--label', label_key + '=' + name,
                 '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                 '--security-opt', 'no-new-privileges:true', '--entrypoint', '/bin/true', IMAGE])
        if set(candidate_context.IMAGE_ARTIFACTS) != set(ARTIFACTS):
            raise ValueError('Pinned diagnostic artifact set differs from the baseline helper.')
        actual = {key: hashlib.sha256(read_stopped_file(name, path)).hexdigest()
                  for key, path in candidate_context.IMAGE_ARTIFACTS.items()}
        manifest = image_archive_audit.shared._strict_json_bytes(
            read_stopped_file(name, candidate_context.RELEASE_MANIFEST), 'Image release manifest')
        if (actual != ARTIFACTS or manifest != {
                'schema_version': 1, 'source_identity': SOURCE, 'artifacts': ARTIFACTS}):
            raise ValueError('Actual image artifacts or release manifest differ from independent pins.')
        return actual
    finally:
        present = command(['docker', 'container', 'ls', '--all', '--no-trunc',
                           '--filter', 'name=^/' + name + '$', '--quiet']).decode().strip()
        if present:
            info = image_archive_audit.shared._strict_json_bytes(
                command(['docker', 'container', 'inspect', present]), 'Owned stopped inspection container')
            if (not isinstance(info, list) or len(info) != 1
                    or info[0].get('Id') != present or info[0].get('Name') != '/' + name
                    or info[0].get('Image') != IMAGE or info[0].get('State', {}).get('Running') is not False
                    or info[0].get('Config', {}).get('Labels', {}).get(label_key) != name):
                raise ValueError('Inspection container ownership/stopped state is not verified.')
            command(['docker', 'container', 'rm', present])


def main():
    phase, passed, error_type = 'source-guard', False, None
    try:
        verify_source()
        phase = 'runner-guard'
        verify_runner()
        phase = 'artifact-guard'
        archive = verify_artifacts()
        phase = 'image-load'
        command(['docker', 'image', 'load', '--input', str(archive)], timeout=600)
        info = image_archive_audit.shared._strict_json_bytes(
            command(['docker', 'image', 'inspect', IMAGE]), 'Diagnostic loaded image')
        if (not isinstance(info, list) or len(info) != 1 or info[0].get('Id') != IMAGE
                or info[0].get('Os') != 'linux' or info[0].get('Architecture') != 'amd64'
                or info[0].get('Config', {}).get('Labels', {}).get('io.cuaderno.source-identity') != SOURCE):
            raise ValueError('Loaded image does not match the pinned candidate.')
        phase = 'image-artifact-bytes'
        verify_loaded_artifact_bytes()
        phase = 'production-round-trip'
        ci_release_gate.production_round_trip(IMAGE)
        phase, passed = 'complete', True
        return 0
    except Exception as exc:
        error_type = type(exc).__name__
        print('Production diagnostic failed: ' + error_type, file=sys.stderr)
        return 1
    finally:
        directory = ROOT / '.cuaderno-runs'
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
        summary = {'kind': 'cuaderno-production-diagnostic', 'release_certification': False,
                   'passed': passed, 'phase': phase, 'candidate_image_id': IMAGE,
                   'candidate_source_identity': SOURCE, 'archive_sha256': ARCHIVE_SHA}
        if error_type:
            summary['error_type'] = error_type
        with (directory / 'production-probe-summary.json').open('x') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(summary, stream, sort_keys=True)
            stream.write('\n')


if __name__ == '__main__':
    raise SystemExit(main())
