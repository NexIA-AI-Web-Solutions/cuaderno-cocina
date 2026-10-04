"""Seed isolated, synthetic fixtures for the Cuaderno Playwright suite."""

import os
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django_scopes import scopes_disabled

from cookbook.models import (
    Food, Ingredient, InventoryEntry, InventoryLocation, MealPlan, MealType, Recipe,
    ShoppingList, ShoppingListEntry, Step, Supermarket, Unit, UserSpace,
)
from cuaderno.models import PackageFormat, PriceVersion, PurchaseOrder, ServicePlan, SpaceProfile
from cuaderno.services.ledger import apply_movement
from cuaderno.services.service_plans import confirm_service_plan


PREFIX = "CUADERNO-E2E"
ROLES = (("consulta", "guest"), ("cocina", "user"), ("responsable", "admin"))
WRITERS = ("cocina", "responsable")
WIDTHS = (390, 768, 1440)


def _guard():
    if (
        os.environ.get("CUADERNO_ENV") not in {"local", "test", "development"}
        or connection.settings_dict["NAME"] != "cuaderno_demo"
    ):
        raise CommandError("Solo se permite la base cuaderno_demo del entorno local aislado.")
    password = os.environ.get("CUADERNO_DEMO_PASSWORD")
    if not password or len(password) < 12:
        raise CommandError("Define CUADERNO_DEMO_PASSWORD con al menos 12 caracteres.")
    return password


