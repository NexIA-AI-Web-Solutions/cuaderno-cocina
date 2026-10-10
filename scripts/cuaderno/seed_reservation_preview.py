"""Run via manage.py shell only against reservas_preview; credentials never printed."""
from datetime import date, datetime
from decimal import Decimal
import json
import os
import secrets
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection, transaction
from django.utils import timezone
from django_scopes import scopes_disabled
from cookbook.models import Food, Household, Ingredient, InventoryEntry, InventoryLocation, MealType, Recipe, Space, Step, Supermarket, Unit, UserSpace
from cuaderno.models import MealCourse, MenuTemplate, MenuTemplateEntry, PackageFormat, PriceVersion, PurchaseOffer, SpaceProfile, StockMinimum

PREFIX = 'QA-RESERVAS-PREVIEW-20261010'
CREDENTIALS_PATH = '/tmp/reservas-preview-credentials.json'
if connection.settings_dict['NAME'] != 'reservas_preview':
    raise RuntimeError('Fixture guard: expected database reservas_preview.')
if os.path.exists(CREDENTIALS_PATH):
    raise RuntimeError('Credential file already exists; preserve its fixture instead of resetting.')
accounts, fixtures = [], []
with transaction.atomic(), scopes_disabled():
    if Space.objects.filter(name__startswith=PREFIX).exists():
        raise RuntimeError('Preview already seeded. Preserve existing fixtures instead of resetting.')
    for edition in ('esencial', 'profesional', 'integral'):
        space = Space.objects.create(name=f'{PREFIX} {edition.title()}')
        home = Household.objects.create(space=space, name='Cocina del restaurante demo')
        owners = {}
        for role, group_name in (('responsable', 'admin'), ('cocina', 'user'), ('consulta', 'guest')):
            username = f'preview-{edition}-{role}'
            password = secrets.token_urlsafe(24)
            user = get_user_model().objects.create_user(username=username, password=password)
            membership = UserSpace.objects.create(user=user, space=space, household=home, active=True)
            membership.groups.add(Group.objects.get_or_create(name=group_name)[0])
            owners[role] = user
            accounts.append(dict(edition=edition, role=role, username=username, password=password, space_id=space.pk))
        owner = owners['responsable']
        space.created_by = owner; space.save(update_fields=['created_by'])
        SpaceProfile.objects.create(space=space, edition=edition, price_policy='net', currency='EUR')
        kg = Unit.objects.create(space=space, name='kg', base_unit='kg')
        veg = Food.add_root(space=space, name='Calabacín demo')
        rice = Food.add_root(space=space, name='Arroz demo')
        recipes = []
        for name, food, amount, ratio, instruction in (
            ('Crema de calabacín demo', veg, '2', '0.8', 'Limpiar el calabacín, cocinar y triturar. Merma declarada del 20 %.'),
            ('Arroz de guarnición demo', rice, '1', '0.9', 'Pesar el arroz, lavar y cocer. Rendimiento útil declarado del 90 %.'),
        ):
            recipe = Recipe.objects.create(space=space, name=name, servings=10, created_by=owner,
                description='Receta sintética de demostración para diez raciones; no es una receta de cliente.')
            step = Step.objects.create(space=space, name='Preparación', instruction=instruction)
            ingredient = Ingredient.objects.create(space=space, food=food, unit=kg, amount=Decimal(amount),
                quantity_basis='net_usable', yield_ratio=Decimal(ratio))
            step.ingredients.add(ingredient); recipe.steps.add(step); recipes.append(recipe)
        meal = MealType.objects.create(space=space, name='Comida', created_by=owner, default=True, order=1)
        courses = [MealCourse.objects.create(space=space, meal_type=meal, name=name, position=position)
                   for position, name in enumerate(('Primer plato', 'Guarnición'))]
        menu = MenuTemplate.objects.create(space=space, name='Menú vegetal demo · dos platos', created_by=owner)
        alternate = MenuTemplate.objects.create(space=space, name='Menú sencillo demo', created_by=owner)
        for recipe, course in zip(recipes, courses):
            MenuTemplateEntry.objects.create(space=space, template=menu, day_index=0, meal_type=meal,
                course=course, recipe=recipe, servings=1)
        MenuTemplateEntry.objects.create(space=space, template=alternate, day_index=0, meal_type=meal,
            course=courses[0], recipe=recipes[0], servings=1)
        supplier = Supermarket.objects.create(space=space, name='Proveedor demo local', description='Proveedor sintético; no recibe comunicaciones.')
        packages, stock_ids = [], []
        if edition == 'integral':
            location = InventoryLocation.objects.create(space=space, household=home, name='Almacén demo', created_by=owner)
        for food, price in ((veg, '20'), (rice, '15')):
            package = PackageFormat.objects.create(space=space, food=food, unit=kg, quantity=Decimal('10'), label='Caja demo 10 kg')
            PriceVersion.objects.create(space=space, package=package, amount=Decimal(price),
                valid_from=timezone.make_aware(datetime(2026, 10, 1)), created_by=owner)
            PurchaseOffer.objects.create(space=space, package=package, supplier=supplier,
                amount=Decimal(price) - 1, created_by=owner)
            packages.append(package.pk)
            if edition == 'integral':
                stock = InventoryEntry.objects.create(space=space, inventory_location=location, food=food, unit=kg,
                    amount=Decimal('100'), expires=date(2027, 10, 12), created_by=owner)
                stock_ids.append(stock.pk)
                StockMinimum.objects.create(space=space, household=home, food=food, unit=kg, quantity=Decimal('110'), updated_by=owner)
        fixtures.append(dict(edition=edition, space_id=space.pk, household_id=home.pk,
            recipe_ids=[recipe.pk for recipe in recipes], template=menu.pk, alternate_template=alternate.pk,
            template_day=0, meal_type=meal.pk, unit=kg.pk, foods=[veg.pk, rice.pk], packages=packages,
            supplier=supplier.pk, stock_ids=stock_ids, service_date='2026-10-12', service_time='13:30'))
fd = os.open(CREDENTIALS_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as file:
    json.dump({'accounts': accounts, 'fixtures': fixtures}, file, ensure_ascii=False, indent=2)
print(json.dumps({'credentials_path': CREDENTIALS_PATH, 'fixtures': fixtures}, ensure_ascii=False))
