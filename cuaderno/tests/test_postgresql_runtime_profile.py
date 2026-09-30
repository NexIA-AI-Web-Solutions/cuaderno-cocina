"""The release OLTP connection profile must avoid expensive per-query JIT."""
from django.db import connection
from django.test import TestCase
from unittest.mock import patch

from recipes import settings as native_settings


class PostgreSQLRuntimeProfileTests(TestCase):
    def test_native_options_preserve_combined_ssl_configuration(self):
        # Characterize upstream parsing; do not force SSL against the local DB.
        names = ("DATABASE_URL", "DB_OPTIONS", "DB_ENGINE", "POSTGRES_HOST",
                 "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "DATABASES")
        with patch.multiple(native_settings, **{name: getattr(native_settings, name) for name in names}):
            configuration = native_settings.setup_database(
                db_options="{'sslmode': 'require', 'options': '-c jit=off'}",
                db_engine="django.db.backends.postgresql", pg_host="synthetic.invalid",
                pg_port="5432", pg_user="synthetic", pg_password="synthetic", pg_db="synthetic",
            )
            self.assertEqual(configuration["default"]["OPTIONS"], {
                "sslmode": "require", "options": "-c jit=off",
            })

    def test_application_connection_has_jit_disabled(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.assertEqual(connection.settings_dict["OPTIONS"].get("options"), "-c jit=off")
        with connection.cursor() as cursor:
            cursor.execute("SHOW jit")
            self.assertEqual(cursor.fetchone()[0], "off")