class Command(BaseCommand):
    help = __doc__

    @transaction.atomic
    def handle(self, *args, **options):
        password = _guard()
        call_command("seed_cuaderno_demo", stdout=self.stdout)
        with scopes_disabled():
            for edition, _title in SpaceProfile.EDITIONS:
                self._seed_edition(edition, password)

    def _seed_edition(self, edition, password):
        User = get_user_model()
        try:
            owner = User.objects.get(username=f"demo-{edition}")
            owner_membership = owner.userspace_set.get(active=True)
        except (User.DoesNotExist, UserSpace.DoesNotExist, UserSpace.MultipleObjectsReturned) as exc:
            raise CommandError(f"La base DEMO de {edition} no está preparada de forma unívoca.") from exc
        if owner_membership.household_id is None:
            raise CommandError(f"La base DEMO de {edition} no tiene hogar operativo.")
        space = owner_membership.space
        household = owner_membership.household

        for role, group_name in ROLES:
            user, _ = User.objects.get_or_create(username=f"demo-{edition}-{role}")
            if not user.check_password(password):
                user.set_password(password)
                user.save(update_fields=["password"])
            UserSpace.objects.filter(user=user).exclude(space=space).update(active=False)
            membership, _ = UserSpace.objects.update_or_create(
                user=user, space=space, defaults={"active": True, "household": household},
            )
            membership.groups.set([Group.objects.get_or_create(name=group_name)[0]])

        litres, _ = Unit.objects.get_or_create(space=space, name=f"{PREFIX} L", defaults={"base_unit": "l"})
        food, _ = Food.objects.get_or_create(space=space, name=f"{PREFIX} aceite")
        location, _ = InventoryLocation.objects.get_or_create(
            space=space, household=household, name=f"{PREFIX} almacén", defaults={"created_by": owner},
        )
        entry, entry_created = InventoryEntry.objects.get_or_create(
            space=space,
            code="E2E-OIL",
            defaults={
                "inventory_location": location, "food": food, "unit": litres,
                "amount": Decimal("0"), "note": f"{PREFIX} datos sintéticos", "created_by": owner,
            },
        )
        if entry.food_id != food.pk or entry.unit_id != litres.pk or entry.inventory_location_id != location.pk:
            raise CommandError(f"La existencia {PREFIX} de {edition} colisiona con otro fixture.")
        if entry_created:
            apply_movement(
                entry_id=entry.pk, space=space, user=owner, kind="receipt", quantity="10000",
                idempotency_key=f"e2e-seed-stock:{space.pk}",
            )

        package, _ = PackageFormat.objects.get_or_create(
            space=space, food=food, label=f"{PREFIX} garrafa",
            defaults={"unit": litres, "quantity": Decimal("5"), "is_reference": True},
        )
        if package.unit_id != litres.pk or package.quantity != Decimal("5") or not package.is_reference:
            raise CommandError(f"El formato {PREFIX} de {edition} colisiona con otro fixture.")
        if not package.prices.exists():
            PriceVersion.objects.create(
                space=space, package=package, amount=Decimal("32"), valid_from=timezone.now(),
                note=f"{PREFIX} precio sintético", created_by=owner,
            )

        public, _ = Recipe.objects.get_or_create(
            space=space, created_by=owner, name=f"{PREFIX} receta pública",
            defaults={"servings": 4, "private": False, "description": f"{PREFIX} datos sintéticos"},
        )
        if public.private:
            public.private = False
            public.save(update_fields=["private"])
        if not public.steps.exists():
            ingredient = Ingredient.objects.create(
                space=space, food=food, unit=litres, amount=Decimal("1"),
            )
            step = Step.objects.create(space=space, name=f"{PREFIX} preparación", instruction="Preparar el aceite sintético.")
            step.ingredients.add(ingredient)
            public.steps.add(step)

        shopping, _ = ShoppingList.objects.get_or_create(space=space, name=f"{PREFIX} compra")
        shopping_entry, _ = ShoppingListEntry.objects.get_or_create(
            space=space, created_by=owner, food=food, unit=litres,
            defaults={"amount": Decimal("1"), "checked": False},
        )
        shopping_entry.shopping_lists.add(shopping)

        if edition in {SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL}:
            meal_type, _ = MealType.objects.get_or_create(
                space=space, name=f"{PREFIX} servicio", defaults={"created_by": owner},
            )
            service_date = timezone.localdate()
            starts = timezone.make_aware(datetime.combine(service_date, time(12)))
            for label in ("borrador", "confirmado"):
                plan, created = ServicePlan.objects.get_or_create(
                    space=space, household=household, title=f"{PREFIX} servicio {label}",
                    defaults={"covers": Decimal("20"), "created_by": owner,
                              "state": ServicePlan.DRAFT, "service_date": service_date},
                )
                if created:
                    plan.meal_plan = MealPlan.objects.create(
                        space=space, recipe=public, servings=plan.covers, title=plan.title,
                        created_by=owner, meal_type=meal_type, from_date=starts,
                        to_date=starts + timedelta(hours=1),
                    )
                    plan.save(update_fields=["meal_plan"])
                    if label == "confirmado":
                        confirm_service_plan(plan, owner)
                elif plan.meal_plan_id is None or plan.service_date is None:
                    raise CommandError(f"El servicio {PREFIX} de {edition} colisiona con un fixture incompleto.")

        if edition == SpaceProfile.INTEGRAL:
            supplier, _ = Supermarket.objects.get_or_create(space=space, name=f"{PREFIX} proveedor")
            for role in WRITERS:
                for width in WIDTHS:
                    marker = f"{PREFIX}-{role}-{width}"
                    order, _ = PurchaseOrder.objects.get_or_create(
                        space=space, household=household, supplier_name=marker,
                        defaults={
                            "food": food, "unit": litres, "quantity": Decimal("1000"),
                            "supplier": supplier, "package": package, "package_count": Decimal("200"),
                            "package_quantity_snapshot": Decimal("5"), "package_unit_snapshot": litres,
                            "price_snapshot": Decimal("32"), "currency_snapshot": "EUR",
                            "state": PurchaseOrder.ORDERED, "ordered_at": timezone.now(), "created_by": owner,
                        },
                    )
                    if order.food_id != food.pk or order.unit_id != litres.pk or order.quantity < Decimal("1000"):
                        raise CommandError(f"El pedido {marker} colisiona con otro fixture.")

        self.stdout.write(f"E2E: {edition}, Consulta/Cocina/Responsable; contraseña fuera del registro.")
