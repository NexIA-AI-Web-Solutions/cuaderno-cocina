from django.test import TestCase
from django_scopes import scope, scopes_disabled
from cookbook.models import Food, Keyword, Space


class TreeCreationScopeTests(TestCase):
    def test_explicit_space_and_space_id_do_not_reuse_another_tenants_tree(self):
        with scopes_disabled():
            first = Space.objects.create(name="first")
            second = Space.objects.create(name="second")
            for model in (Food, Keyword):
                with self.subTest(model=model.__name__):
                    original, created = model.objects.get_or_create(space=first, name="Same name")
                    self.assertTrue(created)
                    other, created = model.objects.get_or_create(space_id=second.pk, name=" same NAME ")
                    self.assertTrue(created)
                    self.assertNotEqual(original.pk, other.pk)
                    self.assertEqual(other.space_id, second.pk)
                    repeated, created = model.objects.get_or_create(space=second, name="SAME NAME")
                    self.assertFalse(created)
                    self.assertEqual(repeated.pk, other.pk)

    def test_defaults_tenant_is_used_and_conflicting_or_absent_tenants_fail_closed(self):
        with scopes_disabled():
            first = Space.objects.create(name="first")
            second = Space.objects.create(name="second")
            original = Food.objects.create(space=first, name="Same")
            other, created = Food.objects.get_or_create(name="Same", defaults={"space": second})
            self.assertTrue(created)
            self.assertNotEqual(other.pk, original.pk)
            for kwargs in ({"space": first, "space_id": second.pk},
                           {"space": first, "defaults": {"space": second}}, {}):
                with self.subTest(kwargs=tuple(kwargs)):
                    with self.assertRaises(ValueError):
                        Food.objects.get_or_create(name="Same", **kwargs)
            with scope(space=second):
                repeated, created = Food.objects.get_or_create(name="Same")
                self.assertFalse(created)
                self.assertEqual(repeated.pk, other.pk)
