"""Create synthetic local accounts for the three editions, never customer data."""
import os
from decimal import Decimal
from django.core.files.base import ContentFile

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django_scopes import scope, scopes_disabled

from cookbook.helper.permission_helper import create_space_for_user
from cookbook.models import Food, Household, Ingredient, InventoryEntry, InventoryLocation, Recipe, Step, Unit, UserFile
from cuaderno.models import PackageFormat, PriceVersion, RecipeYield, SpaceProfile
from cuaderno.services.ledger import apply_movement


class Command(BaseCommand):
    help = __doc__

    @transaction.atomic
    def handle(self, *args, **options):
        if os.environ.get("CUADERNO_ENV") not in {"local", "test", "development"} or connection.settings_dict["NAME"] != "cuaderno_demo":
            raise CommandError("Solo se permite la base cuaderno_demo del entorno local aislado.")
        password = os.environ.get("CUADERNO_DEMO_PASSWORD")
        if not password or len(password) < 12:
            raise CommandError("Define CUADERNO_DEMO_PASSWORD con al menos 12 caracteres; solo cuenta DEMO local.")
        for edition, title in SpaceProfile.EDITIONS:
            with scopes_disabled():
                user, created = get_user_model().objects.get_or_create(username=f"demo-{edition}")
                if created:
                    user.set_password(password)
                    user.save(update_fields=["password"])
                membership = user.userspace_set.filter(active=True).first()
                if membership is None:
                    membership = create_space_for_user(user)
                space = membership.space
                space.name = f"Cuaderno {title} DEMO"
                space.app_name = "Cuaderno Cocina"
                space.ai_enabled = False
                space.allow_sharing = False
                space.space_setup_completed = True
                space.household_setup_completed = True
                space.save(update_fields=["name", "app_name", "ai_enabled", "allow_sharing", "space_setup_completed", "household_setup_completed"])
            with scope(space=space):
                if membership.household_id is None:
                    household, _ = Household.objects.get_or_create(space=space, name="Equipo DEMO")
                    membership.household = household
                    membership.save(update_fields=["household"])
                SpaceProfile.objects.update_or_create(space=space, defaults={"edition": edition, "currency": "EUR", "price_policy": "net"})
                litres, _ = Unit.objects.get_or_create(name="L", space=space, defaults={"base_unit": "l"})
                millilitres, _ = Unit.objects.get_or_create(name="mL", space=space, defaults={"base_unit": "ml"})
                grams, _ = Unit.objects.get_or_create(name="g", space=space, defaults={"base_unit": "g"})
                oil, _ = Food.objects.get_or_create(name="Aceite DEMO", space=space)
                location, _ = InventoryLocation.objects.get_or_create(
                    space=space, household=membership.household, name="Almacén DEMO", defaults={"created_by": user},
                )
                entry, entry_created = InventoryEntry.objects.get_or_create(
                    space=space, inventory_location=location, food=oil, code="ACEITE-DEMO",
                    defaults={"created_by": user, "unit": litres, "amount": Decimal("0")},
                )
                if entry_created:
                    apply_movement(entry_id=entry.pk, space=space, user=user, kind="receipt", quantity="5",
                                   idempotency_key=f"seed-oil:{space.pk}")
                package, _ = PackageFormat.objects.get_or_create(
                    space=space, food=oil, label="Garrafa de 5 L", defaults={"unit": litres, "quantity": Decimal("5")},
                )
                if not package.prices.exists():
                    PriceVersion.objects.create(space=space, package=package, amount=Decimal("32"), valid_from=timezone.now(), created_by=user, note="Datos sintéticos locales")
                recipe, recipe_created = Recipe.objects.get_or_create(
                    name="Salsa DEMO", space=space, created_by=user,
                    defaults={"servings": 4, "private": True, "description": "Receta sintética para comprobar costes y rendimiento."},
                )
                if recipe_created:
                    step = Step.objects.create(space=space, instruction="Mezcla los ingredientes de la demostración.")
                    step.ingredients.add(Ingredient.objects.create(space=space, food=oil, unit=millilitres, amount=Decimal("400"), original_text="400 mL de aceite"))
                    recipe.steps.add(step)
                step = recipe.steps.order_by("order", "pk").first()
                if step and not step.file_id:
                    attachment = UserFile(space=space, name="Ficha DEMO sintética", created_by=user)
                    attachment.file.save("cuaderno-demo.txt", ContentFile("Datos sintéticos locales de Cuaderno Cocina; no contienen recetas del cliente.".encode()))
                    step.file = attachment
                    step.save(update_fields=["file"])
                if edition != SpaceProfile.ESENCIAL:
                    RecipeYield.objects.get_or_create(space=space, recipe=recipe, defaults={"quantity": Decimal("2000"), "unit": grams, "updated_by": user})
                    sauce, _ = Food.objects.get_or_create(name="Salsa elaborada DEMO", space=space, defaults={"recipe": recipe})
                    parent, parent_created = Recipe.objects.get_or_create(name="Plato con salsa DEMO", space=space, created_by=user, defaults={"servings": 1, "private": True})
                    if parent_created:
                        step = Step.objects.create(space=space, instruction="Sirve 300 g de la salsa elaborada.")
                        step.ingredients.add(Ingredient.objects.create(space=space, food=sauce, unit=grams, amount=Decimal("300")))
                        parent.steps.add(step)
            self.stdout.write(f"DEMO local: {user.username}, edición {edition}; contraseña fuera del registro.")
