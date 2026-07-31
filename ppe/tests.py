"""
Unit tests based on a first sample established by Claude.ai, étendus depuis pour couvrir
le flux de géolocalisation (contact_principal, edit_geolocalisation, get_localisation) et
sa sécurisation.
Couvre : models.py, forms.py, util.py, views.py et templatetags/ppe_extras.py

Lancer avec :
    python manage.py test ppe --keepdb

Voici ce qui est couvert :
Modèles (models.py) — ContactPrincipalModelTest, NotaireModelTest, SignataireModelTest, AdresseFacturationModelTest,
DossierPPEModelTest, ZipfileModelTest, ModelHelperFunctionsTest : création en base, méthodes __str__, filename(),
valeurs par défaut, choix des statuts/types, et les fonctions unique_folder_path / rename_pdf_accord.

Formulaires (forms.py) — ValidatePhoneNumberTest, ValidateNpaTest, ContactPrincipalFormTest, NotaireFormTest, SignataireFormTest :
validation des numéros de téléphone et NPA, champs requis, email invalide, clean_*.

Utilitaires (util.py) — CheckGeoshopRefTest et GetLocalisationTest : référence None, format invalide, date future,
date trop ancienne, commande absente en DB, référence valide/hors intervalle, dates manquantes, coordonnées manquantes/hors
canton, réponse inattendue du service satac — avec unittest.mock.patch pour éviter les appels réseau et DB externes.

Filtre de template (templatetags/ppe_extras.py) — JsonifyFilterTest : fidélité de la sérialisation JSON et non-régression
de l'échappement HTML (protection contre l'injection dans l'attribut value="...").

Vues (views.py) — IndexViewTest, AdminLoginViewTest, AdminLogoutViewTest, LoginViewTest, SetGeolocalisationViewTest,
LoginRequiredDecoratorTest (11 vues protégées), OverviewViewTest, DetailViewTest, DefPPETypeViewTest, LoadZipfileViewTest,
ZipStatusViewTest, GetFinalDocumentsViewTest, ContactPrincipalViewTest (flux de création en 2 étapes, round-trip JSON de
localisation_ppe), EditGeolocalisationViewTest (modification de la localisation d'un dossier existant).

Quelques points à noter pour l'intégration :
- Les tests utilisant GeoshopCadastreOrder (table managed=False) sont tous mockés pour ne pas dépendre de la DB externe.
- Les fixtures de fichiers (FileField) sont créées avec file.name directement sans upload réel pour éviter le système de
  fichiers dans les tests, sauf dans ContactPrincipalViewTest qui a besoin d'un vrai upload (voir @override_settings sur
  MEDIA_ROOT) pour exercer le flux de création complet.
- La base de test est partagée entre les runs (--keepdb) et contient déjà des dossiers réels : ne jamais supposer que les
  tables sont vides, toujours filtrer par un identifiant propre au test (login_code, pk, ou delta de count()).
- coord_E/coord_N (DossierPPE) sont des IntegerField alors que get_localisation() les arrondit à 1 décimale : la valeur est
  tronquée à l'entier au moment du save() (int(2530000.4) == 2530000, pas de round "bancaire"). Les tests concernés
  documentent ce comportement explicitement plutôt que de supposer un round naïf.
- get_localisation() retourne soit un dict (succès), soit None (tout échec) ; c'était auparavant incohérent (HttpResponse,
  HttpResponseBadRequest ou dict selon le cas), ce qu'aucun appelant ne vérifiait avant d'utiliser le résultat comme un
  dict - corrigé, avec un garde-fou ajouté dans contact_principal et edit_geolocalisation.
"""

import datetime
import html
import json
import re
import shutil
import tempfile
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils.safestring import SafeString

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
from ppe.templatetags.ppe_extras import jsonify
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
        # __str__ doit concaténer nom et prénom
        contact = ContactPrincipal(nom="Dupont", prenom="Jean", email="j@j.com", no_tel="+41791234567")
        self.assertEqual(str(contact), "Dupont Jean")

    def test_creation_and_retrieval(self):
        # Création en base puis relecture par pk
        contact = make_contact()
        fetched = ContactPrincipal.objects.get(pk=contact.pk)
        self.assertEqual(fetched.email, "jean.dupont@example.com")

    def test_ordering_by_nom(self):
        # Meta.ordering = ["nom"] : tri alphabétique par défaut
        ContactPrincipal.objects.create(nom="Zorro", prenom="A", email="z@z.com", no_tel="+41791234567")
        ContactPrincipal.objects.create(nom="Aaaa", prenom="B", email="a@a.com", no_tel="+41791234567")
        first = ContactPrincipal.objects.first()
        self.assertEqual(first.nom, "Aaaa")


class NotaireModelTest(TestCase):

    def test_str_returns_nom_prenom(self):
        # __str__ doit concaténer nom et prénom
        notaire = Notaire(nom="Martin", prenom="Luc", rue="R", npa=2000, localite="NE")
        self.assertEqual(str(notaire), "Martin Luc")

    def test_creation(self):
        # Création en base réussit et attribue un pk
        notaire = make_notaire()
        self.assertIsNotNone(notaire.pk)


