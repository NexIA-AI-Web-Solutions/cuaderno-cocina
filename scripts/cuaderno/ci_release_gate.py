"""Execute the remaining real candidate checks and aggregate exactly 17 records in CI."""
from pathlib import Path
import argparse
import hashlib
import json
import os
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
    directory = ROOT / 'data/cuaderno/tooling/grype-linux-0.119.0'
    directory.mkdir(parents=True, exist_ok=False)
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
    download(audit.shared.DB_SOURCE, db, 'ac0db74474a11c2850db2376e4838c1bc5444097d21b277ad9dec767b6d39869')
    subprocess.run([str(directory / 'grype'), 'db', 'import', str(db)], check=True,
                   env={**os.environ, 'GRYPE_DB_CACHE_DIR': str(ROOT / 'data/cuaderno/tooling/grype-db'),
                        'GRYPE_CHECK_FOR_APP_UPDATE': 'false', 'GRYPE_DB_AUTO_UPDATE': 'false'})
    db_root = ROOT / 'data/cuaderno/tooling/grype-db/6'
    if audit._sha256(db_root / 'vulnerability.db') != audit.shared.VULNERABILITY_DB_SHA256:
        raise ValueError('La base de vulnerabilidades importada no coincide con el pin.')
    (db_root / 'import.json').write_text(json.dumps({
        'digest': audit.shared.DB_DIGEST, 'source': audit.shared.DB_SOURCE,
        'client_version': audit.shared.DB_CLIENT_VERSION,
    }) + '\n')


def production_round_trip(image_id):
    """Exercise the real production profile/tools on a fresh CI-only database."""
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
        subprocess.run([*command, 'exec', '-T', 'web', '/opt/recipes/venv/bin/python', 'manage.py',
                        'shell', '-c', fixture], cwd=ROOT, check=True)
        bundle = production_backup.create_backup(env, backups, include_env=True)
        report = production_restore_verify.verify(bundle, runtime_image=image_id,
                    report_path=ROOT / '.cuaderno-runs/production-restore-report.json')
        if not report['passed']:
            raise ValueError('Restauración del perfil productivo no aprobada.')
        (ROOT / '.cuaderno-runs/production-backup-manifest.json').write_bytes((bundle / 'manifest.json').read_bytes())
    finally:
        subprocess.run([*command, 'stop'], cwd=ROOT, check=True)



def main():
    if os.environ.get('CI') not in {'true', '1'} or os.environ.get('CUADERNO_ENV') != 'test':
        raise SystemExit('Solo runner CI de pruebas aisladas.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path, required=True)
    args = parser.parse_args()
    context = json.loads(args.context.read_text())
    os.environ['CUADERNO_CANDIDATE_IMAGE'] = context['image_id']
    provision_scanner()
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
