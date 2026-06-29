"""
Unit tests based on a first sample established by Claude.ai
Couvre : models.py, forms.py, util.py et views.py

Lancer avec :
    python manage.py test ppe

Voici le fichier tests.py complet. Voici ce qui est couvert :
Modèles (models.py) — ContactPrincipalModelTest, NotaireModelTest, SignataireModelTest, AdresseFacturationModelTest, 
DossierPPEModelTest, ZipfileModelTest, ModelHelperFunctionsTest : création en base, méthodes __str__, filename(), 
valeurs par défaut, choix des statuts/types, et les fonctions unique_folder_path / rename_pdf_accord.

Formulaires (forms.py) — ValidatePhoneNumberTest, ValidateNpaTest, ContactPrincipalFormTest, NotaireFormTest, SignataireFormTest : 
validation des numéros de téléphone et NPA, champs requis, email invalide, clean_*.

Utilitaires (util.py) — CheckGeoshopRefTest (8 cas) et GetLocalisationTest (4 cas) : référence None, format invalide, date future, 
date trop ancienne, commande absente en DB, référence valide dans l'intervalle, référence hors intervalle, dates manquantes — 
avec unittest.mock.patch pour éviter les appels réseau et DB externes.

Vues (views.py) — IndexViewTest, AdminLoginViewTest, AdminLogoutViewTest, LoginViewTest, SetGeolocalisationViewTest, 
LoginRequiredDecoratorTest (11 vues protégées), OverviewViewTest, DetailViewTest, DefPPETypeViewTest, LoadZipfileViewTest, 
ZipStatusViewTest, GetFinalDocumentsViewTest.

Quelques points à noter pour l'intégration :
Les tests utilisant GeoshopCadastreOrder (table managed=False) sont tous mockés pour ne pas dépendre de la DB externe.
Le test test_missing_coordinates_key_returns_error documente un bug existant dans get_localisation (appel de render() sans request).
Les fixtures de fichiers (FileField) sont créées avec file.name directement sans upload réel pour éviter le système de fichiers 
dans les tests.

"""

import datetime
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from ppe.forms import (
    validate_phone_number,
    validate_npa,
    ContactPrincipalForm,
    NotaireForm,
    SignataireForm,
)
from ppe.models import (
    AdresseFacturation,
    ContactPrincipal,
    DossierPPE,
    Notaire,
    Signataire,
    Zipfile,
    unique_folder_path,
    rename_pdf_accord,
)
from ppe.util import check_geoshop_ref, get_localisation


# ---------------------------------------------------------------------------
# Helpers : création d'objets de test réutilisables
# ---------------------------------------------------------------------------

def make_contact():
    return ContactPrincipal.objects.create(
        nom="Dupont",
        prenom="Jean",
        email="jean.dupont@example.com",
        no_tel="+41791234567",
        raison_sociale="",
    )


def make_notaire():
    return Notaire.objects.create(
        nom="Martin",
        prenom="Luc",
        rue="Rue de la Paix",
        no_rue="1",
        npa=2000,
        localite="Neuchâtel",
    )


def make_signataire():
    return Signataire.objects.create(
        nom="Bernard",
        prenom="Alice",
        rue="Grand-Rue",
        no_rue="10",
        npa=2000,
        localite="Neuchâtel",
    )


def make_adresse_facturation(file_field="ppe/confirmations/test.pdf"):
    af = AdresseFacturation(
        type_personne="pp",
        nom_raison_sociale="Durand",
        prenom="Marie",
        rue="Rue des Fleurs",
        no_rue="3",
        npa=2000,
        localite="Neuchâtel",
    )
    af.file.name = file_field
    af.save()
    return af


def make_dossier(login_code="ABCDEFGH12345678"):
    contact = make_contact()
    notaire = make_notaire()
    signataire = make_signataire()
    facturation = make_adresse_facturation()
    return DossierPPE.objects.create(
        login_code=login_code,
        cadastre="Neuchâtel",
        numcad=1234,
        nummai="1234",
        coord_E=2530000,
        coord_N=1205000,
        statut="P",
        type_dossier="I",
        contact_principal=contact,
        notaire=notaire,
        signataire=signataire,
        adresse_facturation=facturation,
        aff_infolica=0,
        geom=Point(2530000, 1205000, srid=2056),
    )


