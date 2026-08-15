"""Recherche et résolution d'un numéro SATAC.

Ces tests utilisent de vraies lignes fictives insérées dans les tables
partagées, plutôt que des mocks : c'est le chemin réel — requête ORM,
jointure `idcom` vers `numcom` — qui est vérifié.

Le repli HTTP reste mocké, lui : appeler l'endpoint public depuis une
suite de tests serait lent et dépendrait du réseau.
"""

from unittest.mock import patch

from django.test import TestCase

from ..models import Chantier, SearchSatac
from ..services import satac
from .factories import (
    a_commune,
    make_chantier,
    require_table,
    seed_at034,
    seed_search_satac,
)


class SatacResolveTest(TestCase):
    """Résolution complète : localisation puis attributs du permis."""

    def setUp(self):
        seed_search_satac()
        seed_at034()

    def test_resolve_returns_geometry_and_commune(self):
        result = satac.resolve(990001)

        self.assertIsNotNone(result)
        self.assertEqual(result.satac_number, 990001)
        self.assertEqual(result.label, "N° SATAC: 990001")
        self.assertEqual(result.geom.x, 2558956)
        self.assertEqual(result.geom.y, 1210120)
        self.assertEqual(result.commune_name, "Val-de-Ruz")
        self.assertEqual(result.warnings, [])

    def test_commune_is_resolved_through_idcom(self):
        """at034.idcom correspond à Commune.numcom, pas à sa clé primaire."""
        result = satac.resolve(990001)
        self.assertIsNotNone(result.commune)
        self.assertEqual(result.commune.numcom, 74)

    def test_permit_without_search_index_entry_still_resolves(self):
        result = satac.resolve(990004)

        self.assertIsNotNone(result)
        self.assertEqual(result.commune_name, "Val-de-Ruz")
        # La géométrie vient alors du permis lui-même.
        self.assertIsNotNone(result.geom)
        self.assertTrue(
            any("index de recherche" in w for w in result.warnings)
        )

    def test_locator_without_permit_is_reported(self):
        result = satac.resolve(990003)

        self.assertIsNotNone(result)
        self.assertEqual(result.commune_name, "")
        self.assertTrue(
            any("autorisation de construire" in w for w in result.warnings)
        )

    def test_unknown_satac_returns_none(self):
        self.assertIsNone(satac.resolve(123456789))

    def test_non_numeric_input_is_rejected(self):
        self.assertIsNone(satac.resolve("abc"))
        self.assertIsNone(satac.resolve(None))


class SatacSearchTest(TestCase):
    """Autocomplétion sur le numéro."""

    def setUp(self):
        seed_search_satac()

    def test_exact_number_is_found(self):
        results = satac.search("990001")
        self.assertEqual([r.satac_number for r in results], [990001])
        self.assertEqual(results[0].source, "db")

    def test_partial_number_matches_the_fixtures(self):
        results = satac.search("9900", limit=50)
        found = {r.satac_number for r in results}
        self.assertTrue({990001, 990002, 990003} <= found)

    def test_blank_term_returns_nothing(self):
        self.assertEqual(satac.search("  "), [])
        self.assertEqual(satac.search(None), [])

    def test_limit_is_respected(self):
        self.assertLessEqual(len(satac.search("9900", limit=2)), 2)

    # Un numéro à 8 chiffres ne peut correspondre à aucune ligne locale :
    # la base de test est un clone de la production et contient de vrais
    # numéros à 6 chiffres.
    ABSENT_LOCALLY = "98765432"

    @patch("sene_chantiers.services.satac.requests.get")
    def test_http_fallback_used_when_nothing_found_locally(self, mock_get):
        mock_get.return_value.ok = True
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {
            "features": [
                {"properties": {"label": "N° SATAC: 123101"}},
                {"properties": {"label": "sans numéro"}},
            ]
        }

        results = satac.search(self.ABSENT_LOCALLY)

        mock_get.assert_called_once()
        self.assertEqual([r.satac_number for r in results], [123101])
        self.assertEqual(results[0].source, "http")

    @patch("sene_chantiers.services.satac.requests.get")
    def test_local_hit_does_not_call_the_network(self, mock_get):
        satac.search("990001")
        mock_get.assert_not_called()

    @patch(
        "sene_chantiers.services.satac.requests.get",
        side_effect=satac.requests.RequestException("réseau indisponible"),
    )
    def test_http_failure_is_not_fatal(self, _mock_get):
        self.assertEqual(satac.search(self.ABSENT_LOCALLY), [])


class SatacLookupEndpointTest(TestCase):
    """L'endpoint d'autocomplétion signale les dossiers déjà ouverts."""

    def setUp(self):
        from django.test import Client

        from .factories import make_user

        seed_search_satac()
        self.client = Client()
        self.client.force_login(make_user("recherche"))

    def test_existing_dossier_is_flagged(self):
        make_chantier(satac_number=990001)
        response = self.client.get(
            "/sene_chantiers/api/satac-lookup/", {"query": "9900"}
        )
        results = {r["satac_number"]: r["has_dossier"] for r in response.json()["results"]}
        self.assertTrue(results[990001])
        self.assertFalse(results[990002])
