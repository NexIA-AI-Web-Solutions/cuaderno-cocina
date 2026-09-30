import json

import pytest
from django.contrib import auth
from django.urls import reverse
from django_scopes import scopes_disabled

from cookbook.models import Food, Ingredient, Step, Unit

LIST_URL = 'api:ingredient-list'
DETAIL_URL = 'api:ingredient-detail'


@pytest.mark.parametrize("arg", [
    ['a_u', 403],
    ['g1_s1', 403],
    ['u1_s1', 200],
    ['a1_s1', 200],
])
def test_list_permission(arg, request):
    c = request.getfixturevalue(arg[0])
    assert c.get(reverse(LIST_URL)).status_code == arg[1]


def test_list_space(recipe_1_s1, u1_s1, u1_s2, space_2):
    assert len(json.loads(u1_s1.get(reverse(LIST_URL)).content)['results']) == 10
    assert len(json.loads(u1_s2.get(reverse(LIST_URL)).content)['results']) == 0

    with scopes_disabled():
        step_ids = list(recipe_1_s1.steps.values_list('pk', flat=True))
        ingredients = Ingredient.objects.filter(step__pk__in=step_ids).distinct()
        ingredient_ids = list(ingredients.values_list('pk', flat=True))
        food_ids = list(ingredients.exclude(food_id=None).values_list('food_id', flat=True).distinct())
        unit_ids = list(ingredients.exclude(unit_id=None).values_list('unit_id', flat=True).distinct())
        recipe_1_s1.space = space_2
        recipe_1_s1.save()
        Step.objects.filter(pk__in=step_ids).update(space=space_2)
        Ingredient.objects.filter(pk__in=ingredient_ids).update(space=space_2)
        Food.objects.filter(pk__in=food_ids).update(space=space_2)
        Unit.objects.filter(pk__in=unit_ids).update(space=space_2)

    assert len(json.loads(u1_s1.get(reverse(LIST_URL)).content)['results']) == 0
    assert len(json.loads(u1_s2.get(reverse(LIST_URL)).content)['results']) == 10

    # ingredients that are part of a private recipe should not be listable by users not shared in that recipe
    with scopes_disabled():
        recipe_1_s1.private = True
        recipe_1_s1.save()

    assert len(json.loads(u1_s1.get(reverse(LIST_URL)).content)['results']) == 0
    assert len(json.loads(u1_s2.get(reverse(LIST_URL)).content)['results']) == 0

    with scopes_disabled():
        recipe_1_s1.shared.add(auth.get_user(u1_s2))

    assert len(json.loads(u1_s1.get(reverse(LIST_URL)).content)['results']) == 0
    assert len(json.loads(u1_s2.get(reverse(LIST_URL)).content)['results']) == 10


@pytest.mark.parametrize("arg", [
    ['a_u', 403],
    ['g1_s1', 403],
    ['u1_s1', 200],
    ['a1_s1', 200],
    ['g1_s2', 403],
    ['u1_s2', 404],
    ['a1_s2', 404],
])
def test_update(arg, request, recipe_1_s1):
    with scopes_disabled():
        i = recipe_1_s1.steps.first().ingredients.first()
        c = request.getfixturevalue(arg[0])
        r = c.patch(
            reverse(
                DETAIL_URL,
                args={i.id}
            ),
            {'note': 'new'},
            content_type='application/json'
        )
        response = json.loads(r.content)
        assert r.status_code == arg[1]
        if r.status_code == 200:
            assert response['note'] == 'new'


@pytest.mark.parametrize("arg", [
    ['a_u', 403],
    ['g1_s1', 403],
    ['u1_s1', 200],
    ['a1_s1', 404],
    ['g1_s2', 403],
    ['u1_s2', 404],
    ['a1_s2', 404],
])
def test_update_private_recipe(arg, request, recipe_1_s1):
    with scopes_disabled():
        recipe_1_s1.private = True
        recipe_1_s1.save()

        i = recipe_1_s1.steps.first().ingredients.first()
        c = request.getfixturevalue(arg[0])
        r = c.patch(
            reverse(
                DETAIL_URL,
                args={i.id}
            ),
            {'note': 'new'},
            content_type='application/json'
        )
        response = json.loads(r.content)
        assert r.status_code == arg[1]
        if r.status_code == 200:
            assert response['note'] == 'new'


@pytest.mark.parametrize("arg", [
    ['a_u', 403],
    ['g1_s1', 403],
    ['u1_s1', 201],
    ['a1_s1', 201],
])
def test_add(arg, request, u1_s2):
    c = request.getfixturevalue(arg[0])
    r = c.post(
        reverse(LIST_URL),
        {'food': {'name': 'test'}, 'unit': {'name': 'test'}, 'amount': 1},
        content_type='application/json'
    )
    response = json.loads(r.content)
    print(r)
    assert r.status_code == arg[1]
    if r.status_code == 201:
        # id can change when running multiple tests - changed to look at the name of the food
        assert response['food']['name'] == 'test'
        r = c.get(reverse(DETAIL_URL, args={response['id']}))
        assert r.status_code == 404  # ingredient is not linked to a recipe and therefore cannot be accessed
        r = u1_s2.get(reverse(DETAIL_URL, args={response['id']}))
        assert r.status_code == 404


def test_delete(u1_s1, u1_s2, a1_s1, recipe_1_s1):
    with scopes_disabled():
        i = recipe_1_s1.steps.first().ingredients.first()
        r = u1_s2.delete(
            reverse(
                DETAIL_URL,
                args={i.id}
            )
        )
        assert r.status_code == 404

        recipe_1_s1.private = True
        recipe_1_s1.save()

        r = a1_s1.delete(
            reverse(
                DETAIL_URL,
                args={i.id}
            )
        )
        assert r.status_code == 404

        recipe_1_s1.private = False
        recipe_1_s1.save()

        r = u1_s1.delete(
            reverse(
                DETAIL_URL,
                args={i.id}
            )
        )

        assert r.status_code == 204
        assert not Ingredient.objects.filter(pk=i.id).exists()