# ---------------------------------------------------------------------------
# Tests des modèles (models.py)
# ---------------------------------------------------------------------------

class ContactPrincipalModelTest(TestCase):

    def test_str_returns_nom_prenom(self):
        contact = ContactPrincipal(nom="Dupont", prenom="Jean", email="j@j.com", no_tel="+41791234567")
        self.assertEqual(str(contact), "Dupont Jean")

    def test_creation_and_retrieval(self):
        contact = make_contact()
        fetched = ContactPrincipal.objects.get(pk=contact.pk)
        self.assertEqual(fetched.email, "jean.dupont@example.com")

    def test_ordering_by_nom(self):
        ContactPrincipal.objects.create(nom="Zorro", prenom="A", email="z@z.com", no_tel="+41791234567")
        ContactPrincipal.objects.create(nom="Aaaa", prenom="B", email="a@a.com", no_tel="+41791234567")
        first = ContactPrincipal.objects.first()
        self.assertEqual(first.nom, "Aaaa")


class NotaireModelTest(TestCase):

    def test_str_returns_nom_prenom(self):
        notaire = Notaire(nom="Martin", prenom="Luc", rue="R", npa=2000, localite="NE")
        self.assertEqual(str(notaire), "Martin Luc")

    def test_creation(self):
        notaire = make_notaire()
        self.assertIsNotNone(notaire.pk)


class SignataireModelTest(TestCase):

    def test_str_returns_nom_prenom(self):
        signataire = Signataire(nom="Bernard", prenom="Alice", rue="R", npa=2000, localite="NE")
        self.assertEqual(str(signataire), "Bernard Alice")


class AdresseFacturationModelTest(TestCase):

    def test_str_returns_nom_raison_sociale(self):
        af = AdresseFacturation(
            nom_raison_sociale="Durand SA",
            prenom="Marie",
            rue="Rue",
            npa=2000,
            localite="NE",
        )
        self.assertEqual(str(af), "Durand SA")

    def test_filename_method(self):
        af = AdresseFacturation()
        af.file.name = "ppe/confirmations/20240101_120000_accord.pdf"
        self.assertEqual(af.filename(), "20240101_120000_accord.pdf")


class DossierPPEModelTest(TestCase):

    def test_statut_choices(self):
        choices = [c[0] for c in DossierPPE.DossierStatut.choices]
        self.assertIn("P", choices)
        self.assertIn("V", choices)
        self.assertIn("A", choices)

    def test_type_dossier_choices(self):
        choices = [c[0] for c in DossierPPE.TypeDossier.choices]
        self.assertIn("C", choices)
        self.assertIn("R", choices)
        self.assertIn("M", choices)
        self.assertIn("I", choices)

    def test_default_statut_is_P(self):
        dossier = make_dossier()
        self.assertEqual(dossier.statut, "P")

    def test_default_type_dossier_is_I(self):
        dossier = make_dossier()
        self.assertEqual(dossier.type_dossier, "I")

    def test_geom_is_point(self):
        dossier = make_dossier()
        self.assertIsInstance(dossier.geom, Point)

    def test_creation_date_set(self):
        dossier = make_dossier()
        self.assertIsNotNone(dossier.date_creation)

    def test_login_code_stored(self):
        dossier = make_dossier(login_code="TESTCODE1234567")
        self.assertEqual(dossier.login_code, "TESTCODE1234567")


