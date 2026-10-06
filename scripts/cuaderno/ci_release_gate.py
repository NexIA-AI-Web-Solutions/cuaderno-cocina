"""Execute the remaining real candidate checks and aggregate exactly 17 records in CI."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tarfile
import urllib.request

try:
    from . import image_archive_audit as audit
except ImportError:
    import image_archive_audit as audit
try:
    from . import production_backup, production_restore_verify
except ImportError:
    import production_backup
    import production_restore_verify

ROOT = Path(__file__).resolve().parents[2]


def download(url, destination, digest):
    request = urllib.request.Request(url, headers={'User-Agent': 'cuaderno-ci-audit/1.0'})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open('xb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    with destination.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
            raise ValueError('El artefacto descargado no coincide con su pin.')


def provision_scanner():
    from types import SimpleNamespace

    directory = ROOT / 'data/cuaderno/tooling/grype-linux-0.119.0'
    db_root = ROOT / 'data/cuaderno/tooling/grype-db'
    audit.shared._reject_link_ancestors(directory, ROOT.resolve(strict=True))
    audit.shared._reject_link_ancestors(db_root, ROOT.resolve(strict=True))
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    archive = directory / 'grype_0.119.0_linux_amd64.tar.gz'
    download('https://github.com/anchore/grype/releases/download/v0.119.0/' + archive.name,
             archive, audit.LINUX_ARCHIVE_SHA256)
    with tarfile.open(archive) as source:
        member = source.getmember('grype')
        if not member.isfile():
            raise ValueError('El scanner no es un archivo regular.')
        (directory / 'grype').write_bytes(source.extractfile(member).read())
    if audit._sha256(directory / 'grype') != audit.LINUX_GRYPE_SHA256:
        raise ValueError('Hash de scanner incorrecto.')
    (directory / 'grype').chmod(0o700)
    db = directory / 'vulnerability-db.tar.zst'
    download(audit.shared.DB_ARCHIVE_SOURCE, db, audit.shared.VULNERABILITY_DB_ARCHIVE_SHA256)
    # Distribution bytes are pinned before the trusted importer adds indexes/statistics.
    decoder = subprocess.Popen(['zstd', '--decompress', '--stdout', str(db)],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    raw_hash = hashlib.sha256()
    members = 0
    try:
        with tarfile.open(fileobj=decoder.stdout, mode='r|', ignore_zeros=True) as source:
            for member in source:
                members += 1
                if members != 1 or member.name != 'vulnerability.db' or not member.isfile():
                    raise ValueError('El archivo DB debe contener solo vulnerability.db regular.')
                with source.extractfile(member) as stream:
                    while chunk := stream.read(1024 * 1024):
                        raw_hash.update(chunk)
        decoder.stdout.close()
        if decoder.wait(timeout=10) != 0:
            raise ValueError('No se pudo descomprimir el archivo DB fijado.')
    finally:
        decoder.stdout.close()
        try:
            decoder.wait(timeout=10)
        except subprocess.TimeoutExpired:
            decoder.terminate()
            try:
                decoder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                decoder.kill()
                decoder.wait(timeout=5)
    if members != 1 or raw_hash.hexdigest() != audit.shared.VULNERABILITY_DB_RAW_SHA256:
        raise ValueError('La base DB distribuida no coincide con su pin raw.')
    paths = SimpleNamespace(root=ROOT, tool=directory / 'grype', zip_archive=archive,
                            db_root=db_root, db_stamp=db_root / '6/import.json',
                            database=db_root / '6/vulnerability.db')
    environment = audit.shared._offline_environment(paths, os.environ)
    audit.shared._verify_grype(paths, subprocess.run, audit.LINUX_GRYPE_SHA256,
                               audit.LINUX_ARCHIVE_SHA256)
    paths.db_root.mkdir(mode=0o700, exist_ok=False)
    subprocess.run([str(directory / 'grype'), 'db', 'import', str(db)], check=True,
                   env=environment, timeout=audit.shared.SCAN_TIMEOUT_SECONDS)
    paths.database.parent.chmod(0o700)
    installed_hash = audit._sha256(paths.database)
    stamp, original_stamp = audit.shared._read_json_file(
        paths.db_stamp, limit=64 * 1024, label='DB stamp')
    audit.shared._db_stamp(paths, expected_stamp=stamp)
    status = audit.shared._verify_db_status(paths, subprocess.run, environment)
    stamp_hash = hashlib.sha256(original_stamp).hexdigest()
    if (audit._sha256(paths.database) != installed_hash
            or audit._sha256(paths.db_stamp) != stamp_hash
            or audit._sha256(paths.tool) != audit.LINUX_GRYPE_SHA256
            or audit._sha256(archive) != audit.LINUX_ARCHIVE_SHA256
            or audit._sha256(db) != audit.shared.VULNERABILITY_DB_ARCHIVE_SHA256):
        raise ValueError('Los artefactos del scanner cambiaron durante su provisión.')
    receipt = {
        'schema_version': 1, 'passed': True,
        'archive_url': audit.shared.DB_ARCHIVE_SOURCE,
        'archive_sha256': audit.shared.VULNERABILITY_DB_ARCHIVE_SHA256,
        'raw_database_sha256': raw_hash.hexdigest(),
        'scanner_binary_sha256': audit.LINUX_GRYPE_SHA256,
        'scanner_archive_sha256': audit.LINUX_ARCHIVE_SHA256,
        'scanner_version': audit.shared.GRYPE_VERSION,
        'scanner_commit': audit.shared.GRYPE_COMMIT,
        'installed_database_path': str(paths.database.resolve(strict=True)),
        'installed_database_sha256': installed_hash,
        'import_metadata_sha256': stamp_hash, 'import_metadata': stamp, 'status': status,
    }
    raw_receipt = (json.dumps(receipt, sort_keys=True, separators=(',', ':'),
                             allow_nan=False) + '\n').encode()
    receipt_directory = ROOT / '.cuaderno-runs'
    if receipt_directory.is_symlink():
        raise ValueError('El directorio de recibos no puede ser un enlace.')
    receipt_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt_directory.chmod(0o700)
    receipt_path = receipt_directory / 'scanner-db-provision.json'
    with receipt_path.open('xb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw_receipt)
    return hashlib.sha256(raw_receipt).hexdigest()


def restore_error_category(error: RuntimeError) -> str:
    """Reduce a bounded native error to a public enum; never retain its contents."""
    message = str(error)[-2000:].lower()
    categories = (
        ('connection_refused', ('connection refused',)),
        ('connection_closed', ('server closed the connection unexpectedly',
                               'connection to server was lost', 'connection reset by peer')),
        ('server_starting_or_stopping', ('the database system is starting up',
                                         'the database system is shutting down',
                                         'the database system is in recovery mode')),
        ('archive_invalid', ('did not find magic string in file header',
                              'input file does not appear to be a valid archive',
                              'input file is too short')),
        ('permission_error', ('permission denied', 'must be owner of')),
        ('sql_restore_error', ('could not execute query', 'errors ignored on restore')),
    )
    if re.search(r'database "[^"\r\n]+" does not exist', message):
        return 'database_missing'
    if 'unsupported version (' in message and 'in file header' in message:
        return 'archive_version_unsupported'
    for category, fragments in categories:
        if any(fragment in message for fragment in fragments):
            return category
    return 'other'


def production_round_trip(image_id):
    """Exercise the real production profile/tools on a fresh CI-only database."""
    class DiagnosticBoundary(production_restore_verify.RestoreBoundary):
        failed_operation = None
        restore_error_category = None

        @staticmethod
        def operation(argv):
            if argv[:2] == ['docker', 'compose']:
                category = 'compose'
                for action in ('exec', 'ps', 'stop', 'up'):
                    if action in argv:
                        category += '.' + action
                        break
            elif argv[:2] == ['docker', 'exec']:
                category = 'docker.exec'
            elif argv[:2] == ['docker', 'run']:
                category = 'docker.run'
            elif argv[:3] == ['docker', 'image', 'inspect']:
                return 'docker.image.inspect'
            elif argv[:2] == ['docker', 'inspect']:
                return 'docker.inspect'
            elif argv[:2] == ['docker', 'cp']:
                return 'docker.cp'
            elif argv[:2] == ['docker', 'stop']:
                return 'docker.stop'
            elif argv[:2] in (['docker', 'network'], ['docker', 'volume']):
                return 'docker.resource'
            else:
                return 'boundary.other'
            for tool in ('pg_dump', 'pg_restore', 'psql', 'pg_isready', 'tar', 'chown'):
                if tool in argv:
                    return category + '.' + tool
            if any(Path(argument).name == 'python' for argument in argv):
                return category + '.python-smoke'
            return category

        def tracked(self, method, argv, **kwargs):
            try:
                return method(argv, **kwargs)
            except Exception as exc:
                if self.failed_operation is None:
                    self.failed_operation = self.operation(argv)
                    if self.failed_operation == 'docker.exec.pg_restore' and isinstance(exc, RuntimeError):
                        self.restore_error_category = restore_error_category(exc)
                raise

        def run(self, argv, *, data=None):
            return self.tracked(super().run, argv, data=data)

        def run_to_file(self, argv, destination):
            return self.tracked(super().run_to_file, argv, destination=destination)

        def run_from_file(self, argv, source):
            return self.tracked(super().run_from_file, argv, source=source)

    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 18082))
    directory = ROOT / 'data/cuaderno/production-ci'
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    backups = directory / 'backups'
    backups.mkdir(mode=0o700)
    env = directory / 'production.env'
    env.write_text('\n'.join([
        'CUADERNO_IMAGE=' + image_id, 'CUADERNO_DOMAIN=127.0.0.1', 'CUADERNO_HTTP_PORT=18082',
        'CUADERNO_SECRET_KEY=' + secrets.token_hex(48), 'CUADERNO_DB_PASSWORD=' + secrets.token_hex(24),
    ]) + '\n')
    env.chmod(0o600)
    command = ['docker', 'compose', '--project-name', 'cuaderno-prod', '--env-file', str(env),
               '-f', 'deploy/cuaderno/compose.production.yml']
    report_directory = ROOT / '.cuaderno-runs'
    report_directory.mkdir(mode=0o700, exist_ok=True)
    report_directory.chmod(0o700)
    boundary = DiagnosticBoundary()
    phase, failure = 'startup', None
    cleanup = {'attempted': False, 'passed': False}
    try:
        subprocess.run([*command, 'up', '-d', '--wait', '--wait-timeout', '600'], cwd=ROOT, check=True)
        # Synthetic persisted media and recipe data; never a production deployment.
        fixture = """from django.contrib.auth import get_user_model
