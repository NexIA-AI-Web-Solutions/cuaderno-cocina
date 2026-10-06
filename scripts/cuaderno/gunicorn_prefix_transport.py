"""Bounded real HTTP regression for Gunicorn's prefix transport, with no database."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PREFIX_SETTINGS = {'SCRIPT_NAME', 'FORCE_SCRIPT_NAME', 'STATIC_URL', 'MEDIA_URL', 'SESSION_COOKIE_PATH',
                   'CSRF_COOKIE_PATH', 'LANGUAGE_COOKIE_PATH'}


def launch_environment(root: Path, values: dict[str, str]) -> dict[str, str]:
    """Execute the real final boot block, excluding its supervisor exec."""
    block = (root / 'boot.sh').read_text().split('echo "Starting gunicorn"', 1)[1].split('exec python ', 1)[0]
    code = 'import json,os; print(json.dumps(dict(os.environ)))'
    result = subprocess.run(['/bin/sh', '-c', block + '\nexec "$1" -c "$2"', 'transport-test', sys.executable, code],
                            env={'PATH': os.environ['PATH'], **values}, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10)
    return json.loads(result.stdout)


def settings_assignments(root: Path) -> str:
    """Use actual source assignments without initializing Django or connecting to a DB."""
    tree = ast.parse((root / 'recipes/settings.py').read_text())
    selected = [node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id in PREFIX_SETTINGS for target in node.targets)]
    if len(selected) != len(PREFIX_SETTINGS):
        raise ValueError('Missing unique source prefix assignments.')
    return ast.unparse(ast.Module(body=selected, type_ignores=[]))


def application_source(root: Path) -> str:
    tree = ast.parse((root / 'recipes/wsgi.py').read_text())
    wrappers = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'application']
    if len(wrappers) != 1:
        raise ValueError('Missing unique source WSGI adapter.')
    # The test application replaces only Django's final handler. Gunicorn's HTTP
    # parser, launcher environment, settings assignments and WSGI adapter are real.
    return '''import json, os
''' + settings_assignments(root) + '''
def _application(environ, start_response):
    logical_script = FORCE_SCRIPT_NAME or environ.get('SCRIPT_NAME', '')
    document = {
        'ready': True, 'path_info': environ['PATH_INFO'], 'script_name': environ['SCRIPT_NAME'],
        'logical_prefix': SCRIPT_NAME, 'logical_path': logical_script + environ['PATH_INFO'],
        'query': environ['QUERY_STRING'], 'scheme': environ['wsgi.url_scheme'],
        'static_url': STATIC_URL, 'media_url': MEDIA_URL, 'cookie_path': SESSION_COOKIE_PATH,
    }
    body = json.dumps(document).encode()
    start_response('200 OK', [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))])
    return [body]
''' + ast.unparse(wrappers[0]) + '\n'


def _http_cases(root: Path, environment: dict[str, str], cases: list[tuple[str, dict, int]]) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix='cuaderno-transport-') as directory:
        temporary = Path(directory)
        (temporary / 'transport_probe.py').write_text(application_source(root))
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        log = temporary / 'gunicorn.log'
        values = {**environment, 'PYTHONPATH': str(temporary), 'PYTHONDONTWRITEBYTECODE': '1'}
        with log.open('wb') as stream:
            process = subprocess.Popen([
                sys.executable, '-m', 'gunicorn', '--bind', f'127.0.0.1:{port}', '--workers', '1', '--threads', '1',
                '--timeout', '10', '--worker-tmp-dir', str(temporary), '--chdir', str(temporary),
                '--access-logfile', '-', '--error-logfile', '-', 'transport_probe:application',
            ], env=values, stdout=stream, stderr=subprocess.STDOUT)
            results = []
            try:
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Gunicorn transport probe exited before serving HTTP.')
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Gunicorn transport probe startup timeout.')
                        time.sleep(0.05)
                for path, headers, expected in cases:
                    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers=headers)
                    try:
                        with urllib.request.urlopen(request, timeout=5) as response:
                            status, payload = response.status, json.load(response)
                    except urllib.error.HTTPError as error:
                        status, payload = error.code, None
                    if status != expected:
                        raise AssertionError(f'Actual Gunicorn HTTP {path}: expected {expected}, got {status}.')
                    results.append({'status': status, 'payload': payload})
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            return results


def verify(root: Path = ROOT) -> dict:
    import gunicorn
    prefix = '/cuaderno-cocina'
    # Control proves the original failure occurs in the real pinned Gunicorn parser.
    legacy = _http_cases(root, {'PATH': os.environ['PATH'], 'SCRIPT_NAME': prefix}, [('/health/ready/', {}, 500)])
    forwarded = {'X-Script-Name': prefix, 'X-Forwarded-Proto': 'https'}
    cases = [('/health/ready/', {}, 200),
             ('/api/recipe/?q=oil%20salt&next=%2Fshopping%2F', forwarded, 200),
             ('/media/synthetic%20photo.png?share=synthetic%2Btoken', forwarded, 200),
             (prefix + '/recipe/1/?print=1', forwarded, 200),
             ('/cuaderno-cocina-other/recipe/1/?print=1', forwarded, 200)]
    prefixed = _http_cases(root, launch_environment(root, {'SCRIPT_NAME': prefix}), cases)
    expected_paths = ['/health/ready/', '/api/recipe/', '/media/synthetic photo.png', '/recipe/1/',
                      '/cuaderno-cocina-other/recipe/1/']
    for result, expected_path in zip(prefixed, expected_paths):
        payload = result['payload']
        assert payload['path_info'] == expected_path, payload
        assert payload['logical_prefix'] == prefix, payload
        assert payload['logical_path'] == prefix + expected_path, payload
        assert payload['static_url'] == prefix + '/static/', payload
        assert payload['media_url'] == prefix + '/media/', payload
        assert payload['cookie_path'] == prefix + '/', payload
    assert prefixed[0]['payload']['script_name'] == '', prefixed[0]
    assert prefixed[1]['payload']['query'] == 'q=oil%20salt&next=%2Fshopping%2F', prefixed[1]
    assert prefixed[2]['payload']['query'] == 'share=synthetic%2Btoken', prefixed[2]
    assert prefixed[1]['payload']['scheme'] == 'https', prefixed[1]
    root_results = _http_cases(root, launch_environment(root, {}), [('/health/ready/', {}, 200), ('/recipe/1/?print=1', {}, 200)])
    for result in root_results:
        assert result['payload']['logical_prefix'] == '', result
        assert result['payload']['script_name'] == '', result
        assert result['payload']['logical_path'] == result['payload']['path_info'], result
    return {'passed': True, 'gunicorn': gunicorn.__version__, 'legacy_stripped_health_status': legacy[0]['status'],
            'prefixed_http_cases': len(prefixed), 'root_http_cases': len(root_results),
            'database_used': False, 'transport': 'real loopback HTTP, actual source launcher/settings/WSGI adapter, synthetic final handler'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(verify(args.source_root), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
