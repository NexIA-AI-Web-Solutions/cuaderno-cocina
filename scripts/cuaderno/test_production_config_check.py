"""Execute the production health command with harmless PostgreSQL stand-ins."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class FakePostgresClients:
    """No server: model socket-only initialization and final TCP readiness."""

    def __init__(self, *, tcp_at=1, sql_result="1", sql_exit=0):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.log = self.root / "clients.log"
        scripts = {
            "pg_isready": '''#!/bin/sh
n=0; [ ! -f "$PG_TEST_ROOT/polls" ] || n=$(cat "$PG_TEST_ROOT/polls")
n=$((n + 1)); echo "$n" > "$PG_TEST_ROOT/polls"
echo "ready:$*" >> "$PG_TEST_ROOT/clients.log"
case " $* " in
  *" -h 127.0.0.1 "*) [ "$n" -ge "$PG_TEST_TCP_AT" ] ;;
  *) exit 0 ;;
esac
''',
            "psql": '''#!/bin/sh
echo "sql:$*;connect=$PGCONNECT_TIMEOUT;options=$PGOPTIONS" >> "$PG_TEST_ROOT/clients.log"
echo "$PG_TEST_SQL_RESULT"
if [ "$PG_TEST_SQL_EXIT" != 0 ]; then echo 'private-sql-fixture-marker' >&2; fi
exit "$PG_TEST_SQL_EXIT"
''',
            "sleep": '''#!/bin/sh
echo "sleep:$*" >> "$PG_TEST_ROOT/clients.log"
''',
            "timeout": '''#!/bin/sh
echo "timeout:$1" >> "$PG_TEST_ROOT/clients.log"
shift
exec "$@"
''',
        }
        for name, source in scripts.items():
            path = self.root / name
            path.write_text(source)
            path.chmod(0o700)
        self.environment = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ["PATH"],
                                PG_TEST_ROOT=str(self.root), PG_TEST_TCP_AT=str(tcp_at),
                                PG_TEST_SQL_RESULT=sql_result, PG_TEST_SQL_EXIT=str(sql_exit))

    def run(self, command):
        return subprocess.run(["sh", "-ec", command], env=self.environment,
                              capture_output=True, timeout=5)

    def rows(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def cleanup(self):
        self.temporary.cleanup()


class ProductionDatabaseHealthTests(unittest.TestCase):
    def command(self):
        text = (Path(__file__).resolve().parents[2] / "deploy/cuaderno/compose.production.yml").read_text()
        section = text.split("    healthcheck:\n", 1)[1].split("    stop_grace_period:", 1)[0]
        self.assertIn("      interval: 10s\n", section)
        self.assertIn("      timeout: 3s\n", section)
        self.assertIn("      retries: 20\n", section)
        value = re.search(r"^      test: (.+)$", section, re.M).group(1)
        # The original flow sequence contains unquoted YAML scalars.
        if value.startswith('[CMD-SHELL, '):
            return value[len('[CMD-SHELL, '):-1]
        command = json.loads(value)
        self.assertEqual(command[0], "CMD-SHELL")
        return command[1].replace("$$", "$")

    def clients(self, **kwargs):
        clients = FakePostgresClients(**kwargs)
        self.addCleanup(clients.cleanup)
        return clients

    def test_socket_only_temporary_server_is_not_healthy(self):
        clients = self.clients(tcp_at=2)
        result = clients.run(self.command())
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(row.startswith("sql:") for row in clients.rows()))

    def test_missing_real_database_fails_even_when_pg_isready_accepts_connections(self):
        result = self.clients(sql_exit=1).run(self.command())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

    def test_sql_scalar_must_be_exactly_one(self):
        for scalar in ("0", "11", "1\n1", " 1", ""):
            with self.subTest(scalar=scalar):
                self.assertNotEqual(self.clients(sql_result=scalar).run(self.command()).returncode, 0)

    def test_final_tcp_and_own_database_query_are_required(self):
        clients = self.clients()
        result = clients.run(self.command())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, b"")
        rows = clients.rows()
        self.assertIn("ready:-q -h 127.0.0.1 -t 1 -U cuaderno_prod -d cuaderno_prod", rows)
        self.assertIn("timeout:2", rows)
        self.assertIn("sql:-X -w -h /var/run/postgresql -U cuaderno_prod -d cuaderno_prod -v ON_ERROR_STOP=1 -At -c SELECT 1;connect=2;options=-c statement_timeout=1000", rows)

    def test_compose_preserves_shell_dollars_and_has_no_password_argument(self):
        text = (Path(__file__).resolve().parents[2] / "deploy/cuaderno/compose.production.yml").read_text()
        line = next(line for line in text.splitlines() if "test:" in line)
        self.assertIn("$$(", line)
        self.assertIn("$$result", line)
        self.assertNotIn("PASSWORD", line)


if __name__ == "__main__":
    unittest.main()
