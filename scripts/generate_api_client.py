"""Reproduce the SDK from local OpenAPI using an isolated, pinned generator."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "openapitools/openapi-generator-cli:v7.19.0@sha256:b9e7ad71a9f9406bd810378a939755fad114747a767e29bbf83ef9364d5f9dc0"
CLIENT = ROOT / "vue3/src/openapi"
PARTS = ("apis", "models", "index.ts", "runtime.ts")


def generator_user_args() -> list[str]:
    # Generated files must stay readable and removable by the checkout owner.
    # Docker Desktop handles Windows mounts without POSIX host IDs.
    return ["--user", f"{os.getuid()}:{os.getgid()}"] if os.name == "posix" else []


def reject_links(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise ValueError("Refusing a linked generation path.")
    if path.is_dir():
        for directory, directories, filenames in os.walk(path, followlinks=False):
            for name in directories + filenames:
                node = Path(directory) / name
                if node.is_symlink() or node.is_junction():
                    raise ValueError("Refusing a linked generation artifact.")


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate schema key: {key}")
        result[key] = value
    return result


def executable_csrf_contract(runtime: bytes) -> bool:
    """Require the shared configuration helper bound to the final fetch transport.

    This protects the pinned generator customization; frontend transport tests
    separately exercise the helper's configured-cookie and origin/path policy.
    Comments and string decoys never supply executable contract tokens.
    """
    source = runtime.decode("utf-8")
    lexer = re.compile(r"(?P<comment>//[^\r\n]*|/\*[\s\S]*?\*/)|(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)|(?P<identifier>[A-Za-z_$][A-Za-z0-9_$]*)|(?P<other>\S)")
    tokens = []
    for match in lexer.finditer(source):
        if match.lastgroup == "comment":
            continue
        value = match.group()
        if match.lastgroup == "string":
            value = ("CONFIG_LITERAL" if value in ("'@/utils/djangoConfig'", '"@/utils/djangoConfig"')
                     else "HEADER_LITERAL" if value in ("'X-CSRFToken'", '"X-CSRFToken"')
                     else "ERROR_LITERAL" if value in ("'error'", '"error"')
                     else "STRING_LITERAL")
        tokens.append(value)
    executable = " ".join(tokens)
    if not re.search(r"\bimport \{ [^{};]*\bcsrfHeadersForUrl (?=,|\})[^{};]*\} from CONFIG_LITERAL", executable):
        return False
    identifier = r"[A-Za-z_$][A-Za-z0-9_$]*"
    for constructor in re.finditer(
        rf"\b(?:const|let|var) (?P<headers>{identifier}) = new Headers \( (?P<params>{identifier}) \. init \. headers \) ;",
        executable,
    ):
        headers, params = map(re.escape, (constructor["headers"], constructor["params"]))
        deletion = re.search(rf"{headers} \. delete \( HEADER_LITERAL \) ;", executable[constructor.end():])
        if deletion is None:
            continue
        start = constructor.end() + deletion.end()
        binding = re.search(
            rf"for \( const \[ (?P<name>{identifier}) , (?P<value>{identifier}) \] of Object \. entries \( "
            rf"csrfHeadersForUrl \( {params} \. url \) \) \) (?:\{{ )?"
            rf"{headers} \. set \( (?P=name) , (?P=value) \) ;",
            executable[start:],
        )
        if binding is None:
            continue
        start += binding.end()
        init = re.search(
            rf"{params} \. init = \{{ \. \. \. {params} \. init , {headers} , redirect : ERROR_LITERAL \}} ;",
            executable[start:],
        )
        if init is None:
            continue
        start += init.end()
        fetch = re.search(
            rf"(?:\bfetch|\( this \. configuration \. fetchApi \| \| fetch \)) \( {params} \. url , {params} \. init \)",
            executable[start:],
        )
        if fetch is not None:
            # Changes after the final binding would bypass its destination policy.
            middle = executable[start:start + fetch.start()]
            if not re.search(rf"\b{params} (?:\. (?:url|init) )?=", middle):
                return True
    return False


def files(directory: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(directory)).replace("\\", "/"): path.read_bytes()
        for part in PARTS for path in (
            sorted((directory / part).rglob("*.ts")) if (directory / part).is_dir() else [directory / part]
        ) if path.is_file()
    }


def generate(schema: Path, *, check=False, runner=subprocess.run) -> bool:
    schema = schema.resolve(strict=True)
    document = json.loads(schema.read_text(encoding="utf-8"), object_pairs_hook=strict_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if not isinstance(document, dict) or not document.get("openapi", "").startswith("3.") or not document.get("paths"):
        raise ValueError("A nonempty OpenAPI 3 document is required.")
    runs = ROOT / ".cuaderno-runs"
    if runs.is_symlink() or runs.is_junction():
        raise ValueError("Refusing a linked generation path.")
    runs.mkdir(exist_ok=True)
    if not runs.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Generation directory escapes the checkout.")
    reject_links(CLIENT)
    with tempfile.TemporaryDirectory(prefix="sdk-", dir=runs) as temporary:
        stage = Path(temporary)
        shutil.copyfile(schema, stage / "schema.json")
        shutil.copytree(CLIENT / "templates", stage / "templates")
        runner([
            "docker", "run", "--rm", "--network", "none",
            *generator_user_args(),
            "--mount", f"type=bind,source={stage},target=/local", GENERATOR,
            "generate", "-g", "typescript-fetch", "-i", "/local/schema.json",
            "-t", "/local/templates", "-o", "/local/generated",
            "--global-property", "apiDocs=false,modelDocs=false",
            "--additional-properties", "hideGenerationTimestamp=true",
        ], check=True, cwd=ROOT, timeout=300)
        output = stage / "generated"
        reject_links(output)
        if (not all((output / part).is_dir() for part in ("apis", "models"))
                or not all((output / part).is_file() for part in ("index.ts", "runtime.ts"))):
            raise ValueError("Generator did not produce the complete client.")
        generated = files(output)
        if not all(any(name == part or name.startswith(part + "/") for name in generated) for part in PARTS):
            raise ValueError("Generator did not produce the complete client.")
        if not executable_csrf_contract(generated["runtime.ts"]):
            raise ValueError("Generated runtime lost the session CSRF contract.")
        current = files(CLIENT)
        if check:
            changed = sorted(name for name in current.keys() | generated.keys() if current.get(name) != generated.get(name))
            for name in changed:
                print(f"SDK differs: {name}")
            return not changed
        backup = stage / "backup"
        backup.mkdir()
        for base in (CLIENT, output, backup):
            if not base.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError("Client path escapes the checkout.")
        replaced = []
        try:
            for part in PARTS:
                target = CLIENT / part
                if target.is_symlink():
                    raise ValueError("Refusing to replace a linked client artifact.")
                if target.exists():
                    shutil.move(str(target), str(backup / part))
                replaced.append(part)
                shutil.move(str(output / part), str(target))
            if files(CLIENT) != generated:
                raise ValueError("Installed SDK differs from validated generated output.")
        except BaseException:
            for part in reversed(replaced):
                target = CLIENT / part
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                if (backup / part).exists():
                    shutil.move(str(backup / part), str(target))
            raise
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=ROOT / "tooling/cuaderno/openapi.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return 0 if generate(args.schema, check=args.check) else 1


if __name__ == "__main__":
    raise SystemExit(main())
