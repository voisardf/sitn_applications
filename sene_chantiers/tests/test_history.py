"""Historisation : django-simple-history enregistre quoi, et surtout qui.

L'attribution nominative est la raison pour laquelle simple-history a été
retenu plutôt que les tables `h_` à déclencheurs SQL du standard SITN : un
dossier de conformité peut aboutir à une dénonciation au Ministère public,
donc « qui a modifié ce constat » doit rester traçable. Or `history_user`
n'est rempli automatiquement que dans l'admin Django — et les rapports ne
sont volontairement pas édités par l'admin. Sans
`HistoryRequestMiddleware`, toutes les lignes d'historique écrites par les
vues sur mesure portent un `history_user` NULL, en silence.
"""

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from ..models import Chantier
from .factories import a_commune, make_chantier, make_user


class HistoryRecordingTest(TestCase):
    def test_creation_and_update_are_both_recorded(self):
        chantier = make_chantier(satac_number=999401)
        chantier.site_name = "Chantier renommé"
        chantier.save()

        history = chantier.history.order_by("history_date")
        self.assertEqual([h.history_type for h in history], ["+", "~"])
        self.assertEqual(history.last().site_name, "Chantier renommé")

    def test_deletion_is_recorded(self):
        chantier = make_chantier(satac_number=999402)
        chantier.delete()

        self.assertIn(
            "-",
            [h.history_type for h in Chantier.history.filter(satac_number=999402)],
        )

    def test_history_tables_live_in_the_application_schema(self):
        # Sans table_name explicite, simple-history créerait ces tables dans
        # le schéma par défaut plutôt que dans celui de l'application.
        self.assertTrue(
            Chantier.history.model._meta.db_table.startswith('sene_chantiers"."')
        )


class HistoryUserTest(TestCase):
    """L'attribution dépend d'un middleware, donc d'un réglage global."""

    def test_middleware_is_registered(self):
        self.assertIn(
            "simple_history.middleware.HistoryRequestMiddleware",
            settings.MIDDLEWARE,
        )

    def test_middleware_comes_after_authentication(self):
        # Il lit request.user : placé trop tôt, il n'enregistrerait rien.
        self.assertLess(
            settings.MIDDLEWARE.index(
                "django.contrib.auth.middleware.AuthenticationMiddleware"
            ),
            settings.MIDDLEWARE.index(
                "simple_history.middleware.HistoryRequestMiddleware"
            ),
        )

    def test_write_through_a_view_attributes_the_change(self):
        """Le vrai cas d'usage : une écriture faite pendant une requête.

        C'est le seul moment où le middleware peut agir — il dépose
        l'utilisateur dans un thread-local pour la durée de la requête. Un
        `save()` hors cycle requête/réponse, comme dans une commande
        d'administration, n'a par construction aucun utilisateur à
        enregistrer.
        """
        user = make_user("historien")
        commune = a_commune()

        self.client.force_login(user)
        response = self.client.post(
            reverse("sene_chantiers:chantier_create", args=[999403]),
            {
                "site_name": "Chantier créé par la vue",
                "adresse": "Rue du Test 1",
                "commune": commune.pk,
                "maitre_ouvrage": "MO",
                "maitre_ouvrage_email": "mo@exemple.ch",
                "entreprise_generale": "EG",
            },
        )
        self.assertEqual(response.status_code, 302)

        chantier = Chantier.objects.get(satac_number=999403)
        self.assertEqual(chantier.history.first().history_user, user)

    def test_explicit_history_user_is_honoured(self):
        user = make_user("inspectrice")
        chantier = make_chantier(satac_number=999404)
        chantier._history_user = user
        chantier.site_name = "Modifié explicitement"
        chantier.save()

        self.assertEqual(chantier.history.first().history_user, user)
