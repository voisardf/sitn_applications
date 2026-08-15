"""Contrôle d'accès : SSO plus appartenance au groupe."""

from django.test import Client, TestCase
from django.urls import reverse

from .factories import make_user


class AccessControlTest(TestCase):
    def setUp(self):
        self.url = reverse("sene_chantiers:home")

    def test_anonymous_is_redirected_to_login(self):
        self.assertEqual(Client().get(self.url).status_code, 302)

    def test_authenticated_non_member_is_refused(self):
        client = Client()
        client.force_login(make_user("etranger", in_group=False))
        self.assertEqual(client.get(self.url).status_code, 403)

    def test_group_member_is_accepted(self):
        client = Client()
        client.force_login(make_user("membre"))
        self.assertEqual(client.get(self.url).status_code, 200)

    def test_superuser_is_accepted_without_the_group(self):
        client = Client()
        client.force_login(
            make_user("admin", in_group=False, is_superuser=True, is_staff=True)
        )
        self.assertEqual(client.get(self.url).status_code, 200)


# ---------------------------------------------------------------------------
# Vues
# ---------------------------------------------------------------------------
