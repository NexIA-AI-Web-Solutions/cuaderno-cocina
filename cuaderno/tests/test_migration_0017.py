"""PostgreSQL integrity migration, preserved history and installed constraints."""
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


MIGRATE_FROM = [("cuaderno", "0016_servicepreparationitem")]
MIGRATE_TO = [("cuaderno", "0017_release_integrity_and_allergen_audit")]


class ReleaseIntegrityMigrationTests(TransactionTestCase):
    """Exercise the preflight, audit-field history, indexes and constraints."""

    databases = {"default"}
    serialized_rollback = False

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(MIGRATE_FROM)
        # MigrationExecutor's loader snapshots applied migrations at creation.
        # Reload after moving backwards before planning the forward migration.
        self.executor = MigrationExecutor(connection)
        self.old_apps = self.executor.loader.project_state(MIGRATE_FROM).apps

    def tearDown(self):
        # Always restore the full graph so this class cannot leak an old schema
        # into whichever test follows it, including after a deliberately failed
        # preflight migration.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    @staticmethod
    def _catalog(apps, suffix=""):
        User = apps.get_model(*settings.AUTH_USER_MODEL.split(".", 1))
        Space = apps.get_model("cookbook", "Space")
        Food = apps.get_model("cookbook", "Food")
        Unit = apps.get_model("cookbook", "Unit")

        user = User._base_manager.create(username=f"migration-0017{suffix}")
        space = Space._base_manager.create(name=f"Migration 0017{suffix}", created_by_id=user.pk)
        # Historical Treebeard models do not expose add_root reliably.  These
        # are the canonical fields of a single root node.
        food = Food._base_manager.create(
            space_id=space.pk,
            name=f"Food{suffix}",
            path="0001",
            depth=1,
            numchild=0,
        )
        unit = Unit._base_manager.create(space_id=space.pk, name=f"kg{suffix}")
        return user, space, food, unit

    def test_preflight_aborts_without_modifying_invalid_history(self):
        Package = self.old_apps.get_model("cuaderno", "PackageFormat")
        _user, space, food, unit = self._catalog(self.old_apps, "-invalid")
        invalid = Package._base_manager.create(
            space_id=space.pk,
            food_id=food.pk,
            unit_id=unit.pk,
            label="Invalid historical package",
            quantity=Decimal("0"),
            is_reference=True,
        )

        try:
            with self.assertRaisesRegex(RuntimeError, r"PackageFormat: 1 filas"):
                self.executor.migrate(MIGRATE_TO)
            self.assertTrue(Package._base_manager.filter(pk=invalid.pk, quantity=0).exists())
            self.assertNotIn(MIGRATE_TO[0], MigrationRecorder(connection).applied_migrations())
            Allergen = self.old_apps.get_model("cuaderno", "AllergenDeclaration")
            with connection.cursor() as cursor:
                columns = {column.name for column in connection.introspection.get_table_description(
                    cursor, Allergen._meta.db_table)}
            self.assertNotIn("created_at", columns)
            self.assertNotIn("created_by_id", columns)
        finally:
            # Only remove this deliberately invalid test fixture; production
            # migration above must leave it untouched even when it aborts.
            Package._base_manager.filter(pk=invalid.pk).delete()

    def test_valid_history_keeps_unknown_audit_and_new_rows_get_a_timestamp(self):
        Allergen = self.old_apps.get_model("cuaderno", "AllergenDeclaration")
        _user, space, food, _unit = self._catalog(self.old_apps, "-valid")
        historical = Allergen._base_manager.create(
            space_id=space.pk,
            food_id=food.pk,
            name="Gluten",
            state="declared",
        )

        self.executor.migrate(MIGRATE_TO)
        new_apps = self.executor.loader.project_state(MIGRATE_TO).apps
        NewAllergen = new_apps.get_model("cuaderno", "AllergenDeclaration")

        migrated = NewAllergen._base_manager.get(pk=historical.pk)
        self.assertIsNone(migrated.created_at)
        self.assertIsNone(migrated.created_by_id)

        created = NewAllergen._base_manager.create(
            space_id=space.pk,
            food_id=food.pk,
            name="Milk",
            state="unknown",
        )
        self.assertIsNotNone(created.created_at)
        self.assertIsNone(created.created_by_id)

    def test_database_constraints_and_covering_indexes_are_installed(self):
        _user, space, food, unit = self._catalog(self.old_apps, "-constraints")
        self.executor.migrate(MIGRATE_TO)
        new_apps = self.executor.loader.project_state(MIGRATE_TO).apps
        Allergen = new_apps.get_model("cuaderno", "AllergenDeclaration")
        Package = new_apps.get_model("cuaderno", "PackageFormat")
        Price = new_apps.get_model("cuaderno", "PriceVersion")
        Movement = new_apps.get_model("cuaderno", "StockMovement")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Allergen._base_manager.create(
                space_id=space.pk,
                food_id=food.pk,
                name="Invalid",
                state="absent",
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Package._base_manager.create(
                space_id=space.pk,
                food_id=food.pk,
                unit_id=unit.pk,
                label="Invalid",
                quantity=Decimal("0"),
                is_reference=False,
            )

        with connection.cursor() as cursor:
            price_constraints = connection.introspection.get_constraints(
                cursor, Price._meta.db_table,
            )
            movement_constraints = connection.introspection.get_constraints(
                cursor, Movement._meta.db_table,
            )
        self.assertTrue(price_constraints["cuaderno_price_current_cover"]["index"])
        self.assertEqual(
            price_constraints["cuaderno_price_current_cover"]["columns"][:4],
            ["space_id", "package_id", "valid_from", "id"],
        )
        self.assertTrue(movement_constraints["cuaderno_movement_space_id"]["index"])
        self.assertEqual(
            movement_constraints["cuaderno_movement_space_id"]["columns"],
            ["space_id", "id"],
        )
