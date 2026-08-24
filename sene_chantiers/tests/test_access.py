"""Contrôle d'accès : SSO plus la permission de l'application."""

from django.test import Client, TestCase
from django.urls import reverse

from .factories import make_user


class AccessControlTest(TestCase):
    def setUp(self):
        self.url = reverse("sene_chantiers:home")

    def test_anonymous_is_redirected_to_login(self):
        self.assertEqual(Client().get(self.url).status_code, 302)

    def test_authenticated_user_without_the_permission_is_refused(self):
        client = Client()
        client.force_login(make_user("etranger", with_access=False))
        self.assertEqual(client.get(self.url).status_code, 403)

    def test_permission_holder_is_accepted(self):
        client = Client()
        client.force_login(make_user("membre"))
        self.assertEqual(client.get(self.url).status_code, 200)

    def test_superuser_is_accepted_without_any_grant(self):
        # Django gives a superuser every permission, so the application
        # needs no special case of its own for them.
        client = Client()
        client.force_login(
            make_user("admin", with_access=False, is_superuser=True, is_staff=True)
        )
        self.assertEqual(client.get(self.url).status_code, 200)
