"""Carry native recipe visibility through operational Food references."""

from django.db.models import Exists, F, OuterRef, Prefetch, Q
from django.db.models.functions import Length, Substr

from cookbook.models import Food
from cuaderno.models import PackageFormat, StockMinimum
from cuaderno.services.costing import visible_recipes


def coherent_ingredients(user, space):
    """SQL scope for ingredient rows, independent of parent linkage."""
    from cookbook.models import Ingredient
    return Ingredient._base_manager.filter(space=space).filter(
        Q(unit_id__isnull=True) | Q(unit__space=space),
    ).filter(
        Q(food_id__isnull=True) | Q(food_id__in=visible_foods(user, space).values("pk")),
    )


def coherent_steps(user, space):
    """Omit an entire Step when any actual ingredient edge is inaccessible."""
    from cookbook.models import Ingredient, Step
    unavailable = Ingredient._base_manager.filter(step=OuterRef("pk")).exclude(
        pk__in=coherent_ingredients(user, space).values("pk"),
    )
    return Step._base_manager.filter(space=space).filter(
        Q(step_recipe_id__isnull=True)
        | Q(step_recipe_id__in=visible_recipes(user, space).values("pk")),
    ).filter(~Exists(unavailable))


def visible_foods(user, space, *, recipes=None):
    foods = Food.objects.filter(space=space)
    linked_foods = foods.filter(recipe_id__isnull=False)
    # Native full_name and parent expose ancestry. Hide the whole inaccessible
    # branch rather than returning a descendant with a private ancestor label.
    hidden_ancestors = Food.objects.filter(space=space, recipe_id__isnull=False).exclude(
        recipe_id__in=(visible_recipes(user, space) if recipes is None else recipes).values("pk"),
    ).annotate(_descendant_prefix=Substr(OuterRef("path"), 1, Length("path"))).filter(
        path=F("_descendant_prefix"),
    )
    # Keep the fast path inside the same statement/snapshot as the ACL. A
    # Python exists() check would race with a newly linked private ancestor.
    return foods.filter(~Exists(linked_foods) | ~Exists(hidden_ancestors))


def native_recipe_read_policy(root, request):
    """Apply root permission first; its share capability never grants children.

    Called only after the native view's get_object/object permissions. Cycles
    remain readable for repair; this is visibility, not costing validation.
    """
    from rest_framework.exceptions import NotFound
    from cookbook.helper.permission_helper import CustomRecipePermission
    from cookbook.models import Ingredient, Recipe, Step, UserSpace

    if not CustomRecipePermission().has_object_permission(request, None, root):
        raise NotFound("La receta no está disponible.")
    same_space = getattr(request.space, "pk", None) == root.space_id
    if request.space is None and getattr(request.user, "is_authenticated", False):
        # Native share middleware deliberately disables scopes/sets space=None.
        # Retain normal ACL only for an active membership in the root's Space.
        same_space = UserSpace.objects.filter(user=request.user, space=root.space, active=True).exists()
    user = request.user if same_space else None
    allowed = visible_recipes(user, root.space)
    # Union the already authorized root only. Anonymous/cross-Space share reads
    # can see public children, but not any unrelated private recipe.
    allowed = Recipe.objects.filter(space=root.space).filter(
        Q(pk__in=allowed.values("pk")) | Q(pk=root.pk),
    )
    foods = visible_foods(user, root.space, recipes=allowed)
    seen, pending, food_ids, edges = set(), [root.pk], set(), 0
    while pending:
        recipe_id = pending.pop()
        if recipe_id in seen:
            continue
        if len(seen) >= 1001:
            raise NotFound("La receta no está disponible.")
        # Inspect actual M2M edges, not ScopedManager's silently filtered view:
        # an incoherent foreign Step/Ingredient must fail the whole detail.
        recipe = allowed.filter(pk=recipe_id).prefetch_related(Prefetch(
            "steps", queryset=Step._base_manager.prefetch_related(Prefetch(
                "ingredients", queryset=Ingredient._base_manager.select_related("food", "unit"),
            )),
        )).first()
        if recipe is None:
            raise NotFound("La receta no está disponible.")
        seen.add(recipe_id)
        for step in recipe.steps.all():
            if step.space_id != root.space_id:
                raise NotFound("La receta no está disponible.")
            if step.step_recipe_id:
                pending.append(step.step_recipe_id)
                edges += 1
                if edges > 10000:
                    raise NotFound("La receta no está disponible.")
            for ingredient in step.ingredients.all():
                if (ingredient.space_id != root.space_id
                        or (ingredient.unit_id and ingredient.unit.space_id != root.space_id)
                        or (ingredient.food_id and ingredient.food.space_id != root.space_id)):
                    raise NotFound("La receta no está disponible.")
                if ingredient.food_id:
                    food_ids.add(ingredient.food_id)
                    if ingredient.food.recipe_id:
                        pending.append(ingredient.food.recipe_id)
                edges += 1
                if edges > 10000:
                    raise NotFound("La receta no está disponible.")
    if foods.filter(pk__in=food_ids).count() != len(food_ids):
        raise NotFound("La receta no está disponible.")
    return {"root_id": root.pk, "space": root.space, "recipes": allowed, "foods": foods}


def visible_packages(user, space):
    return PackageFormat.objects.filter(
        space=space, food_id__in=visible_foods(user, space).values("pk"), unit__space=space,
    )


def visible_minimums(user, space):
    return StockMinimum.objects.filter(
        space=space, food_id__in=visible_foods(user, space).values("pk"),
        unit__space=space, household__space=space,
    ).filter(
        Q(location_id__isnull=True)
        | Q(location__space=space, location__household_id=F("household_id")),
    )