class SignataireModelTest(TestCase):

    def test_str_returns_nom_prenom(self):
        # __str__ doit concaténer nom et prénom
        signataire = Signataire(nom="Bernard", prenom="Alice", rue="R", npa=2000, localite="NE")
        self.assertEqual(str(signataire), "Bernard Alice")


class AdresseFacturationModelTest(TestCase):

    def test_str_returns_nom_raison_sociale(self):
        # __str__ doit renvoyer le nom/raison sociale
        af = AdresseFacturation(
            nom_raison_sociale="Durand SA",
            prenom="Marie",
            rue="Rue",
            npa=2000,
            localite="NE",
        )
        self.assertEqual(str(af), "Durand SA")

    def test_filename_method(self):
        # filename() doit renvoyer le basename du chemin stocké, pas le chemin complet
        af = AdresseFacturation()
        af.file.name = "ppe/confirmations/20240101_120000_accord.pdf"
        self.assertEqual(af.filename(), "20240101_120000_accord.pdf")


class DossierPPEModelTest(TestCase):

    def test_statut_choices(self):
        # Les valeurs de statut attendues doivent exister dans les choices
        choices = [c[0] for c in DossierPPE.DossierStatut.choices]
        self.assertIn("P", choices)
        self.assertIn("V", choices)
        self.assertIn("A", choices)

    def test_type_dossier_choices(self):
        # Les valeurs de type de dossier attendues doivent exister dans les choices
        choices = [c[0] for c in DossierPPE.TypeDossier.choices]
        self.assertIn("C", choices)
        self.assertIn("R", choices)
        self.assertIn("M", choices)
        self.assertIn("I", choices)

    def test_default_statut_is_P(self):
        # Statut par défaut à la création : "P" (en préparation)
        dossier = make_dossier()
        self.assertEqual(dossier.statut, "P")

    def test_default_type_dossier_is_I(self):
        # Type de dossier par défaut à la création : "I" (indéfini)
        dossier = make_dossier()
        self.assertEqual(dossier.type_dossier, "I")

    def test_geom_is_point(self):
        # Le champ geom doit être un objet Point (GEOS), pas une simple chaîne
        dossier = make_dossier()
        self.assertIsInstance(dossier.geom, Point)

    def test_creation_date_set(self):
        # date_creation (auto_now) doit être renseignée automatiquement
        dossier = make_dossier()
        self.assertIsNotNone(dossier.date_creation)

    def test_login_code_stored(self):
        # Le login_code fourni à la création doit être conservé tel quel
        dossier = make_dossier(login_code="TESTCODE1234567")
        self.assertEqual(dossier.login_code, "TESTCODE1234567")


class ZipfileModelTest(TestCase):

    def test_default_statut_is_CAC(self):
        # Statut par défaut d'un Zipfile : "CAC" (contrôle automatique en cours)
        dossier = make_dossier()
        zipfile = Zipfile(dossier_ppe=dossier, file_statut="CAC")
        self.assertEqual(zipfile.file_statut, "CAC")

    def test_file_statut_choices_contains_all_codes(self):
        # Tous les codes de statut de contrôle doivent être présents dans les choices
        codes = [c[0] for c in Zipfile.FileStatut.choices]
        for expected in ["CAA", "CAC", "CAE", "ERR", "CAV", "CMS", "CMC", "CME", "CMV", "DPV"]:
            self.assertIn(expected, codes)

    def test_filename_method(self):
        # filename() doit renvoyer le basename du chemin stocké, pas le chemin complet
        zf = Zipfile()
        zf.zipfile.name = "ppe/42/20240101_120000.zip"
        self.assertEqual(zf.filename(), "20240101_120000.zip")


class ModelHelperFunctionsTest(TestCase):

    def test_rename_pdf_accord_returns_path_with_date(self):
        # Le chemin généré doit être préfixé par une date et garder le nom d'origine
        instance = MagicMock()
        result = rename_pdf_accord(instance, "accord.pdf")
        self.assertTrue(result.startswith("ppe/confirmations/"))
        self.assertTrue(result.endswith("_accord.pdf"))

    def test_unique_folder_path_returns_path_with_dossier_id(self):
        # Le chemin généré doit inclure l'id du dossier PPE associé
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
        # Numéro suisse valide : ne doit pas lever d'exception
        validate_phone_number("+41791234567")

    def test_valid_french_number(self):
        # Le validateur accepte aussi les numéros d'autres pays européens (FR ici)
        validate_phone_number("+33612345678")

    def test_invalid_number_raises(self):
        # Numéro trop court/mal formé : invalide pour tous les pays testés
        with self.assertRaises(ValidationError):
            validate_phone_number("0000")

    def test_empty_string_raises(self):
        # Chaîne non numérique : invalide pour tous les pays testés
        with self.assertRaises(ValidationError):
            validate_phone_number("abc")