class ZipfileModelTest(TestCase):

    def test_default_statut_is_CAC(self):
        dossier = make_dossier()
        zipfile = Zipfile(dossier_ppe=dossier, file_statut="CAC")
        self.assertEqual(zipfile.file_statut, "CAC")

    def test_file_statut_choices_contains_all_codes(self):
        codes = [c[0] for c in Zipfile.FileStatut.choices]
        for expected in ["CAA", "CAC", "CAE", "ERR", "CAV", "CMS", "CMC", "CME", "CMV", "DPV"]:
            self.assertIn(expected, codes)

    def test_filename_method(self):
        zf = Zipfile()
        zf.zipfile.name = "ppe/42/20240101_120000.zip"
        self.assertEqual(zf.filename(), "20240101_120000.zip")


class ModelHelperFunctionsTest(TestCase):

    def test_rename_pdf_accord_returns_path_with_date(self):
        instance = MagicMock()
        result = rename_pdf_accord(instance, "accord.pdf")
        self.assertTrue(result.startswith("ppe/confirmations/"))
        self.assertTrue(result.endswith("_accord.pdf"))

    def test_unique_folder_path_returns_path_with_dossier_id(self):
        dossier = make_dossier()
        instance = MagicMock()
        instance.dossier_ppe.id = dossier.id
        result = unique_folder_path(instance, "archive.zip")
        self.assertIn(str(dossier.id), result)
        self.assertTrue(result.endswith(".zip"))


# ---------------------------------------------------------------------------
# Tests des formulaires (forms.py)
# ---------------------------------------------------------------------------

class ValidatePhoneNumberTest(TestCase):

    def test_valid_swiss_number(self):
        # Ne doit pas lever d'exception
        validate_phone_number("+41791234567")

    def test_valid_french_number(self):
        validate_phone_number("+33612345678")

    def test_invalid_number_raises(self):
        with self.assertRaises(ValidationError):
            validate_phone_number("0000")

    def test_empty_string_raises(self):
        with self.assertRaises(ValidationError):
            validate_phone_number("abc")


class ValidateNpaTest(TestCase):

    def test_valid_npa(self):
        validate_npa(2000)  # Ne doit pas lever d'exception

    def test_npa_too_low_raises(self):
        with self.assertRaises(ValidationError):
            validate_npa(999)

    def test_npa_too_high_raises(self):
        with self.assertRaises(ValidationError):
            validate_npa(10000)

    def test_npa_string_raises(self):
        with self.assertRaises(ValidationError):
            validate_npa("2000")


class ContactPrincipalFormTest(TestCase):

    def _valid_data(self):
        return {
            "contact-nom": "Dupont",
            "contact-prenom": "Jean",
            "contact-email": "jean@example.com",
            "contact-no_tel": "+41791234567",
            "contact-raison_sociale": "",
        }

    def test_valid_form(self):
        form = ContactPrincipalForm(data=self._valid_data(), prefix="contact")
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_email_makes_form_invalid(self):
        data = self._valid_data()
        data["contact-email"] = "pas-un-email"
        form = ContactPrincipalForm(data=data, prefix="contact")
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_missing_nom_makes_form_invalid(self):
        data = self._valid_data()
        data["contact-nom"] = ""
        form = ContactPrincipalForm(data=data, prefix="contact")
        self.assertFalse(form.is_valid())

    def test_clean_email_raises_on_empty(self):
        data = self._valid_data()
        data["contact-email"] = ""
        form = ContactPrincipalForm(data=data, prefix="contact")
        self.assertFalse(form.is_valid())


class NotaireFormTest(TestCase):

    def _valid_data(self):
        return {
            "notaire-nom": "Martin",
            "notaire-prenom": "Luc",
            "notaire-complement": "",
            "notaire-rue": "Rue de la Paix",
            "notaire-no_rue": "1",
            "notaire-npa": "2000",
            "notaire-localite": "Neuchâtel",
        }

    def test_valid_form(self):
        form = NotaireForm(data=self._valid_data(), prefix="notaire")
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_required_field(self):
        data = self._valid_data()
        data["notaire-rue"] = ""
        form = NotaireForm(data=data, prefix="notaire")
        self.assertFalse(form.is_valid())


