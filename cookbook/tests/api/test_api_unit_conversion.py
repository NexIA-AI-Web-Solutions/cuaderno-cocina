import json

import pytest
from django.contrib import auth
from django.urls import reverse
from django_scopes import scopes_disabled

from cookbook.models import Food, MealType, Unit, UnitConversion
from cookbook.tests.conftest import get_random_food, get_random_unit

LIST_URL = 'api:unitconversion-list'
DETAIL_URL = 'api:unitconversion-detail'


@pytest.fixture()
def obj_1(space_1, u1_s1):
    return UnitConversion.objects.get_or_create(
        food=get_random_food(space_1, u1_s1),
        base_amount=100,
        base_unit=get_random_unit(space_1, u1_s1),
        converted_amount=100,
        converted_unit=get_random_unit(space_1, u1_s1),
        created_by=auth.get_user(u1_s1),
        space=space_1)[0]


@pytest.fixture
def obj_2(space_1, u1_s1):
    return UnitConversion.objects.get_or_create(
        food=get_random_food(space_1, u1_s1),
        base_amount=100,
        base_unit=get_random_unit(space_1, u1_s1),
        converted_amount=100,
        converted_unit=get_random_unit(space_1, u1_s1),
        created_by=auth.get_user(u1_s1),
        space=space_1)[0]


@pytest.mark.parametrize("arg", [
    ['a_u', 403],
    ['g1_s1', 403],
    ['u1_s1', 200],
    ['a1_s1', 200],
])
def test_list_permission(arg, request):
    c = request.getfixturevalue(arg[0])
    assert c.get(reverse(LIST_URL)).status_code == arg[1]


def test_list_space(obj_1, obj_2, u1_s1, u1_s2, space_2):
    assert json.loads(u1_s1.get(reverse(LIST_URL)).content)['count'] == 2
    assert json.loads(u1_s2.get(reverse(LIST_URL)).content)['count'] == 0

    obj_1.space = space_2
    obj_1.save()

    assert json.loads(u1_s1.get(reverse(LIST_URL)).content)['count'] == 1
    # Moving only the conversion leaves its Food/Unit references in space1.
    # Such legacy corruption must not expose their names in another Space.
    assert json.loads(u1_s2.get(reverse(LIST_URL)).content)['count'] == 0
    with scopes_disabled():
        assert UnitConversion.objects.filter(pk=obj_1.pk).exists()
        local = UnitConversion.objects.create(
            food=get_random_food(space_2, u1_s2),
            base_amount=100,
            base_unit=get_random_unit(space_2, u1_s2),
            converted_amount=100,
            converted_unit=get_random_unit(space_2, u1_s2),
            created_by=auth.get_user(u1_s2),
            space=space_2,
        )
    assert local.food.space_id == local.base_unit.space_id == local.converted_unit.space_id == space_2.pk
    assert json.loads(u1_s2.get(reverse(LIST_URL)).content)['count'] == 1


@pytest.mark.parametrize("arg", [
    ['a_u', 403],
    ['g1_s1', 403],
    ['u1_s1', 200],
    ['a1_s1', 200],
    ['g1_s2', 403],
    ['u1_s2', 404],
    ['a1_s2', 404],
])
def test_update(arg, request, obj_1):
    c = request.getfixturevalue(arg[0])
    r = c.patch(reverse(DETAIL_URL, args={obj_1.id}), {'base_amount': 1000},
                content_type='application/json')
    response = json.loads(r.content)
    assert r.status_code == arg[1]
    if r.status_code == 200:
        assert response['base_amount'] == 1000