class ValidateNpaTest(TestCase):

    def test_valid_npa(self):
        # NPA suisse à 4 chiffres dans l'intervalle valide : ne doit pas lever d'exception
        validate_npa(2000)

    def test_npa_too_low_raises(self):
        # NPA en dessous de 1000 : hors intervalle valide
        with self.assertRaises(ValidationError):
            validate_npa(999)

    def test_npa_too_high_raises(self):
        # NPA au dessus de 9999 : hors intervalle valide
        with self.assertRaises(ValidationError):
            validate_npa(10000)

    def test_npa_string_raises(self):
        # validate_npa attend un int, pas une chaîne (même si elle contient des chiffres)
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
        # Données complètes et valides : le formulaire doit être accepté
        form = ContactPrincipalForm(data=self._valid_data(), prefix="contact")
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_email_makes_form_invalid(self):
        # Email mal formé : le formulaire doit être rejeté avec une erreur sur le champ email
        data = self._valid_data()
        data["contact-email"] = "pas-un-email"
        form = ContactPrincipalForm(data=data, prefix="contact")
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_missing_nom_makes_form_invalid(self):
        # Champ obligatoire "nom" vide : le formulaire doit être rejeté
        data = self._valid_data()
        data["contact-nom"] = ""
        form = ContactPrincipalForm(data=data, prefix="contact")
        self.assertFalse(form.is_valid())

    def test_clean_email_raises_on_empty(self):
        # clean_email() lève explicitement une erreur si l'email est vide
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
        # Données complètes et valides : le formulaire doit être accepté
        form = NotaireForm(data=self._valid_data(), prefix="notaire")
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_required_field(self):
        # Champ obligatoire "rue" vide : le formulaire doit être rejeté
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
        # Données complètes et valides : le formulaire doit être accepté
        form = SignataireForm(data=self._valid_data(), prefix="signataire")
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_prenom_makes_form_invalid(self):
        # Champ obligatoire "prenom" vide : le formulaire doit être rejeté
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
        # Référence absente : rejet immédiat, avant tout accès à la DB
        doc = self._make_doc()
        ok, msg = check_geoshop_ref(None, doc)
        self.assertFalse(ok)
        self.assertIn("n'existe pas", msg)

    def test_invalid_format_returns_false(self):
        # Référence qui ne respecte pas le format AAAAMMJJ_numero
        doc = self._make_doc()
        ok, msg = check_geoshop_ref("INVALID_FORMAT", doc)
        self.assertFalse(ok)
        self.assertIn("n'existe pas", msg)

    def test_ref_in_the_future_returns_false(self):
        # Date de commande dans le futur : forcément invalide/inventée
        doc = self._make_doc()
        future_date = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%Y%m%d")
        ref = f"{future_date}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("futur", msg)

    def test_ref_older_than_one_year_returns_false(self):
        # Date de commande de plus d'un an : données considérées trop anciennes
        doc = self._make_doc()
        old_date = (datetime.date.today() - datetime.timedelta(days=400)).strftime("%Y%m%d")
        ref = f"{old_date}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("une année", msg)

    @patch("ppe.util.GeoshopCadastreOrder.objects")
    def test_ref_not_found_in_db_returns_false(self, mock_manager):
        # Format et dates valides, mais aucune commande ne couvre ce bien-fonds
        mock_manager.filter.return_value.first.return_value = None
        doc = self._make_doc()
        valid_date = (datetime.date.today() - datetime.timedelta(days=10)).strftime("%Y%m%d")
        ref = f"{valid_date}_12345"
        ok, msg = check_geoshop_ref(ref, doc)
        self.assertFalse(ok)
        self.assertIn("bien-fonds", msg)

    @patch("ppe.util.GeoshopCadastreOrder.objects")
    def test_valid_ref_in_interval_returns_true(self, mock_manager):
        # Cas de succès : référence dans l'intervalle [date_ordered, date_processed]
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
        # Référence datée après la date de traitement de la commande : incohérente
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
        # La commande existe mais n'a pas de date_ordered valide
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
        # La commande existe mais n'a pas de date_processed valide
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


class JsonifyFilterTest(TestCase):
    """
    Tests pour le filtre de template `jsonify` (ppe/templatetags/ppe_extras.py).

    Ce filtre remplace l'ancien couple {{ dict }} (repr Python) + ast.literal_eval
    utilisé pour faire transiter `localisation_ppe` par un champ hidden. Les tests
    ci-dessous vérifient à la fois la fidélité de la sérialisation et le fait que
    Django continue bien d'échapper le résultat (le filtre ne doit pas être "safe").
    """

    def test_jsonify_serializes_dict_to_json(self):
        # Le filtre doit produire du JSON valide et fidèle aux données d'origine
        data = {"cadastre": "Neuchâtel", "coord_est": 2530000.4, "coordinates": [2530000.4, 1205000.6]}
        self.assertEqual(json.loads(jsonify(data)), data)

    def test_jsonify_result_is_not_marked_safe(self):
        # Le résultat ne doit PAS être une SafeString : si on le marquait safe,
        # Django n'échapperait plus les guillemets lors du rendu dans l'attribut
        # HTML, ce qui réintroduirait le risque d'injection corrigé ci-dessous.
        self.assertNotIsInstance(jsonify({"x": "<b>"}), SafeString)

    def test_jsonify_prevents_html_attribute_breakout(self):
        # Reproduit l'ancien bug : une valeur contenant des guillemets (ex. un
        # nom de cadastre malveillant) ne doit plus permettre de sortir de
        # l'attribut HTML value="..." pour injecter du HTML/JS.
        payload = 'Neuchâtel" onmouseover="alert(1)'
        template = Template('{% load ppe_extras %}<input value="{{ data|jsonify }}">')
        rendered = template.render(Context({"data": {"cadastre": payload}}))

        self.assertNotIn('" onmouseover="alert(1)', rendered)
        self.assertIn("&quot;", rendered)

        # Le contenu doit malgré tout rester récupérable après un aller-retour
        # navigateur (les entités HTML sont décodées par le navigateur avant
        # l'envoi du formulaire, donc html.unescape() + json.loads() doit
        # redonner exactement la valeur d'origine)
        match = re.search(r'value="(.*?)"', rendered)
        recovered = json.loads(html.unescape(match.group(1)))
        self.assertEqual(recovered["cadastre"], payload)


