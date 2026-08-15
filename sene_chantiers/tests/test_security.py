"""Sécurité : isolation entre onglets, exigée par la spécification."""

from django.test import Client, TestCase
from django.urls import reverse

from .factories import (
    make_chantier,
    make_control_report,
    make_followup,
    make_user,
)


class MemberClientMixin:
    def setUp(self):
        super().setUp()
        self.user = make_user("membre")
        self.client = Client()
        self.client.force_login(self.user)


class TabIsolationTest(MemberClientMixin, TestCase):
    """Deux dossiers ouverts côte à côte ne doivent jamais se mélanger."""

    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999400)
        self.report = make_control_report(chantier=self.chantier)
        self.other = make_chantier(satac_number=999401)

    def test_control_report_refuses_a_foreign_satac(self):
        response = self.client.post(
            reverse("sene_chantiers:control_report_edit", args=[999400]),
            {"satac_number": "999401"},
        )
        self.assertEqual(response.status_code, 403)

    def test_followup_refuses_a_foreign_satac(self):
        followup = make_followup(self.chantier)
        response = self.client.post(
            reverse(
                "sene_chantiers:corrective_measure_report_edit", args=[followup.pk]
            ),
            {"satac_number": "999401"},
        )
        self.assertEqual(response.status_code, 403)

    def test_email_manager_refuses_a_foreign_satac(self):
        response = self.client.post(
            reverse(
                "sene_chantiers:email_manager", args=["controle", self.report.pk]
            ),
            {"satac_number": "999401", "action": "save"},
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------
