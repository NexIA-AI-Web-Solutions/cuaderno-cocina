"""Read installed runtime metadata and published PyPI advisories; no data writes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib import metadata
import json
import platform
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen


def inspect_distribution(distribution):
    name, version = distribution.metadata['Name'], distribution.version
    component = {'type': 'library', 'name': name, 'version': version,
                 'purl': f'pkg:pypi/{name.lower().replace("_", "-")}@{version}'}
    declared = distribution.metadata.get('License-Expression') or distribution.metadata.get('License')
    if declared:
        component['properties'] = [{'name': 'cuaderno:declared-license', 'value': declared[:500]}]
    try:
        with urlopen(f'https://pypi.org/pypi/{quote(name, safe="")}/{quote(version, safe="")}/json', timeout=30) as response:
            package = json.load(response)
        findings = [{'package': name, 'version': version, 'id': item['id'],
                     'link': item.get('link'), 'fixed_versions': item.get('fixed_in', [])}
                    for item in package.get('vulnerabilities', []) if not item.get('withdrawn')]
        return component, findings, None
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
        return component, [], {'package': name, 'version': version, 'error': str(exc)}


def main():
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(inspect_distribution, metadata.distributions()))
    findings = [finding for _, findings, _ in rows for finding in findings]
    gaps = [gap for _, _, gap in rows if gap]
    alpine = subprocess.run(['apk', 'info', '-v'], capture_output=True, text=True, check=True).stdout.splitlines()
    report = {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
              'metadata': {'timestamp': datetime.now(timezone.utc).isoformat()},
              'components': sorted([component for component, _, _ in rows], key=lambda item: item['name'].lower())}
    # Advisory and OS inventories are separate from the CycloneDX component list.
    print(json.dumps({'sbom': report, 'python': platform.python_version(), 'alpine_installed': alpine,
                      'advisory_source': 'PyPI version JSON; published advisories only, not an image scanner',
                      'findings': findings, 'unresolved': gaps}, ensure_ascii=False, sort_keys=True))
    return 2 if gaps else 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