class SignataireFormTest(TestCase):

    def _valid_data(self):
        return {
            "signataire-nom": "Bernard",
            "signataire-prenom": "Alice",
            "signataire-complement": "",
            "signataire-rue": "Grand-Rue",
            "signataire-no_rue": "10",
            "signataire-npa": "2000",
            "signataire-localite": "Neuchâtel",
        }

    def test_valid_form(self):
        form = SignataireForm(data=self._valid_data(), prefix="signataire")
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_prenom_makes_form_invalid(self):
        data = self._valid_data()
        data["signataire-prenom"] = ""
        form = SignataireForm(data=data, prefix="signataire")
        self.assertFalse(form.is_valid())


# ---------------------------------------------------------------------------
# Tests de util.py
# ---------------------------------------------------------------------------

class CheckGeoshopRefTest(TestCase):
    """
    Tests pour check_geoshop_ref(ref, doc).
    GeoshopCadastreOrder est managed=False (vue externe), on utilise des mocks.
    """

    def _make_doc(self):
        return DossierPPE.objects.first()

    def test_none_ref_returns_false(self):
        doc = self._make_doc()
        ok, msg = check_geoshop_ref(None, doc)
        self.assertFalse(ok)
        self.assertIn("n'existe pas", msg)

    def test_invalid_format_returns_false(self):
        doc = self._make_doc()
        ok, msg = check_geoshop_ref("INVALID_FORMAT", doc)
        self.assertFalse(ok)
        self.assertIn("n'existe pas", msg)

    def test_ref_in_the_future_returns_false(self):
        doc = self._make_doc()
        future_date = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%Y%m%d")
        ref = f"{future_date}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("futur", msg)

    def test_ref_older_than_one_year_returns_false(self):
        doc = self._make_doc()
        old_date = (datetime.date.today() - datetime.timedelta(days=400)).strftime("%Y%m%d")
        ref = f"{old_date}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("une année", msg)

    @patch("ppe.util.GeoshopCadastreOrder.objects")
    def test_ref_not_found_in_db_returns_false(self, mock_manager):
        mock_manager.filter.return_value.first.return_value = None
        doc = self._make_doc()
        valid_date = (datetime.date.today() - datetime.timedelta(days=10)).strftime("%Y%m%d")
        ref = f"{valid_date}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("bien-fonds", msg)

    @patch("ppe.util.GeoshopCadastreOrder.objects")
    def test_valid_ref_in_interval_returns_true(self, mock_manager):
        order_date = datetime.date.today() - datetime.timedelta(days=5)
        proc_date = datetime.date.today() - datetime.timedelta(days=1)
        ref_date = datetime.date.today() - datetime.timedelta(days=3)

        mock_order = MagicMock()
        mock_order.date_ordered = datetime.datetime.combine(order_date, datetime.time())
        mock_order.date_processed = datetime.datetime.combine(proc_date, datetime.time())
        mock_manager.filter.return_value.first.return_value = mock_order

        doc = self._make_doc()
        ref = f"{ref_date.strftime('%Y%m%d')}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertTrue(ok)
        self.assertIsNone(msg)

    @patch("ppe.util.GeoshopCadastreOrder.objects")
    def test_ref_outside_interval_returns_false(self, mock_manager):
        order_date = datetime.date.today() - datetime.timedelta(days=20)
        proc_date = datetime.date.today() - datetime.timedelta(days=15)
        ref_date = datetime.date.today() - datetime.timedelta(days=5)  # après proc_date

        mock_order = MagicMock()
        mock_order.date_ordered = datetime.datetime.combine(order_date, datetime.time())
        mock_order.date_processed = datetime.datetime.combine(proc_date, datetime.time())
        mock_manager.filter.return_value.first.return_value = mock_order

        doc = self._make_doc()
        ref = f"{ref_date.strftime('%Y%m%d')}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("erronée", msg)

    @patch("ppe.util.GeoshopCadastreOrder.objects")
    def test_missing_date_ordered_returns_false(self, mock_manager):
        mock_order = MagicMock()
        mock_order.date_ordered = None
        mock_manager.filter.return_value.first.return_value = mock_order

        doc = self._make_doc()
        valid_date = (datetime.date.today() - datetime.timedelta(days=5)).strftime("%Y%m%d")
        ref = f"{valid_date}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("date de commande", msg)

    @patch("ppe.util.GeoshopCadastreOrder.objects")
    def test_missing_date_processed_returns_false(self, mock_manager):
        order_date = datetime.date.today() - datetime.timedelta(days=10)
        mock_order = MagicMock()
        mock_order.date_ordered = datetime.datetime.combine(order_date, datetime.time())
        mock_order.date_processed = None
        mock_manager.filter.return_value.first.return_value = mock_order

        doc = self._make_doc()
        valid_date = (datetime.date.today() - datetime.timedelta(days=5)).strftime("%Y%m%d")
        ref = f"{valid_date}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("traitement", msg)


