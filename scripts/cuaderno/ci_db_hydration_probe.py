"""Two fresh Linux Grype imports; records evidence, never sets application pins."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
BRANCH = "cuaderno-db-probe-20261006"
GRYPE_URL = "https://github.com/anchore/grype/releases/download/v0.119.0/grype_0.119.0_linux_amd64.tar.gz"
GRYPE_ARCHIVE_SHA = "3fa2dc4b924621ab65404cf08d0b8438d896d80ab949c9d5a4ca283c36004c9b"
GRYPE_BINARY_SHA = "e02ba25615668c6bae03473e3c6493b6dfffc2e4e419f65f9bd62555ac10cd0e"
DB_URL = (
    "https://grype.anchore.io/databases/v6/"
    "vulnerability-db_v6.1.10_2026-10-06T00:34:33Z_1791268334.tar.zst"
    "?checksum=sha256%3A1535cef8f13c12f3b7cdfc652722bb59d99fab934d0ac80d810a0462466d97cb"
)
DB_ARCHIVE_SHA = "1535cef8f13c12f3b7cdfc652722bb59d99fab934d0ac80d810a0462466d97cb"
RAW_SQLITE_SHA = "977ceff7828db1b57fa5c0ada35e26f7c0dc783e5485f6b950c13c094761fbd8"
BUILD_DAY = date(2026, 10, 6)
MIN_FREE_BYTES = 20 * 1024**3
CHUNK = 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def strict_json(raw):
    def unique(pairs):
        document = {}
        for key, value in pairs:
            require(key not in document, "Duplicate JSON metadata key")
            document[key] = value
        return document
    return json.loads(raw, object_pairs_hook=unique)


def validate_status(status, stamp, database):
    require(isinstance(status, dict) and isinstance(stamp, dict), "Invalid status/stamp JSON")
    require(status.get("valid") is True, "Imported database is not valid")
    require(status.get("schemaVersion") == "v6.1.10", "Unexpected installed database schema")
    require(status.get("from") == "manual import", "Status did not originate from manual import")
    require(status.get("path") == str(database), "Status names another database")
    built = datetime.fromisoformat(status.get("built", "").replace("Z", "+00:00"))
    require(built.utcoffset() is not None and built.astimezone(timezone.utc).date() == BUILD_DAY,
            "Database was not built on the pinned day")
    require(set(stamp) == {"digest", "source", "client_version"}, "Unexpected generated stamp fields")
    require(stamp["source"] == "manual import" and stamp["client_version"] == "v6.1.9",
            "Unexpected generated stamp source/client")
    require(isinstance(stamp["digest"], str) and re.fullmatch(r"xxh64:[0-9a-f]{16}", stamp["digest"]),
            "Invalid generated database digest")


def delete_owned_cache(cache, probe):
    # Validate the entire tree before unlinking anything; never follow links.
    require(cache.parent == probe and cache.name in {"cache-1", "cache-2"}, "Refusing deletion outside owned cache")
    require(not probe.is_symlink() and not cache.is_symlink(), "Refusing linked cache")
    files, directories = [], []
    for parent, children, names in os.walk(cache, followlinks=False):
        directory = Path(parent)
        require(stat.S_ISDIR(directory.lstat().st_mode), "Invalid cache directory")
        directories.append(directory)
        for child in children:
            require(stat.S_ISDIR((directory / child).lstat().st_mode), "Linked/special cache directory")
        for name in names:
            path = directory / name
            metadata = path.lstat()
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, "Linked/special cache file")
            files.append(path)
    for path in files:
        path.unlink()
    for directory in reversed(directories):
        directory.rmdir()


def download(url, destination, expected_sha, proof):
    request = urllib.request.Request(url, headers={"User-Agent": "cuaderno-ci-audit/1.0"})
    digest, size = hashlib.sha256(), 0
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("xb") as output:
        require(response.geturl().startswith("https://"), "Download redirected outside HTTPS")
        while chunk := response.read(CHUNK):
            size += len(chunk)
            require(size <= 2 * 1024**3, "Archive exceeds diagnostic size limit")
            digest.update(chunk)
            output.write(chunk)
    actual = digest.hexdigest()
    result = {"url": url, "sha256": actual, "expected_sha256": expected_sha, "bytes": size}
    write_json(proof, result)
    require(actual == expected_sha, "Official archive SHA256 mismatch")
    return result


def extract_binary(archive, destination, proof):
    with tarfile.open(archive, "r:gz") as package:
        candidates = [member for member in package.getmembers() if member.name == "grype"]
        require(len(candidates) == 1 and candidates[0].isfile(), "Archive must contain one regular Grype binary")
        require(candidates[0].size <= 256 * 1024**2, "Binary exceeds diagnostic limit")
        with package.extractfile(candidates[0]) as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output, CHUNK)
    actual = sha256(destination)
    write_json(proof, {"sha256": actual, "expected_sha256": GRYPE_BINARY_SHA})
    require(actual == GRYPE_BINARY_SHA, "Official Linux binary SHA256 mismatch")
    destination.chmod(0o700)


def verify_raw_database(archive, evidence):
    require(shutil.which("zstd") is not None, "Runner lacks zstd for raw archive verification")
    with (evidence / "raw-db-verification.log").open("wb") as log:
        process = subprocess.Popen(["zstd", "--quiet", "--decompress", "--stdout", str(archive)],
                                   stdout=subprocess.PIPE, stderr=log)
        try:
            members, size, digest = [], 0, hashlib.sha256()
            with tarfile.open(fileobj=process.stdout, mode="r|") as package:
                for member in package:
                    name = PurePosixPath(member.name)
                    require(not name.is_absolute() and ".." not in name.parts, "Unsafe database archive member")
                    if member.isdir():
                        continue
                    require(member.isfile() and str(name) == "vulnerability.db" and not members,
                            "Database archive must contain only its one raw SQLite file")
                    members.append(str(name))
                    with package.extractfile(member) as source:
                        while chunk := source.read(CHUNK):
                            if size == 0:
                                require(chunk.startswith(b"SQLite format 3\0"), "Raw database is not SQLite")
                            size += len(chunk)
                            require(size <= 16 * 1024**3, "Raw database exceeds diagnostic limit")
                            digest.update(chunk)
            # Consume compressor output to EOF and require a clean exit.
            while process.stdout.read(CHUNK):
                pass
            require(process.wait(timeout=30) == 0, "zstd archive validation failed")
            result = {"members": members, "sha256": digest.hexdigest(), "expected_sha256": RAW_SQLITE_SHA, "bytes": size}
            write_json(evidence / "raw-database-proof.json", result)
            require(len(members) == 1 and digest.hexdigest() == RAW_SQLITE_SHA, "Raw SQLite SHA256 mismatch")
            return result
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()


def run_grype(binary, arguments, environment, evidence, label, *, timeout):
    stdout = evidence / (label + ".json" if arguments[0] != "db" or arguments[1] == "status" else label + ".log")
    stderr = evidence / (label + "-stderr.log")
    with stdout.open("xb") as output, stderr.open("xb") as error:
        completed = subprocess.run([str(binary), "--config", environment["PROBE_CONFIG"], *arguments],
                                   cwd=binary.parent, env={key: value for key, value in environment.items() if key != "PROBE_CONFIG"},
                                   stdout=output, stderr=error, timeout=timeout, check=False)
    require(completed.returncode == 0, "Grype " + label + " failed; see saved diagnostic logs")
    return stdout.read_bytes()


def probe():
    require(os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true",
            "This diagnostic can run only inside GitHub Actions CI")
    require(os.environ.get("RUNNER_OS") == "Linux" and os.environ.get("RUNNER_ARCH") == "X64"
            and platform.system() == "Linux" and platform.machine() == "x86_64", "Requires fresh Linux x64 runner")
    require(os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH, "Wrong diagnostic branch")
    require(Path(os.environ["GITHUB_WORKSPACE"]).resolve() == ROOT, "Wrong diagnostic checkout")
    require(datetime.now(timezone.utc).date() == BUILD_DAY, "Pinned database is no longer today's snapshot")
    os.umask(0o077)
    runs = ROOT / ".cuaderno-runs"
    require(not runs.is_symlink(), "Linked diagnostic parent")
    runs.mkdir(mode=0o700, exist_ok=True)
    private = runs / "db-hydration-probe"
    private.mkdir(mode=0o700)  # Never reuse an old result/cache.
    evidence = private / "evidence"
    evidence.mkdir(mode=0o700)
    report = {"passed": False, "minimum_free_bytes": MIN_FREE_BYTES, "imports": [], "free_space": []}
    try:
        def capacity(stage):
            free = shutil.disk_usage(private).free
            report["free_space"].append({"stage": stage, "free_bytes": free})
            write_json(evidence / "summary.json", report)
            require(free >= MIN_FREE_BYTES, "Insufficient owned-runner capacity before " + stage)

        capacity("downloads")
        binary_archive = private / "grype.tar.gz"
        db_archive = private / "vulnerability-db.tar.zst"
        report["grype_archive"] = download(GRYPE_URL, binary_archive, GRYPE_ARCHIVE_SHA, evidence / "grype-archive-proof.json")
        binary = private / "grype"
        extract_binary(binary_archive, binary, evidence / "grype-binary-proof.json")
        report["grype_binary_sha256"] = sha256(binary)
        report["database_archive"] = download(DB_URL, db_archive, DB_ARCHIVE_SHA, evidence / "database-archive-proof.json")
        report["raw_database"] = verify_raw_database(db_archive, evidence)
        config = private / "grype-config.yaml"
        config.write_text("{}\n", encoding="utf-8")
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "PROBE_CONFIG": str(config),
            "GRYPE_CHECK_FOR_APP_UPDATE": "false", "GRYPE_DB_AUTO_UPDATE": "false",
            "GRYPE_EXTERNAL_SOURCES_ENABLE": "false",
        }
        for number in (1, 2):
            capacity("import-" + str(number))
            cache = private / ("cache-" + str(number))
            cache.mkdir(mode=0o700)
            current_environment = {**environment, "GRYPE_DB_CACHE_DIR": str(cache), "TMPDIR": str(cache), "SQLITE_TMPDIR": str(cache)}
            label = "import-" + str(number)
            run_grype(binary, ["db", "import", str(db_archive)], current_environment, evidence, label, timeout=600)
            database, stamp_path = cache / "6/vulnerability.db", cache / "6/import.json"
            require(database.is_file() and not database.is_symlink() and stamp_path.is_file() and not stamp_path.is_symlink(),
                    "Import did not generate regular database/stamp files")
            installed_sha = sha256(database)
            stamp_raw = stamp_path.read_bytes()
            require(0 < len(stamp_raw) <= 65536, "Generated stamp has invalid size")
            (evidence / (label + "-generated-stamp.json")).write_bytes(stamp_raw)
            stamp = strict_json(stamp_raw)
            version_raw = run_grype(binary, ["version", "-o", "json"], current_environment, evidence,
                                    label + "-version", timeout=30)
            version = strict_json(version_raw)
            require(version.get("version") == "0.119.0", "Wrong verified scanner version")
            row = {"cache": cache.name, "installed_sha256": installed_sha, "installed_bytes": database.stat().st_size,
                   "generated_stamp_sha256": hashlib.sha256(stamp_raw).hexdigest(), "generated_stamp": stamp,
                   "binary_version": version}
            report["imports"].append(row)
            write_json(evidence / (label + "-installed-proof.json"), row)
            write_json(evidence / "summary.json", report)
            status_raw = run_grype(binary, ["db", "status", "-o", "json"], current_environment, evidence,
                                   label + "-status", timeout=120)
            row["status"] = strict_json(status_raw)
            write_json(evidence / (label + "-installed-proof.json"), row)
            write_json(evidence / "summary.json", report)
            validate_status(row["status"], stamp, database)
            require(stamp_path.read_bytes() == stamp_raw and sha256(database) == installed_sha,
                    "Status changed the generated database/stamp")
            # All processes have returned. Remove only this freshly created cache.
            delete_owned_cache(cache, private)
        first, second = report["imports"]
        require(first["installed_sha256"] == second["installed_sha256"], "Independent imports differ in installed SHA256")
        require(first["generated_stamp_sha256"] == second["generated_stamp_sha256"]
                and first["generated_stamp"] == second["generated_stamp"], "Independent imports generated different stamps")
        require(first["binary_version"] == second["binary_version"], "Independent imports used different clients")
        report["passed"] = True
        return report
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        write_json(evidence / "summary.json", report)


if __name__ == "__main__":
    try:
        result = probe()
        print(json.dumps({"passed": True, "installed_sha256": result["imports"][0]["installed_sha256"],
                          "generated_stamp": result["imports"][0]["generated_stamp"]}, sort_keys=True))
    except Exception as error:
        print("Grype hydration diagnostic FAILED: " + str(error), file=sys.stderr)
        sys.exit(1)
