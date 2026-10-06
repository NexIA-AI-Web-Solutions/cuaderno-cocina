"""Bind a loaded immutable Docker ID to the verified archive's config/OCI chain."""
import argparse
import json
from pathlib import Path
import subprocess

try:
    from . import image_archive_audit
except ImportError:
    import image_archive_audit


def verify(archive, expected_id, source, *, inspector=subprocess.run,
           binder=image_archive_audit._archive_binding):
    binding = binder(archive, image_id=expected_id, source_ref=source)
    references = [expected_id]
    if binding.get('manifest_digest') and binding['manifest_digest'] != expected_id:
        references.append(binding['manifest_digest'])
    for reference in references:
        result = inspector(['docker', 'image', 'inspect', reference], check=False,
                           capture_output=True, text=True, timeout=30)
        if result.returncode:
            continue
        values = json.loads(result.stdout)
        if len(values) != 1:
            raise ValueError('La imagen cargada no es única.')
        info = values[0]
        actual = info.get('Id')
        allowed = binding.get('chain', [binding['config_digest']])
        if (actual not in allowed or actual != reference
                or info.get('Config', {}).get('Labels', {}).get('io.cuaderno.source-identity') != source):
            raise ValueError('La imagen local no enlaza a la fuente y cadena verificadas.')
        return {'archive_image_id': expected_id, 'local_image_id': actual,
                'source_identity': source, 'archive_binding': binding}
    raise ValueError('No existe la imagen inmutable de la cadena verificada.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--image-id-file', type=Path, required=True)
    parser.add_argument('--source-identity-file', type=Path, required=True)
    parser.add_argument('--local-id-output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.archive, args.image_id_file.read_text().strip(), args.source_identity_file.read_text().strip())
    with args.local_id_output.open('x') as output:
        output.write(result['local_image_id'] + '\n')
    with args.report.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(result['local_image_id'])


if __name__ == '__main__':
    main()