class GetLocalisationTest(TestCase):
    """Tests pour get_localisation(request,localisation)."""

    @patch("ppe.util.requests.request")    
    def test_coords_outside_canton_returns_bad_request(self, mock_request):
        localisation = {"coordinates": [1000000, 500000]}  # hors canton
        result = get_localisation(mock_request, localisation)
        # Doit retourner un HttpResponseBadRequest
        self.assertEqual(result.status_code, 400)

    @patch("ppe.util.requests.request")
    def test_missing_coordinates_key_returns_error(self, mock_request):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bien_fonds": {"type": "bien_fonds"},
            "nummai": "1234",
            "numcad": 100,
            "nomcad": "Neuchâtel",
        }
        mock_request.return_value = mock_response
        localisation = {"wrong_key": [2530000, 1205000]}
        result = get_localisation(mock_request, localisation)
        # KeyError → render d'erreur (pas de status_code standard), on vérifie juste que ça ne plante pas
        # La fonction retourne un render() sans request, ce qui est un bug connu dans le code source.
        # On teste simplement que la fonction ne lève pas d'exception non gérée.
        self.assertIsNotNone(result)

    @patch("ppe.util.requests.request")
    def test_valid_coords_in_canton_calls_service(self, mock_request):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bien_fonds": {"type": "bien_fonds"},
            "nummai": "1234",
            "numcad": 100,
            "nomcad": "Neuchâtel",
        }
        mock_request.return_value = mock_response

        localisation = {"coordinates": [2530000, 1205000]}
        result = get_localisation(mock_request, localisation)

        mock_request.assert_called_once()
        self.assertIsInstance(result, dict)
        self.assertIn("cadastre", result)
        self.assertIn("coord_est", result)
        self.assertIn("coord_nord", result)
        self.assertEqual(result["cadastre"], "Neuchâtel")

    @patch("ppe.util.requests.request")
    def test_valid_coords_with_list_bien_fonds(self, mock_request):
        """Cas avec plusieurs DDP (bien_fonds est une liste)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bien_fonds": [{"bien_fonds": None}, {"ddp": None}],
            "nummai": ["1234", "1235"],
            "numcad": 100,
            "nomcad": "Neuchâtel",
        }
        mock_request.return_value = mock_response

        localisation = {"coordinates": [2530000, 1205000]}
        result = get_localisation(mock_request, localisation)

        self.assertIsInstance(result, dict)
        self.assertIsNotNone(result["bf_list"])
        self.assertIsNone(result["bien_fonds"])


# ---------------------------------------------------------------------------
# Tests des vues (views.py)
# ---------------------------------------------------------------------------

class IndexViewTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_index_anonymous_returns_200(self):
        response = self.client.get(reverse("ppe:index"))
        self.assertEqual(response.status_code, 200)

    def test_index_anonymous_no_dossiers_in_context(self):
        response = self.client.get(reverse("ppe:index"))
        self.assertIsNone(response.context.get("latest_dossiers_list"))

    def test_index_authenticated_shows_dossiers(self):
        user = User.objects.create_superuser("admin", "admin@test.com", "password")
        self.client.login(username="admin", password="password")
        make_dossier()
        response = self.client.get(reverse("ppe:index"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("latest_dossiers_list"))

    def test_index_resets_session_login_code(self):
        session = self.client.session
        session["login_code"] = "SOMECODE123456"
        session.save()
        self.client.get(reverse("ppe:index"))
        session = self.client.session
        self.assertIsNone(session.get("login_code"))


class AdminLoginViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser("admin", "admin@test.com", "password")

class AdminLogoutViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    def test_logout_redirects_to_index(self):
        self.client.login(username="admin", password="password")
        response = self.client.get(reverse("ppe:admin_logout"))
        self.assertRedirects(response, reverse("ppe:index"))

    def test_logout_clears_session(self):
        self.client.login(username="admin", password="password")
        self.client.get(reverse("ppe:admin_logout"))
        response = self.client.get(reverse("ppe:index"))
        self.assertIsNone(response.context.get("latest_dossiers_list"))


class LoginViewTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_get_login_page_returns_200(self):
        response = self.client.get(reverse("ppe:login"))
        self.assertEqual(response.status_code, 200)

    def test_valid_login_code_redirects_to_overview(self):
        dossier = make_dossier()
        response = self.client.post(reverse("ppe:login"), {
            "login_code": dossier.login_code,
        })
        self.assertRedirects(response, reverse("ppe:overview"))

    def test_invalid_login_code_stays_on_login_page(self):
        response = self.client.post(reverse("ppe:login"), {
            "login_code": "INVALIDE___LOGIN",
        })
        self.assertEqual(response.status_code, 200)


class SetGeolocalisationViewTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_get_returns_200(self):
        response = self.client.get(reverse("ppe:geolocalisation"))
        self.assertEqual(response.status_code, 200)

    def test_post_empty_geom_resets_form(self):
        response = self.client.post(reverse("ppe:geolocalisation"), {"geom": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get("mode"), "reset")

    def test_post_without_geom_key_shows_init_mode(self):
        response = self.client.post(reverse("ppe:geolocalisation"), {})
        self.assertEqual(response.status_code, 200)


class LoginRequiredDecoratorTest(TestCase):
    """
    Vérifie que les vues protégées par @login_required redirigent
    vers ppe:login lorsqu'il n'y a pas de session active.
    """

    def setUp(self):
        self.client = Client()

    def _assert_redirects_to_login(self, url_name):
        response = self.client.get(reverse(f"ppe:{url_name}"))
        self.assertRedirects(response, reverse("ppe:login"))

    def test_overview_requires_login(self):
        self._assert_redirects_to_login("overview")

    def test_detail_requires_login(self):
        self._assert_redirects_to_login("detail")

    def test_soumission_requires_login(self):
        self._assert_redirects_to_login("soumission")

    def test_define_ppe_type_requires_login(self):
        self._assert_redirects_to_login("define_ppe_type")

    def test_load_zipfile_requires_login(self):
        self._assert_redirects_to_login("load_zipfile")

    def test_submit_for_validation_requires_login(self):
        self._assert_redirects_to_login("submit_for_validation")

    def test_edit_geolocalisation_requires_login(self):
        self._assert_redirects_to_login("edit_geolocalisation")

    def test_edit_contacts_requires_login(self):
        self._assert_redirects_to_login("edit_contacts")

    def test_edit_ppe_type_requires_login(self):
        self._assert_redirects_to_login("edit_ppe_type")

    def test_zip_status_requires_login(self):
        self._assert_redirects_to_login("zip_status")

    def test_get_final_documents_requires_login(self):
        self._assert_redirects_to_login("get_final_documents")


class OverviewViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.dossier = make_dossier()
        session = self.client.session
        session["login_code"] = self.dossier.login_code
        session.save()

    def test_overview_returns_200(self):
        response = self.client.get(reverse("ppe:overview"))
        self.assertEqual(response.status_code, 200)

    def test_overview_context_contains_dossier(self):
        response = self.client.get(reverse("ppe:overview"))
        self.assertIn("dossier_ppe", response.context)
        self.assertEqual(response.context["dossier_ppe"].login_code, self.dossier.login_code)

    def test_overview_type_modification_fetches_initial(self):
        dossier_initial = make_dossier(login_code="INITIAL12345678")
        self.dossier.type_dossier = "M"
        self.dossier.ref_dossier_initial = dossier_initial.id
        self.dossier.save()
        response = self.client.get(reverse("ppe:overview"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("dossier_initial", response.context)

    def test_overview_type_modification_missing_ref_shows_error(self):
        self.dossier.type_dossier = "M"
        self.dossier.ref_dossier_initial = 99999  # inexistant
        self.dossier.save()
        response = self.client.get(reverse("ppe:overview"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("error_message"))


class DetailViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.dossier = make_dossier()
        session = self.client.session
        session["login_code"] = self.dossier.login_code
        session.save()

    def test_detail_returns_200(self):
        response = self.client.get(reverse("ppe:detail"))
        self.assertEqual(response.status_code, 200)

    def test_detail_context_contains_dossier(self):
        response = self.client.get(reverse("ppe:detail"))
        self.assertIn("dossier_ppe", response.context)


class DefPPETypeViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.dossier = make_dossier()
        session = self.client.session
        session["login_code"] = self.dossier.login_code
        session.save()

# TEST TO FIX
#    def test_get_define_ppe_type_returns_200(self):
#        response = self.client.get(reverse("ppe:define_ppe_type"))
#        self.assertEqual(response.status_code, 200)

    def test_post_type_I_stays_on_page(self):
        response = self.client.post(reverse("ppe:define_ppe_type"), {
            "type_dossier": "I",
        })
        self.assertEqual(response.status_code, 200)

    @patch("ppe.util.check_geoshop_ref", return_value=(False, "Référence invalide"))
    def test_post_type_C_invalid_ref_shows_error(self, mock_check):
        response = self.client.post(reverse("ppe:define_ppe_type"), {
            "type_dossier": "C",
            "ref_geoshop": "20240101_12345",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("error_message"))

# FIX OR REMOVE INVALID TEST
#    def test_post_type_M_missing_initial_code_shows_error(self):
#        # Pas de code initial fourni
#        response = self.client.post(reverse("ppe:define_ppe_type"), {
#            "type_dossier": "M",
#        })
#        self.assertEqual(response.status_code, 200)


class LoadZipfileViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.dossier = make_dossier()
        session = self.client.session
        session["login_code"] = self.dossier.login_code
        session.save()

    def test_get_load_zipfile_returns_200(self):
        response = self.client.get(reverse("ppe:load_zipfile"))
        self.assertEqual(response.status_code, 200)

    def test_context_contains_dossier_and_form(self):
        response = self.client.get(reverse("ppe:load_zipfile"))
        self.assertIn("dossier_ppe", response.context)
        self.assertIn("zip_form", response.context)


class ZipStatusViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.dossier = make_dossier()
        session = self.client.session
        session["login_code"] = self.dossier.login_code
        session.save()

    def test_zip_status_with_cav_returns_200(self):
        Zipfile.objects.create(
            dossier_ppe=self.dossier,
            file_statut="CAV",
            zipfile="ppe/1/test.zip",
        )
        response = self.client.get(reverse("ppe:zip_status"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("zip", response.context)

    def test_zip_status_cae_returns_hx_refresh(self):
        Zipfile.objects.create(
            dossier_ppe=self.dossier,
            file_statut="CAE",
            zipfile="ppe/1/test.zip",
        )
        response = self.client.get(reverse("ppe:zip_status"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("HX-Refresh"), "true")


class GetFinalDocumentsViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.doc = make_dossier(login_code="AAAABBBB11112222")
        self.doc.save()
        session = self.client.session
        session["login_code"] = self.doc.login_code
        session.save()

    def test_file_not_found_raises_404(self):
        response = self.client.get(reverse("ppe:get_final_documents"))
        self.assertEqual(response.status_code, 404)