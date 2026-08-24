"""Ce que la coquille partagée et le partiel de champ doivent produire.

Deux points que la refactorisation des gabarits a introduits et que rien
d'autre ne garde : le ruban d'onglets est rendu pour les *deux* rapports
depuis `_report_page.html`, et `_field.html` tire l'astérisque du
formulaire. La page d'ouverture de dossier n'était par ailleurs testée
qu'en POST.
"""

from django.test import TestCase
from django.urls import reverse

from .factories import (
    a_commune,
    make_chantier,
    make_control_report,
    make_user,
    seed_sections,
)

REQUIRED_MARK = '<span class="text-danger" aria-hidden="true">*</span>'


class FormRenderingTest(TestCase):
    def setUp(self):
        a_commune()
        self.user = make_user("rendu")
        self.client.force_login(self.user)

    def test_opening_a_dossier_renders_its_form(self):
        response = self.client.get(
            reverse("sene_chantiers:chantier_create", args=[999911]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('name="site_name"', html)
        # Obligatoire d'après forms.py, donc marqué comme tel...
        self.assertIn(f"Commune {REQUIRED_MARK}", html)
        # ...et facultatif sans astérisque.
        self.assertNotIn(f"Entreprise générale {REQUIRED_MARK}", html)

    def test_both_reports_render_the_shared_tab_strip(self):
        """Le suivi porte lui aussi `data-tab-code`.

        Sans lui, le garde-fou de complétude annonçait des sections
        « undefined » sur le rapport de suivi.
        """
        chantier = make_chantier(satac_number=999912)
        report = make_control_report(chantier=chantier, user=self.user)
        seed_sections(report)

        html = self.client.get(reverse(
            "sene_chantiers:control_report_edit", args=[999912])
        ).content.decode()
        self.assertIn('id="control-report-form"', html)
        for code in ("tab01", "tab02", "tab03", "tab04"):
            self.assertIn(f'data-tab-code="{code}"', html)

        self.client.post(reverse(
            "sene_chantiers:corrective_measure_report_create", args=[999912]))
        followup = chantier.corrective_measure_reports.first()
        html = self.client.get(reverse(
            "sene_chantiers:corrective_measure_report_edit", args=[followup.pk])
        ).content.decode()
        self.assertIn('id="followup-form"', html)
        for code in ("f01", "f02", "f03", "f04"):
            self.assertIn(f'data-tab-code="{code}"', html)
