"""CI-only characterization of PostgreSQL temporary Unix versus final TCP readiness."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import secrets
import shutil
import socket
import subprocess
import tarfile
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
BASE = "bda944d35bd0039d96454d53a883fdbc5e702077"
BRANCH = "refs/heads/cuaderno-pg-readiness-probe-20261006"
IMAGE = "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
FILES = {".github/workflows/cuaderno-pg-readiness-probe.yml", "scripts/cuaderno/ci_pg_readiness_probe.py"}
LABEL = "io.cuaderno.pg-readiness-probe"
MAX_COPY = 256 * 1024


class ProbeFailure(ValueError):
    pass


def require(condition):
    if not condition:
        raise ProbeFailure("Probe contract failed")


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def entrypoint_proof(archive):
    require(len(archive) <= MAX_COPY)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
        members = source.getmembers()
        require(len(members) == 1)
        member = members[0]
        require(member.name == "docker-entrypoint.sh" and member.isfile()
                and not member.sparse and member.size <= MAX_COPY)
        with source.extractfile(member) as stream:
            raw = stream.read(MAX_COPY + 1)
    require(len(raw) <= MAX_COPY)
    text = raw.decode("utf-8")
    match = re.search(r"(?m)^docker_temp_server_start\(\)\s*\{\n(.*?)^\}", text, re.S)
    require(match is not None)
    require("listen_addresses=''" in match[1] and "pg_ctl" in match[1])
    main = text[text.index("_main() {"):]
    order = [main.index(name) for name in ("docker_temp_server_start", "docker_setup_db",
                                         "docker_process_init_files", "docker_temp_server_stop")]
    require(order == sorted(order) and 'exec "$@"' in main)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "temporary_server_socket_only": True,
            "init_hook_precedes_temporary_stop_and_final_exec": True}


class Boundary:
    def __init__(self):
        self.deadline = time.monotonic() + 145

    def run(self, argv, *, accept_failure=False, limit=1024 * 1024):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0)
        end = time.monotonic() + min(40, remaining)
        chunks, size = [], 0
        process = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    require(end > time.monotonic())
                    events = selector.select(end - time.monotonic())
                    require(bool(events))
                    chunk = os.read(process.stdout.fileno(), min(65536, limit + 1 - size))
                    if not chunk:
                        selector.unregister(process.stdout)
                        break
                    size += len(chunk)
                    require(size <= limit)
                    chunks.append(chunk)
            code = process.wait(timeout=max(0.01, end - time.monotonic()))
            result = subprocess.CompletedProcess(argv, code, stdout=b"".join(chunks))
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        if not accept_failure:
            require(result.returncode == 0)
        return result

    def success(self, argv):
        return self.run(argv, accept_failure=True).returncode == 0


def source_guard(boundary):
    require(os.environ.get("CI") in {"true", "1"} and os.environ.get("CUADERNO_ENV") == "test")
    require(os.environ.get("GITHUB_REPOSITORY") == "NexIA-AI-Web-Solutions/cuaderno-cocina")
    require(os.environ.get("GITHUB_REF") == BRANCH)
    require(datetime.now(timezone.utc).date().isoformat() == "2026-10-06")
    require(boundary.success(["git", "merge-base", "--is-ancestor", BASE, "HEAD"]))
    changed = boundary.run(["git", "diff", "--name-only", BASE]).stdout.decode().splitlines()
    untracked = boundary.run(["git", "ls-files", "--others", "--exclude-standard"]).stdout.decode().splitlines()
    require(set(changed + untracked) <= FILES)
    require(not boundary.run(["git", "status", "--porcelain", "--untracked-files=all"]).stdout)


def runner_guard(boundary):
    available = re.search(r"(?m)^MemAvailable:\s+(\d+) kB$", Path("/proc/meminfo").read_text())
    require(available is not None and int(available[1]) * 1024 > 2 * 1024**3)
    require(shutil.disk_usage(ROOT).free > 5 * 1024**3)
    require(not boundary.run(["docker", "ps", "-aq"]).stdout.strip())
    require(not boundary.run(["docker", "volume", "ls", "-q"]).stdout.strip())
    networks = boundary.run(["docker", "network", "ls", "--format", "{{.Name}}"])
    require(set(networks.stdout.decode().splitlines()) <= {"bridge", "host", "none"})
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 18082))


def owned(boundary, kind, name, namespace, image_id):
    result = boundary.run(["docker", kind, "inspect", name], accept_failure=True)
    require(result.returncode == 0)
    rows = strict_json(result.stdout)
    require(isinstance(rows, list) and len(rows) == 1)
    info = rows[0]
    labels = info.get("Config", {}).get("Labels", {}) if kind == "container" else info.get("Labels", {})
    require(labels.get(LABEL) == namespace and info.get("Name") == ("/" + name if kind == "container" else name))
    if kind == "container":
        require(info.get("Image") == image_id and re.fullmatch(r"[a-f0-9]{64}", info.get("Id", "")))
        require(not info.get("HostConfig", {}).get("PortBindings"))
    return info


def private_write(path, text):
    with path.open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(text)


def main():
    boundary = Boundary()
    phase = "source-guard"
    resources = []
    directory = None
    namespace = "cuaderno-pg-probe-" + uuid.uuid4().hex[:12]
    image_id = None
    receipt = {"schema_version": 1, "kind": "postgres-readiness-diagnostic", "release_certification": False,
               "passed": False, "base_commit": BASE, "image_reference": IMAGE,
               "published_ports": False, "raw_output_recorded": False}
    cleanup = {"passed": True, "owned_resources_removed": 0}
    try:
        source_guard(boundary)
        receipt["diagnostic_source_commit"] = boundary.run(["git", "rev-parse", "HEAD"]).stdout.decode().strip()
        require(re.fullmatch(r"[a-f0-9]{40}", receipt["diagnostic_source_commit"]) is not None)
        receipt["namespace"] = namespace
        phase = "runner-guard"
        runner_guard(boundary)
        phase = "image-pull"
        boundary.run(["docker", "pull", "--platform", "linux/amd64", IMAGE])
        info = strict_json(boundary.run(["docker", "image", "inspect", IMAGE]).stdout)[0]
        image_id = info["Id"]
        require(re.fullmatch(r"sha256:[a-f0-9]{64}", image_id) is not None)
        require(info.get("Os") == "linux" and info.get("Architecture") == "amd64")
        require(any(x.endswith(IMAGE.split("@", 1)[1]) for x in info.get("RepoDigests", [])))
        receipt["runtime_image_id"] = image_id
        receipt["runtime_platform"] = "linux/amd64"
        phase = "entrypoint-proof"
        # Mount one labelled named volume even in the stopped reader; the image
        # declares PGDATA as VOLUME and otherwise creates an unlabelled volume.
        volume = namespace + "-data"
        resources.append(("volume", volume))
        boundary.run(["docker", "volume", "create", "--label", LABEL + "=" + namespace, volume])
        reader = namespace + "-reader"
        resources.append(("container", reader))
        boundary.run(["docker", "create", "--name", reader, "--label", LABEL + "=" + namespace,
                      "--network", "none", "--read-only", "--cap-drop", "ALL",
                      "--mount", "type=volume,source=" + volume + ",target=/var/lib/postgresql/data",
                      "--security-opt", "no-new-privileges:true", "--entrypoint", "/bin/true", image_id])
        reader_info = owned(boundary, "container", reader, namespace, image_id)
        require(reader_info.get("State", {}).get("Running") is False)
        raw = boundary.run(["docker", "cp", reader + ":/usr/local/bin/docker-entrypoint.sh", "-"], limit=MAX_COPY).stdout
        receipt["actual_entrypoint"] = entrypoint_proof(raw)
        phase = "own-resources"
        directory = ROOT / ".cuaderno-runs" / namespace
        directory.parent.mkdir(mode=0o700, exist_ok=True)
        directory.parent.chmod(0o700)
        directory.mkdir(mode=0o700)
        env = directory / "database.env"
        private_write(env, "POSTGRES_USER=cuaderno_probe\nPOSTGRES_DB=cuaderno_probe\nPOSTGRES_PASSWORD=" + secrets.token_hex(32) + "\n")
        hook = directory / "init.sh"
        private_write(hook, '#!/bin/sh\nset -eu\nprintf started > "$PGDATA/cuaderno-probe-started"\npsql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atqc "SELECT pg_sleep(8)" > /dev/null\nprintf completed > "$PGDATA/cuaderno-probe-completed"\n')
        # Executable hooks run in a child shell; their `set -u` must not alter
        # the official entrypoint's deliberately different shell options.
        hook.chmod(0o555)
        receipt["benign_init_hook_sha256"] = hashlib.sha256(hook.read_bytes()).hexdigest()
        network, database = namespace + "-network", namespace + "-db"
        resources.append(("network", network))
        boundary.run(["docker", "network", "create", "--internal", "--label", LABEL + "=" + namespace, network])
        require(owned(boundary, "network", network, namespace, image_id)["Internal"] is True)
        resources.append(("container", database))
        boundary.run(["docker", "run", "-d", "--name", database, "--label", LABEL + "=" + namespace,
                      "--network", network, "--user", "postgres", "--env-file", str(env),
                      "--mount", "type=volume,source=" + volume + ",target=/var/lib/postgresql/data",
                      "--mount", "type=bind,source=" + str(hook) + ",target=/docker-entrypoint-initdb.d/01-cuaderno-probe.sh,readonly",
                      "--memory", "512m", "--cpus", "0.5", "--pids-limit", "128", "--restart=no",
                      "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", image_id,
                      "postgres", "-c", "shared_buffers=64MB", "-c", "max_connections=20"])
        env.unlink()
        phase = "temporary-readiness"
        marker_started = ["docker", "exec", database, "test", "-f", "/var/lib/postgresql/data/cuaderno-probe-started"]
        marker_completed = ["docker", "exec", database, "test", "-f", "/var/lib/postgresql/data/cuaderno-probe-completed"]
        while not boundary.success(marker_started):
            time.sleep(0.1)
        unix_ready = boundary.success(["docker", "exec", database, "pg_isready", "-U", "cuaderno_probe", "-d", "cuaderno_probe"])
        tcp_command = ["docker", "exec", database, "pg_isready", "-h", "127.0.0.1", "-U", "cuaderno_probe", "-d", "cuaderno_probe"]
        tcp_ready = boundary.success(tcp_command)
        marker_done = boundary.success(marker_completed)
        require(unix_ready and not tcp_ready and not marker_done)
        require(boundary.success(["docker", "exec", database, "pg_isready", "-h", "/var/run/postgresql",
                                  "-U", "cuaderno_probe", "-d", "cuaderno_probe"]))
        receipt["old_guard_red"] = {"unix_ready": True, "tcp_ready": False, "initialization_completed": False,
                                   "observation": "temporary-server-false-readiness"}
        phase = "final-readiness"
        sql_command = ["docker", "exec", database, "sh", "-ec", 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atqc "SELECT 1"']
        while True:
            if boundary.success(tcp_command):
                sql = boundary.run(sql_command, accept_failure=True)
                if sql.returncode == 0 and sql.stdout.strip() == b"1" and boundary.success(marker_completed):
                    break
            time.sleep(0.1)
        owned(boundary, "container", database, namespace, image_id)
        require(boundary.success(["docker", "exec", database, "timeout", "1", "true"]))
        unix_sql = boundary.run(["docker", "exec", database, "timeout", "2", "psql", "-h", "/var/run/postgresql",
                                 "-X", "-w", "-U", "cuaderno_probe", "-d", "cuaderno_probe",
                                 "-v", "ON_ERROR_STOP=1", "-Atqc", "SELECT 1"])
        require(unix_sql.stdout.strip() == b"1")
        receipt["client_tools"] = {"timeout_applet_usable": True, "explicit_unix_socket_ready": True,
                                   "final_own_database_unix_select_one": True}
        receipt["new_guard_green"] = {"tcp_ready": True, "sql_select_one": True, "initialization_completed": True,
                                      "observation": "final-server-ready"}
        phase = "complete"
        receipt["passed"] = True
    except Exception as exc:
        receipt["error_type"] = type(exc).__name__
    finally:
        # 145s measurement + 25s cleanup + at most 5s own-child reap stays below 3min.
        boundary.deadline = min(boundary.deadline + 25, time.monotonic() + 25)
        for kind, name in reversed(resources):
            try:
                info = owned(boundary, kind, name, namespace, image_id)
                if kind == "container":
                    if info.get("State", {}).get("Running"):
                        boundary.run(["docker", "stop", "--time", "2", info["Id"]])
                    boundary.run(["docker", "rm", info["Id"]])
                else:
                    boundary.run(["docker", kind, "rm", name])
                cleanup["owned_resources_removed"] += 1
            except Exception as exc:
                cleanup["passed"] = False
                cleanup["error_type"] = type(exc).__name__
        if directory is not None:
            (directory / "database.env").unlink(missing_ok=True)
        receipt["cleanup"] = cleanup
        receipt["passed"] = receipt["passed"] and cleanup["passed"]
        receipt["phase"] = phase
        output = ROOT / ".cuaderno-runs" / "pg-readiness-probe.json"
        output.parent.mkdir(mode=0o700, exist_ok=True)
        output.parent.chmod(0o700)
        private_write(output, json.dumps(receipt, sort_keys=True) + "\n")
        print(json.dumps({"passed": receipt["passed"], "phase": phase,
                          "receipt_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