class GetLocalisationTest(TestCase):
    """
    Tests pour get_localisation(request, localisation).

    Contrat : la fonction retourne soit un dict de localisation (succès), soit
    None (coordonnées manquantes, hors canton, ou erreur du service satac).
    Avant correction, chaque cas d'échec retournait un type différent (un
    HttpResponse 200 pour les coordonnées manquantes, un HttpResponseBadRequest
    pour les deux autres cas), ce qu'aucun appelant (contact_principal,
    edit_geolocalisation) ne vérifiait avant d'utiliser le résultat comme un
    dict - un TypeError non géré était possible dès qu'un utilisateur tombait
    sur l'un de ces cas d'erreur. Les tests ci-dessous vérifient le contrat
    uniforme désormais en place.
    """

    @patch("ppe.util.requests.request")
    def test_coords_outside_canton_returns_none(self, mock_request):
        # Coordonnées hors du canton de Neuchâtel : échec attendu
        localisation = {"coordinates": [1000000, 500000]}
        result = get_localisation(mock_request, localisation)
        self.assertIsNone(result)
        # Le service externe ne doit même pas être appelé pour des coords hors canton
        mock_request.assert_not_called()

    @patch("ppe.util.requests.request")
    def test_missing_coordinates_key_returns_none(self, mock_request):
        # Localisation sans clé "coordinates" : échec attendu, sans exception
        localisation = {"wrong_key": [2530000, 1205000]}
        result = get_localisation(mock_request, localisation)
        self.assertIsNone(result)
        mock_request.assert_not_called()

    @patch("ppe.util.requests.request")
    def test_unknown_service_response_returns_none(self, mock_request):
        # Le service satac répond avec une structure inattendue (pas de
        # "bien_fonds") : échec attendu plutôt qu'un KeyError non géré
        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected": "shape"}
        mock_request.return_value = mock_response
        localisation = {"coordinates": [2530000, 1205000]}
        result = get_localisation(mock_request, localisation)
        self.assertIsNone(result)

    @patch("ppe.util.requests.request")
    def test_valid_coords_in_canton_calls_service(self, mock_request):
        # Cas de succès : coordonnées dans le canton, réponse satac exploitable
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
        # Page d'accueil accessible sans authentification
        response = self.client.get(reverse("ppe:index"))
        self.assertEqual(response.status_code, 200)

    def test_index_anonymous_no_dossiers_in_context(self):
        # La liste des dossiers est réservée aux admins connectés (queryset vide, pas None,
        # car la vue est désormais une ListView/FilterView)
        response = self.client.get(reverse("ppe:index"))
        self.assertFalse(response.context.get("dossiers_list"))

    def test_index_authenticated_shows_dossiers(self):
        # Un admin connecté doit voir la liste des dossiers
        user = User.objects.create_superuser("admin", "admin@test.com", "password")
        self.client.login(username="admin", password="password")
        dossier = make_dossier()
        response = self.client.get(reverse("ppe:index"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(dossier, response.context.get("dossiers_list"))

    def test_index_resets_session_login_code(self):
        # La page d'accueil doit "déconnecter" une session de dossier PPE en cours
        session = self.client.session
        session["login_code"] = "SOMECODE123456"
        session.save()
        self.client.get(reverse("ppe:index"))
        session = self.client.session
        self.assertIsNone(session.get("login_code"))

    def test_index_filters_by_cadastre(self):
        # Le filtre "cadastre" ne doit renvoyer que les dossiers correspondants
        User.objects.create_superuser("admin", "admin@test.com", "password")
        self.client.login(username="admin", password="password")
        dossier = make_dossier(login_code="AAAAAAAA11111111")

        response = self.client.get(reverse("ppe:index"), {"cadastre": "cadastre-inexistant-xyz"})
        self.assertNotIn(dossier, response.context.get("dossiers_list"))

        response = self.client.get(reverse("ppe:index"), {"cadastre": "neuchâtel"})
        self.assertIn(dossier, response.context.get("dossiers_list"))

    def test_index_default_page_size(self):
        # Par défaut, la pagination affiche 15 résultats par page
        User.objects.create_superuser("admin", "admin@test.com", "password")
        self.client.login(username="admin", password="password")
        response = self.client.get(reverse("ppe:index"))
        self.assertEqual(response.context.get("paginator").per_page, 15)

    def test_index_per_page_param_is_honored(self):
        # ?per_page= doit modifier le nombre de résultats par page (parmi les valeurs autorisées)
        User.objects.create_superuser("admin", "admin@test.com", "password")
        self.client.login(username="admin", password="password")
        response = self.client.get(reverse("ppe:index"), {"per_page": 50})
        self.assertEqual(response.context.get("paginator").per_page, 50)

    def test_index_invalid_per_page_falls_back_to_default(self):
        # Une valeur de per_page non autorisée doit être ignorée au profit du défaut
        User.objects.create_superuser("admin", "admin@test.com", "password")
        self.client.login(username="admin", password="password")
        response = self.client.get(reverse("ppe:index"), {"per_page": 9999})
        self.assertEqual(response.context.get("paginator").per_page, 15)


class AdminLoginViewTest(TestCase):
    # NB: aucun test propre à cette classe ; conservée telle que fournie par le
    # sample d'origine (le setUp seul ne teste rien).

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser("admin", "admin@test.com", "password")

class AdminLogoutViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser("admin", "admin@test.com", "password")

    def test_logout_redirects_to_index(self):
        # La déconnexion admin doit rediriger vers la page d'accueil
        self.client.login(username="admin", password="password")
        response = self.client.get(reverse("ppe:admin_logout"))
        self.assertRedirects(response, reverse("ppe:index"))

    def test_logout_clears_session(self):
        # Après déconnexion, la liste des dossiers ne doit plus être visible
        self.client.login(username="admin", password="password")
        self.client.get(reverse("ppe:admin_logout"))
        response = self.client.get(reverse("ppe:index"))
        self.assertFalse(response.context.get("dossiers_list"))


class LoginViewTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_get_login_page_returns_200(self):
        # Affichage simple du formulaire de connexion par code
        response = self.client.get(reverse("ppe:login"))
        self.assertEqual(response.status_code, 200)

    def test_valid_login_code_redirects_to_overview(self):
        # Code de connexion valide : redirection vers le récapitulatif du dossier
        dossier = make_dossier()
        response = self.client.post(reverse("ppe:login"), {
            "login_code": dossier.login_code,
        })
        self.assertRedirects(response, reverse("ppe:overview"))

    def test_invalid_login_code_stays_on_login_page(self):
        # Code de connexion inexistant : réaffiche le formulaire, pas de redirection
        response = self.client.post(reverse("ppe:login"), {
            "login_code": "INVALIDE___LOGIN",
        })
        self.assertEqual(response.status_code, 200)


class SetGeolocalisationViewTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_get_returns_200(self):
        # Affichage initial du formulaire de géolocalisation
        response = self.client.get(reverse("ppe:geolocalisation"))
        self.assertEqual(response.status_code, 200)

    def test_post_empty_geom_resets_form(self):
        # geom vide explicitement soumis : réinitialise le formulaire (mode "reset")
        response = self.client.post(reverse("ppe:geolocalisation"), {"geom": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get("mode"), "reset")

    def test_post_without_geom_key_shows_init_mode(self):
        # Aucune clé geom du tout (premier affichage) : mode "init" par défaut
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
        # Session valide (login_code) : accès au récapitulatif du dossier
        response = self.client.get(reverse("ppe:overview"))
        self.assertEqual(response.status_code, 200)

    def test_overview_context_contains_dossier(self):
        # Le dossier fourni par @login_required doit être celui de la session
        response = self.client.get(reverse("ppe:overview"))
        self.assertIn("dossier_ppe", response.context)
        self.assertEqual(response.context["dossier_ppe"].login_code, self.dossier.login_code)

    def test_overview_type_modification_fetches_initial(self):
        # Dossier de type "Modification" avec une référence valide : le
        # dossier initial correspondant doit être chargé dans le contexte
        dossier_initial = make_dossier(login_code="INITIAL12345678")
        self.dossier.type_dossier = "M"
        self.dossier.ref_dossier_initial = dossier_initial.id
        self.dossier.save()
        response = self.client.get(reverse("ppe:overview"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("dossier_initial", response.context)

    def test_overview_type_modification_missing_ref_shows_error(self):
        # Dossier de type "Modification" avec une référence inexistante :
        # doit afficher une erreur plutôt que planter
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
        # Session valide : accès à la page de détail du dossier
        response = self.client.get(reverse("ppe:detail"))
        self.assertEqual(response.status_code, 200)

    def test_detail_context_contains_dossier(self):
        # Le dossier fourni par @login_required doit être passé au template
        response = self.client.get(reverse("ppe:detail"))
        self.assertIn("dossier_ppe", response.context)


class DefPPETypeViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.dossier = make_dossier()
        session = self.client.session
        session["login_code"] = self.dossier.login_code
        session.save()

    def test_get_define_ppe_type_returns_200(self):
        # Simple affichage du formulaire (type_dossier par défaut 'I')
        response = self.client.get(reverse("ppe:define_ppe_type"))
        self.assertEqual(response.status_code, 200)

    def test_post_type_I_stays_on_page(self):
        # type_dossier 'I' (indéfini) : réaffiche le formulaire avec un message
        response = self.client.post(reverse("ppe:define_ppe_type"), {
            "type_dossier": "I",
        })
        self.assertEqual(response.status_code, 200)

    @patch("ppe.util.check_geoshop_ref", return_value=(False, "Référence invalide"))
    def test_post_type_C_invalid_ref_shows_error(self, mock_check):
        # Constitution avec une référence geoshop invalide : erreur affichée,
        # pas de sauvegarde
        response = self.client.post(reverse("ppe:define_ppe_type"), {
            "type_dossier": "C",
            "ref_geoshop": "20240101_12345",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("error_message"))

    def test_post_type_M_missing_initial_code_shows_error(self):
        # Modification sans code de dossier initial fourni : doit afficher un
        # message d'erreur clair plutôt que de planter. Corrige un bug réel où
        # `ref_error` était référencée sans jamais avoir été assignée dans ce
        # cas (UnboundLocalError), silencieusement masqué par @login_required
        # en une redirection déroutante vers la page de connexion.
        response = self.client.post(reverse("ppe:define_ppe_type"), {
            "type_dossier": "M",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("error_message"))

    def test_post_type_M_unknown_initial_code_shows_error(self):
        # Modification avec un code de dossier initial qui n'existe pas :
        # même famille de bug (dossier_ppe_initial jamais assigné avant d'être
        # utilisé dans le except non géré) - doit afficher une erreur propre.
        response = self.client.post(reverse("ppe:define_ppe_type"), {
            "type_dossier": "M",
            "initial_code": "DOESNOTEXIST1234",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("error_message"))


class LoadZipfileViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.dossier = make_dossier()
        session = self.client.session
        session["login_code"] = self.dossier.login_code
        session.save()

    def test_get_load_zipfile_returns_200(self):
        # Affichage du formulaire d'upload du zip PPE
        response = self.client.get(reverse("ppe:load_zipfile"))
        self.assertEqual(response.status_code, 200)

    def test_context_contains_dossier_and_form(self):
        # Le dossier et le formulaire d'upload doivent être passés au template
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
        # Statut "validé" (CAV) : affichage normal, le zip est dans le contexte
        Zipfile.objects.create(
            dossier_ppe=self.dossier,
            file_statut="CAV",
            zipfile="ppe/1/test.zip",
        )
        response = self.client.get(reverse("ppe:zip_status"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("zip", response.context)

    def test_zip_status_cae_returns_hx_refresh(self):
        # Statut "erreurs à corriger" (CAE) : déclenche un rafraîchissement htmx
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
        # Aucun document final n'a encore été généré pour ce dossier
        response = self.client.get(reverse("ppe:get_final_documents"))
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Tests du flux de création en 2 étapes (contact_principal) et de la
# sécurisation du round-trip JSON de `localisation_ppe` à travers le champ
# hidden. Contexte : `localisation_ppe` (contenant à la fois `coordinates` et
# sa version arrondie `coord_est`/`coord_nord`) transite par un champ hidden
# entre l'étape 1 (choix de la localisation) et l'étape 2 (contacts). Ce
# round-trip était auparavant fait via repr Python + ast.literal_eval, ce qui
# ne garantissait ni l'échappement HTML ni la cohérence des données reçues.
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ContactPrincipalViewTest(TestCase):

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client = Client()

    def _pdf_file(self):
        return SimpleUploadedFile("accord.pdf", b"%PDF-1.4 fake content", content_type="application/pdf")

    def _valid_creation_post_data(self):
        """ Données valides pour contact_form/notaire_form/signataire_form/facturation_form,
        sans les champs geom/nummai/localisation_ppe propres à la géolocalisation """
        return {
            "contact-nom": "Dupont",
            "contact-prenom": "Jean",
            "contact-email": "jean.dupont@example.com",
            "contact-no_tel": "+41791234567",
            "contact-raison_sociale": "",
            "notaire-nom": "Martin",
            "notaire-prenom": "Luc",
            "notaire-complement": "",
            "notaire-rue": "Rue de la Paix",
            "notaire-no_rue": "1",
            "notaire-npa": "2000",
            "notaire-localite": "Neuchâtel",
            "signataire-nom": "Bernard",
            "signataire-prenom": "Alice",
            "signataire-complement": "",
            "signataire-rue": "Grand-Rue",
            "signataire-no_rue": "10",
            "signataire-npa": "2000",
            "signataire-localite": "Neuchâtel",
            "facturation-type_personne": "pp",
            "facturation-nom_raison_sociale": "Durand",
            "facturation-prenom": "Marie",
            "facturation-complement": "",
            "facturation-rue": "Rue des Fleurs",
            "facturation-no_rue": "3",
            "facturation-npa": "2000",
            "facturation-localite": "Neuchâtel",
        }

    def _step1(self, coordinates, nummai="1234", satac_response=None):
        """ Simule l'étape 1 (POST du geom choisi sur la carte) et retourne le
        dict `localisation_ppe` tel qu'il serait effectivement soumis par un
        navigateur à l'étape 2 : extrait du champ hidden rendu dans le HTML,
        entités HTML décodées (comportement natif du navigateur), puis
        json.loads() du résultat """
        mock_response = MagicMock()
        mock_response.json.return_value = satac_response or {
            "bien_fonds": {"type": "bien_fonds"},
            "nummai": nummai,
            "numcad": 100,
            "nomcad": "Neuchâtel",
        }
        with patch("ppe.util.requests.request", return_value=mock_response):
            response = self.client.post(reverse("ppe:contact_principal"), {
                "geom": json.dumps({"coordinates": coordinates}),
                "nummai": nummai,
            })
        self.assertEqual(response.status_code, 200)
        match = re.search(r'value="(.*?)"\s+name="localisation_ppe"', response.content.decode())
        self.assertIsNotNone(match, "Le champ hidden localisation_ppe est absent de la page.")
        localisation_ppe = json.loads(html.unescape(match.group(1)))
        return localisation_ppe, response

    # --- Etape 1 : choix de la localisation --------------------------------

    def test_step1_missing_nummai_raises_bad_request(self):
        # Sans numéro de bien-fonds sélectionné, la requête est invalide
        response = self.client.post(reverse("ppe:contact_principal"), {
            "geom": json.dumps({"coordinates": [2530000.4, 1205000.6]}),
        })
        self.assertEqual(response.status_code, 400)

    def test_step1_localisation_without_coordinates_raises_bad_request(self):
        # Une localisation sans clé "coordinates" ne peut pas être traitée
        response = self.client.post(reverse("ppe:contact_principal"), {
            "geom": json.dumps({"foo": "bar"}),
            "nummai": "1234",
        })
        self.assertEqual(response.status_code, 400)

    def test_step1_unresolvable_localisation_raises_bad_request_not_crash(self):
        # Si get_localisation() échoue (ex. réponse inattendue du service
        # satac) elle retourne None ; sans le garde-fou correspondant dans la
        # vue, `localisation_ppe['nummai'] = nummai` plante avec un TypeError
        # non géré (None n'est pas subscriptable). Doit être un 400 propre.
        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected": "shape"}
        with patch("ppe.util.requests.request", return_value=mock_response):
            response = self.client.post(reverse("ppe:contact_principal"), {
                "geom": json.dumps({"coordinates": [2530000.4, 1205000.6]}),
                "nummai": "1234",
            })
        self.assertEqual(response.status_code, 400)

    def test_step1_hidden_field_matches_get_localisation_output(self):
        # Le hidden field doit contenir exactement les coordonnées d'origine
        # ainsi que leur version arrondie, cohérentes entre elles puisque
        # calculées en un seul appel à get_localisation()
        localisation_ppe, _ = self._step1([2530000.44, 1205000.66])
        self.assertEqual(localisation_ppe["coordinates"], [2530000.44, 1205000.66])
        self.assertEqual(localisation_ppe["coord_est"], round(2530000.44, 1))
        self.assertEqual(localisation_ppe["coord_nord"], round(1205000.66, 1))

    def test_step1_xss_payload_from_external_service_is_escaped(self):
        # Le service satac est externe et donc non fiable : si la réponse
        # contient du HTML/JS (ex. nom de cadastre corrompu), celui-ci ne
        # doit jamais apparaître tel quel dans la page (XSS stocké/réfléchi)
        payload = "<script>alert('xss')</script>"
        _, response = self._step1(
            [2530000.4, 1205000.6],
            satac_response={
                "bien_fonds": {"type": "bien_fonds"},
                "nummai": "1234",
                "numcad": 100,
                "nomcad": payload,
            },
        )
        content = response.content.decode()
        self.assertNotIn(payload, content)
        self.assertIn("&lt;script&gt;", content)

    # --- Etape 2 : création du dossier --------------------------------------

    def test_step2_creates_dossier_with_consistent_coords_and_geom(self):
        # Test fonctionnel principal : les coordonnées d'origine saisies par
        # l'utilisateur ("coordinates") doivent se retrouver telles quelles
        # dans geom, et coord_E/coord_N doivent en être dérivées - le tout à
        # partir de la même localisation, sans possibilité de dérive.
        # NB: coord_E/coord_N sont des IntegerField ; la valeur arrondie à 1
        # décimale par get_localisation() est donc tronquée à l'entier au
        # moment du save() (int(2530000.4) == 2530000) - ce test documente ce
        # comportement réel plutôt que le "round" naïf qu'on pourrait attendre.
        coordinates = [2530000.44, 1205000.66]
        localisation_ppe, _ = self._step1(coordinates)

        data = self._valid_creation_post_data()
        data["localisation_ppe"] = json.dumps(localisation_ppe)
        data["facturation-file"] = self._pdf_file()

        response = self.client.post(reverse("ppe:contact_principal"), data)

        self.assertRedirects(response, reverse("ppe:define_ppe_type"))
        # La base de test contient déjà d'autres dossiers (DB partagée avec --keepdb) :
        # on retrouve le nôtre via le login_code que la vue a mis en session.
        dossier = DossierPPE.objects.get(login_code=self.client.session["login_code"])
        self.assertEqual(dossier.coord_E, int(round(coordinates[0], 1)))
        self.assertEqual(dossier.coord_N, int(round(coordinates[1], 1)))
        self.assertEqual(list(dossier.geom.coords), coordinates)

    def test_step2_tampered_coord_est_is_rejected(self):
        # Un client malveillant (ou un bug côté client) modifie coord_est
        # dans le hidden field sans changer "coordinates" : les deux ne
        # correspondent plus, le serveur doit refuser plutôt que de créer un
        # dossier avec un geom et des coord_E/coord_N incohérents.
        count_before = DossierPPE.objects.count()
        coordinates = [2530000.4, 1205000.6]
        localisation_ppe, _ = self._step1(coordinates)
        localisation_ppe["coord_est"] = 9999999.9

        data = self._valid_creation_post_data()
        data["localisation_ppe"] = json.dumps(localisation_ppe)
        data["facturation-file"] = self._pdf_file()

        response = self.client.post(reverse("ppe:contact_principal"), data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DossierPPE.objects.count(), count_before)

    def test_step2_malformed_json_is_rejected_not_500(self):
        # Un hidden field corrompu/invalide (JSON cassé) doit être rejeté
        # proprement (400), pas provoquer une erreur serveur non gérée (500).
        count_before = DossierPPE.objects.count()
        data = self._valid_creation_post_data()
        data["localisation_ppe"] = "{not valid json"
        data["facturation-file"] = self._pdf_file()

        response = self.client.post(reverse("ppe:contact_principal"), data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DossierPPE.objects.count(), count_before)

    def test_step2_missing_localisation_ppe_is_rejected(self):
        # Champ localisation_ppe totalement absent de la requête (ex. champ
        # supprimé/désactivé via les devtools du navigateur)
        count_before = DossierPPE.objects.count()
        data = self._valid_creation_post_data()
        data["facturation-file"] = self._pdf_file()

        response = self.client.post(reverse("ppe:contact_principal"), data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DossierPPE.objects.count(), count_before)


class EditGeolocalisationViewTest(TestCase):
    """
    Tests pour edit_geolocalisation (modification de la localisation d'un
    dossier existant). Contrairement à contact_principal, il n'y a pas de
    round-trip par un champ hidden ici : cadastre/numcad/nummai/coord_E/
    coord_N/geom sont tous dérivés d'un seul appel à get_localisation() au
    moment de la modification, donc pas de dérive possible par construction -
    ce que ce test vérifie explicitement.
    """

    def setUp(self):
        self.client = Client()
        self.dossier = make_dossier()
        session = self.client.session
        session["login_code"] = self.dossier.login_code
        session.save()

    @patch("ppe.views.GeolocalisationForm.save", return_value=None)
    @patch("ppe.views.GeolocalisationForm.is_valid", return_value=True)
    @patch("ppe.util.requests.request")
    def test_edit_updates_coord_and_geom_consistently(self, mock_request, mock_is_valid, mock_save):
        # GeolocalisationForm.is_valid()/save() sont mockés : ce n'est pas le
        # widget cartographique qui est testé ici, mais le fait que
        # coord_E/coord_N/geom soient bien mis à jour ensemble à partir de la
        # même localisation nouvellement calculée.
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bien_fonds": {"type": "bien_fonds"},
            "nummai": "4321",
            "numcad": 200,
            "nomcad": "La Chaux-de-Fonds",
        }
        mock_request.return_value = mock_response

        new_coordinates = [2540000.44, 1210000.66]
        response = self.client.post(reverse("ppe:edit_geolocalisation"), {
            "geom": json.dumps({"coordinates": new_coordinates}),
            "nummai": "4321",
        })

        self.assertRedirects(response, reverse("ppe:overview"))
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.cadastre, "La Chaux-de-Fonds")
        self.assertEqual(self.dossier.numcad, 200)
        self.assertEqual(self.dossier.nummai, "4321")
        # coord_E/coord_N sont des IntegerField : la valeur arrondie à 1 décimale
        # par get_localisation() est tronquée à l'entier au moment du save().
        self.assertEqual(self.dossier.coord_E, int(round(new_coordinates[0], 1)))
        self.assertEqual(self.dossier.coord_N, int(round(new_coordinates[1], 1)))
        self.assertEqual(list(self.dossier.geom.coords), new_coordinates)

    @patch("ppe.util.requests.request")
    def test_edit_unresolvable_localisation_shows_error_not_crash(self, mock_request):
        # Si get_localisation() échoue (ex. réponse inattendue du service
        # satac) elle retourne None ; sans le garde-fou correspondant, cette
        # vue plantait avec un TypeError non géré (localisation_ppe["nummai"]
        # sur None), silencieusement transformé par @login_required en une
        # redirection vers /login - un cas particulièrement déroutant pour
        # l'utilisateur puisqu'il semble alors brutalement déconnecté.
        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected": "shape"}
        mock_request.return_value = mock_response

        original_coord_e = self.dossier.coord_E
        response = self.client.post(reverse("ppe:edit_geolocalisation"), {
            "geom": json.dumps({"type": "Point", "coordinates": [2540000.4, 1210000.6]}),
            "nummai": "4321",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get("error_message"))
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.coord_E, original_coord_e)

    @patch("ppe.util.requests.request")
    def test_edit_missing_nummai_does_not_modify_dossier(self, mock_request):
        # Sans nummai (étape intermédiaire où l'utilisateur n'a pas encore
        # choisi de bien-fonds), le dossier existant ne doit pas être modifié.
        # Le service satac est quand même appelé par get_localisation() dès
        # que "geom" est présent : on le mocke pour ne pas dépendre du réseau.
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bien_fonds": {"type": "bien_fonds"},
            "nummai": "4321",
            "numcad": 200,
            "nomcad": "La Chaux-de-Fonds",
        }
        mock_request.return_value = mock_response

        # Le widget cartographique (WMTSWithSearchWidget) soumet du GeoJSON
        # complet ({"type": "Point", ...}) : get_localisation() ne lit que la
        # clé "coordinates", mais GeolocalisationForm a besoin du GeoJSON
        # complet pour pouvoir réafficher la carte dans le render() ci-dessous.
        original_coord_e = self.dossier.coord_E
        response = self.client.post(reverse("ppe:edit_geolocalisation"), {
            "geom": json.dumps({"type": "Point", "coordinates": [2540000.4, 1210000.6]}),
        })
        self.assertEqual(response.status_code, 200)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.coord_E, original_coord_e)