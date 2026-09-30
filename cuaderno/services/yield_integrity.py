"""Shared native-write invariant; callers hold the Space transaction lock."""
from django.db.models import Q

from cookbook.models import Food, Ingredient
from cuaderno.domain.errors import DomainError
from cuaderno.domain.ingredient_yields import validate_yield_policy


def assert_food_recipe_compatible(food_id, space_id, recipe_id):
    if recipe_id is not None and Ingredient._base_manager.filter(
        space_id=space_id, food_id=food_id,
    ).filter(~Q(quantity_basis="gross") | Q(yield_ratio__isnull=False)).exists():
        raise DomainError("double_yield", "El alimento tiene ingredientes con merma. Retira esa merma antes de vincular una subelaboración.")


def assert_ingredient_yield_compatible(ingredient):
    active = ingredient.quantity_basis != "gross" or ingredient.yield_ratio is not None
    is_subrecipe = False
    if active and ingredient.food_id is not None:
        food = Food._base_manager.filter(pk=ingredient.food_id, space_id=ingredient.space_id).values("recipe_id").first()
        if food is None:
            raise DomainError("ingredient_food_space", "El alimento no pertenece al espacio del ingrediente.")
        is_subrecipe = food["recipe_id"] is not None
    validate_yield_policy(ingredient.quantity_basis, ingredient.yield_ratio, is_subrecipe=is_subrecipe)