from django_scopes import scopes_disabled
from cookbook.models import Space, Recipe
from pathlib import Path
with scopes_disabled():
 user=get_user_model().objects.create_user(username='ci-recovery-synthetic')
 space=Space.objects.create(name='CI recovery synthetic')
 Recipe.objects.create(space=space,created_by=user,name='CI persisted recipe',private=True,servings=4)
Path('/opt/recipes/mediafiles/ci-recovery.txt').write_text('CI persisted media\\n')
"""
        phase = 'fixture'
        subprocess.run([*command, 'exec', '-T', 'web', '/opt/recipes/venv/bin/python', 'manage.py',
                        'shell', '-c', fixture], cwd=ROOT, check=True)
        phase = 'backup'
        bundle = production_backup.create_backup(env, backups, include_env=True, boundary=boundary)
        phase = 'restore'
        report = production_restore_verify.verify(bundle, runtime_image=image_id, boundary=boundary,
                    report_path=ROOT / '.cuaderno-runs/production-restore-report.json')
        if not report['passed']:
            raise ValueError('Restauración del perfil productivo no aprobada.')
        phase = 'manifest'
        (ROOT / '.cuaderno-runs/production-backup-manifest.json').write_bytes((bundle / 'manifest.json').read_bytes())
        phase = 'complete'
    except Exception as exc:
        failure = exc
        raise
    finally:
        cleanup['attempted'] = True
        try:
            subprocess.run([*command, 'stop'], cwd=ROOT, check=True)
            cleanup['passed'] = True
        except Exception as exc:
            cleanup['error_type'] = type(exc).__name__
            if failure is None:
                phase, failure = 'cleanup', exc
                raise
        finally:
            diagnostic = {'passed': failure is None, 'phase': phase,
                          'operation': boundary.failed_operation or phase, 'cleanup': cleanup}
            if failure is not None:
                diagnostic['error_type'] = type(failure).__name__
            if boundary.restore_error_category is not None:
                diagnostic['restore_error_category'] = boundary.restore_error_category
            with (report_directory / 'production-round-trip-diagnostic.json').open('x') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(diagnostic, stream, sort_keys=True)
                stream.write('\n')



def main():
    if os.environ.get('CI') not in {'true', '1'} or os.environ.get('CUADERNO_ENV') != 'test':
        raise SystemExit('Solo runner CI de pruebas aisladas.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path, required=True)
    args = parser.parse_args()
    context = json.loads(args.context.read_text())
    os.environ['CUADERNO_CANDIDATE_IMAGE'] = context['image_id']
    os.environ['CUADERNO_SCANNER_DB_RECEIPT_SHA256'] = provision_scanner()
    subprocess.run([sys.executable, 'scripts/cuaderno/native_baseline_build.py',
                    '--candidate-image', context['image_id'], '--proof', '.cuaderno-runs/native-baseline.json'],
                   cwd=ROOT, env={**os.environ, 'CI': 'true'}, check=True)
    native = json.loads((ROOT / '.cuaderno-runs/native-baseline.json').read_text())
    os.environ['CUADERNO_NATIVE_BASELINE_IMAGE'] = native['image_id']
    os.environ['CUADERNO_NATIVE_BASELINE_PROOF'] = '.cuaderno-runs/native-baseline.json'

    failed = []
    for check in ('migrations-final', 'schema-final', 'native-regression-final', 'integration-final',
                  'typecheck-final', 'security-final', 'performance-final', 'image-audit-linux',
                  'restore-final', 'rollback-final'):
        code = subprocess.run([sys.executable, 'scripts/cuaderno/candidate_check.py', check,
                               '--context', str(args.context), '--allow-isolated-mutations'], cwd=ROOT).returncode
        if code:
            failed.append(check)
    try:
        production_round_trip(context['image_id'])
    except Exception as exc:
        failed.append('production-backup-restore')
        print('Ensayo productivo de recuperación fallido: ' + type(exc).__name__, file=sys.stderr)
    # The image job supplies build + five artifact records; the root browser
    # job supplies its strict E2E record. Prefix acceptance is independently required.
    records = []
    for path in (ROOT / '.cuaderno-runs').glob('*.json'):
        value = json.loads(path.read_text())
        if value.get('command') and value.get('candidate_id') == context['candidate_id']:
            records.append(path)
    code = subprocess.run([sys.executable, 'scripts/cuaderno/release_manifest_collect.py',
                           '--context', str(args.context), '--output', '.cuaderno-runs/release-manifest.json',
                           '--records', *map(str, records)], cwd=ROOT).returncode
    if code or failed:
        print('G7 no aprobado; checks fallidos: ' + ', '.join(failed), file=sys.stderr)
        return 1
    return subprocess.run([sys.executable, 'scripts/cuaderno/release_gate.py',
                           '.cuaderno-runs/release-manifest.json'], cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