@pytest.mark.parametrize("arg", [
    ['a_u', 403],
    ['g1_s1', 403],
    ['u1_s1', 201],
    ['a1_s1', 201],
])
def test_add(arg, request, u1_s2, space_1, u1_s1):
    with scopes_disabled():
        c = request.getfixturevalue(arg[0])
        random_unit_1 = get_random_unit(space_1, u1_s1)
        random_unit_2 = get_random_unit(space_1, u1_s1)
        random_food_1 = get_random_food(space_1, u1_s1)
        r = c.post(reverse(LIST_URL), {
            'food': {
                'id': random_food_1.id,
                'name': random_food_1.name
            },
            'base_amount': 100,
            'base_unit': {
                'id': random_unit_1.id,
                'name': random_unit_1.name
            },
            'converted_amount': 100,
            'converted_unit': {
                'id': random_unit_2.id,
                'name': random_unit_2.name
            }
        },
                   content_type='application/json')

        response = json.loads(r.content)
        print(response)
        assert r.status_code == arg[1]
        if r.status_code == 201:
            assert response['base_amount'] == 100
            r = c.get(reverse(DETAIL_URL, args={response['id']}))
            assert r.status_code == 200
            r = u1_s2.get(reverse(DETAIL_URL, args={response['id']}))
            assert r.status_code == 404


def test_add_duplicate(u1_s1, u1_s2, obj_1, space_2):
    r = u1_s1.post(reverse(LIST_URL), {
        'food': {
            'id': obj_1.food.id,
            'name': obj_1.food.name
        },
        'base_amount': 100,
        'base_unit': {
            'id': obj_1.base_unit.id,
            'name': obj_1.base_unit.name
        },
        'converted_amount': 100,
        'converted_unit': {
            'id': obj_1.converted_unit.id,
            'name': obj_1.converted_unit.name
        }
    },
                   content_type='application/json')
    response = json.loads(r.content)
    assert r.status_code == 201
    assert response['id'] == obj_1.id

    with scopes_disabled():
        before = tuple(model.objects.filter(space=space_2).count() for model in (Food, Unit, UnitConversion))
    r = u1_s2.post(reverse(LIST_URL), {
        'food': {
            'id': obj_1.food.id,
            'name': obj_1.food.name
        },
        'base_amount': 100,
        'base_unit': {
            'id': obj_1.base_unit.id,
            'name': obj_1.base_unit.name
        },
        'converted_amount': 100,
        'converted_unit': {
            'id': obj_1.converted_unit.id,
            'name': obj_1.converted_unit.name
        }
    },
                   content_type='application/json')
    assert r.status_code == 400
    with scopes_disabled():
        assert tuple(model.objects.filter(space=space_2).count() for model in (Food, Unit, UnitConversion)) == before

    # Native creation by explicit names remains supported; foreign identities
    # are not silently reinterpreted or copied into the active Space.
    r = u1_s2.post(reverse(LIST_URL), {
        'food': {'name': obj_1.food.name},
        'base_amount': 100,
        'base_unit': {'name': obj_1.base_unit.name},
        'converted_amount': 100,
        'converted_unit': {'name': obj_1.converted_unit.name},
    }, content_type='application/json')
    response = json.loads(r.content)
    assert r.status_code == 201
    assert response['id'] != obj_1.id
    with scopes_disabled():
        local = UnitConversion.objects.select_related('food', 'base_unit', 'converted_unit').get(pk=response['id'])
        assert local.space_id == local.food.space_id == local.base_unit.space_id == local.converted_unit.space_id == space_2.pk
        assert local.food_id != obj_1.food_id
        assert local.base_unit_id != obj_1.base_unit_id
        assert local.converted_unit_id != obj_1.converted_unit_id
    assert u1_s1.get(reverse(DETAIL_URL, args={local.pk})).status_code == 404


def test_delete(u1_s1, u1_s2, obj_1):
    r = u1_s2.delete(reverse(DETAIL_URL, args={obj_1.id}))
    assert r.status_code == 404

    r = u1_s1.delete(reverse(DETAIL_URL, args={obj_1.id}))

    assert r.status_code == 204
    with scopes_disabled():
        assert MealType.objects.count() == 0
