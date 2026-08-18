"""Vues : récapitulatif, rapport initial et rapport de suivi."""

import json
import re
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from django.utils import timezone

from ..labels import followup_conclusion_lines
from ..models import (
    Appreciation,
    CorrectiveMeasureReport,
    EmailRecord,
    EmailStatus,
    EmailTemplate,
    Conformity,
    ConstructionPhase,
    ControlPoint,
    ControlReport,
    CorrectiveMeasureReport,
    FollowUpStatus,
    MeasureFollowUp,
    MeasureStatus,
    Theme,
    WeatherCondition,
)
from .factories import (
    TODAY,
    make_chantier,
    make_control_report,
    make_followup,
    make_measure,
    make_user,
)


class MemberClientMixin:
    def setUp(self):
        super().setUp()
        self.user = make_user("membre")
        self.client = Client()
        self.client.force_login(self.user)


class LandingViewTest(MemberClientMixin, TestCase):
    @patch("sene_chantiers.views.satac.resolve", return_value=None)
    def test_unknown_satac_offers_manual_creation(self, _resolve):
        response = self.client.get(
            reverse("sene_chantiers:chantier_landing", args=[999999])
        )
        self.assertContains(response, "Ouvrir un dossier de suivi")

    def test_existing_dossier_lists_its_reports(self):
        chantier = make_chantier(satac_number=999100)
        make_control_report(chantier=chantier)
        response = self.client.get(
            reverse("sene_chantiers:chantier_landing", args=[999100])
        )
        self.assertContains(response, "Historique des rapports")
        self.assertContains(response, "Contrôle environnemental")

    def test_dossier_without_report_shows_the_empty_state(self):
        make_chantier(satac_number=999101)
        response = self.client.get(
            reverse("sene_chantiers:chantier_landing", args=[999101])
        )
        self.assertContains(response, "Aucun rapport pour ce chantier")


class ControlReportViewTest(MemberClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999200)

    def _create_report(self):
        self.client.post(
            reverse("sene_chantiers:control_report_create", args=[999200])
        )
        return ControlReport.objects.get(chantier=self.chantier)

    def test_creation_materialises_the_fixed_sections(self):
        report = self._create_report()
        self.assertEqual(report.theme_assessments.count(), Theme.objects.count())
        self.assertEqual(
            report.control_point_answers.count(), ControlPoint.objects.count()
        )
        # Une réponse vide n'est pas un N.A. : elle reste à remplir.
        self.assertEqual(
            report.control_point_answers.exclude(conformity="").count(), 0
        )

    def test_second_creation_does_not_duplicate(self):
        self._create_report()
        self.client.post(
            reverse("sene_chantiers:control_report_create", args=[999200])
        )
        self.assertEqual(
            ControlReport.objects.filter(chantier=self.chantier).count(), 1
        )

    def _payload(self, report, appreciation_value, measures=0, **extra):
        data = {
            "satac_number": str(self.chantier.satac_number),
            "control_date": TODAY.isoformat(),
            "weather_condition": WeatherCondition.objects.first().pk,
            "construction_phase": ConstructionPhase.objects.first().pk,
            "temperature": "18.5",
            "next_control_date": (TODAY + timedelta(days=30)).isoformat(),
            "signature_date": "",
            "global_appreciation": appreciation_value,
            "global_appreciation_is_manual_override": "",
            "observations_generales": "R.A.S.",
            "procedure_controle": "Visite sur site.",
        }
        assessments = list(report.theme_assessments.all())
        data["themes-TOTAL_FORMS"] = len(assessments)
        data["themes-INITIAL_FORMS"] = len(assessments)
        for index, assessment in enumerate(assessments):
            data[f"themes-{index}-id"] = assessment.pk
            data[f"themes-{index}-appreciation"] = assessment.appreciation
            data[f"themes-{index}-synthesis_remarks"] = "R.A.S."
            data[f"themes-{index}-detail_observations"] = "R.A.S."
        answers = list(report.control_point_answers.all())
        data["answers-TOTAL_FORMS"] = len(answers)
        data["answers-INITIAL_FORMS"] = len(answers)
        for index, answer in enumerate(answers):
            data[f"answers-{index}-id"] = answer.pk
            data[f"answers-{index}-conformity"] = Conformity.YES
        data["measures-TOTAL_FORMS"] = measures
        data["measures-INITIAL_FORMS"] = 0
        for index in range(measures):
            data[f"measures-{index}-order"] = index + 1
            data[f"measures-{index}-description"] = "Corriger le tri"
            data[f"measures-{index}-responsible"] = "Entreprise"
            data[f"measures-{index}-deadline"] = (
                TODAY + timedelta(days=20)
            ).isoformat()
            data[f"measures-{index}-status"] = MeasureStatus.OPEN
        data.update(extra)
        return data

    def test_conforme_report_saves_without_measures(self):
        report = self._create_report()
        response = self.client.post(
            reverse("sene_chantiers:control_report_edit", args=[999200]),
            self._payload(report, Appreciation.VERT),
        )
        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.global_appreciation, Appreciation.VERT)

    def test_non_conforme_report_requires_a_measure(self):
        """Règle inter-lignes : ni clean() ni contrainte ne peut la porter."""
        report = self._create_report()
        response = self.client.post(
            reverse("sene_chantiers:control_report_edit", args=[999200]),
            self._payload(report, Appreciation.ROUGE, measures=0),
        )
        self.assertEqual(response.status_code, 200)  # réaffiché, pas enregistré
        self.assertEqual(report.corrective_measures.count(), 0)

    def test_non_conforme_report_saves_with_a_measure(self):
        report = self._create_report()
        response = self.client.post(
            reverse("sene_chantiers:control_report_edit", args=[999200]),
            self._payload(report, Appreciation.ROUGE, measures=1),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(report.corrective_measures.count(), 1)

    def test_draft_accepts_an_incomplete_form(self):
        report = self._create_report()
        response = self.client.post(
            reverse("sene_chantiers:control_report_edit", args=[999200]),
            {
                "satac_number": "999200",
                "save_draft": "1",
                "control_date": "",
                "themes-TOTAL_FORMS": "0",
                "themes-INITIAL_FORMS": "0",
                "answers-TOTAL_FORMS": "0",
                "answers-INITIAL_FORMS": "0",
                "measures-TOTAL_FORMS": "0",
                "measures-INITIAL_FORMS": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ControlReport.objects.filter(pk=report.pk).exists())

    def test_locked_report_is_read_only(self):
        report = self._create_report()
        report.is_locked = True
        report.save(update_fields=["is_locked"])

        response = self.client.get(
            reverse("sene_chantiers:control_report_edit", args=[999200])
        )
        self.assertContains(response, "Lecture seule")
        self.assertNotContains(response, "Enregistrer le rapport")

        self.client.post(
            reverse("sene_chantiers:control_report_edit", args=[999200]),
            self._payload(report, Appreciation.ROUGE, measures=1),
        )
        self.assertEqual(report.corrective_measures.count(), 0)


class CorrectiveMeasureReportViewTest(MemberClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999300)
        self.report = make_control_report(
            chantier=self.chantier,
            global_appreciation=Appreciation.ROUGE,
            next_control_date=TODAY + timedelta(days=10),
        )
        self.measure_a = make_measure(self.report, order=1)
        self.measure_b = make_measure(
            self.report, order=2, description="Bâcher les camions"
        )

    def _create_followup(self):
        self.client.post(
            reverse("sene_chantiers:corrective_measure_report_create", args=[999300])
        )
        return (
            CorrectiveMeasureReport.objects.filter(chantier=self.chantier)
            .order_by("-pk")
            .first()
        )

    def test_first_followup_chains_from_the_initial_report(self):
        followup = self._create_followup()
        self.assertIsNone(followup.previous_followup)
        self.assertEqual(followup.measure_followups.count(), 2)

    def test_second_followup_chains_from_the_first(self):
        first = self._create_followup()
        rows = list(first.measure_followups.order_by("original_measure__order"))
        rows[0].status = FollowUpStatus.NOT_DONE
        rows[0].new_deadline = TODAY + timedelta(days=10)
        rows[0].save()
        rows[1].status = FollowUpStatus.CLOSED
        rows[1].save()

        second = self._create_followup()

        self.assertEqual(second.previous_followup_id, first.pk)
        carried = {
            row.original_measure.order: row.state_at_previous_control
            for row in second.measure_followups.all()
        }
        # L'état repris est celui du dernier contrôle, pas du rapport initial.
        self.assertEqual(carried[1], FollowUpStatus.NOT_DONE)
        self.assertEqual(carried[2], FollowUpStatus.CLOSED)

    def test_followup_needs_the_initial_report(self):
        orphan = make_chantier(satac_number=999301)
        response = self.client.post(
            reverse(
                "sene_chantiers:corrective_measure_report_create", args=[999301]
            ),
            follow=True,
        )
        self.assertEqual(
            CorrectiveMeasureReport.objects.filter(chantier=orphan).count(), 0
        )
        self.assertContains(response, "contrôle initial doit exister")


# ---------------------------------------------------------------------------
# Sécurité : isolation entre onglets
# ---------------------------------------------------------------------------


class ConclusionTextSourceTest(MemberClientMixin, TestCase):
    """Le texte de conclusion n'existe qu'à un seul endroit.

    Il vivait en double — une fois dans `labels.py` pour le PDF, une fois
    dans un littéral JS pour l'aperçu du formulaire — et les deux avaient
    déjà divergé (« restent » contre « demeurent » insuffisantes).
    """

    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999310)
        make_control_report(
            chantier=self.chantier, global_appreciation=Appreciation.ROUGE
        )
        self.followup = make_followup(self.chantier)

    def test_page_serves_the_server_side_wording(self):
        response = self.client.get(
            reverse(
                "sene_chantiers:corrective_measure_report_edit",
                args=[self.followup.pk],
            )
        )
        self.assertContains(response, 'id="conclusion-lines"')
        # json_script escapes non-ASCII, so parse rather than substring-match.
        payload = re.search(
            r'id="conclusion-lines" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.S,
        )
        self.assertIsNotNone(payload)
        self.assertEqual(json.loads(payload.group(1)), followup_conclusion_lines())

    def test_the_wording_is_not_restated_in_the_template(self):
        source = (
            settings.BASE_DIR
            / "sene_chantiers/templates/sene_chantiers"
            / "corrective_measure_report.html"
        )
        body = source.read_text(encoding="utf-8")
        self.assertNotIn("Toutes les mesures correctives ont été", body)
        self.assertIn("conclusion-lines", body)


class CaseClosureTest(MemberClientMixin, TestCase):
    """Deux états distincts en fin de cycle.

    Une visite conforme arrête la chaîne : aucun nouveau suivi. Mais le
    dossier n'est *clos* qu'une fois le courriel envoyé — tant qu'il ne
    l'est pas, le rapport reste modifiable et une correction rouvre le
    cycle.
    """

    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999500)
        self.report = make_control_report(
            self.chantier, global_appreciation=Appreciation.ROUGE,
            next_control_date=TODAY + timedelta(days=10),
        )
        self.measure = make_measure(self.report)

    def _followup(self, appreciation_value, concluded=True, **kwargs):
        """Un suivi tel que l'inspecteur le laisse après sa visite.

        `concluded=False` reproduit un rapport fraîchement créé, encore
        vierge : son appréciation est la valeur par défaut, pas un constat.
        """
        kwargs.setdefault("follow_up_date", TODAY)
        report = CorrectiveMeasureReport.objects.create(
            chantier=self.chantier,
            inspector=self.user,
            global_appreciation=appreciation_value,
            **kwargs,
        )
        MeasureFollowUp.objects.create(
            corrective_measure_report=report,
            original_measure=self.measure,
            findings="Mesure vérifiée sur place." if concluded else "",
            status=(
                FollowUpStatus.CLOSED
                if appreciation_value == Appreciation.VERT
                else FollowUpStatus.NOT_DONE
            ),
            new_deadline=(
                None
                if appreciation_value == Appreciation.VERT
                else TODAY + timedelta(days=10)
            ),
        )
        return report

    def test_dossier_is_open_while_the_site_is_not_compliant(self):
        self._followup(Appreciation.ROUGE)
        self.assertFalse(self.chantier.is_compliant)
        self.assertFalse(self.chantier.is_closed)

    def test_a_blank_report_does_not_stop_the_cycle(self):
        """Son `vert` est la valeur par défaut du champ, pas un constat."""
        self._followup(Appreciation.VERT, concluded=False)
        self.assertFalse(self.chantier.is_compliant)

    def test_a_compliant_visit_stops_the_cycle_but_does_not_close_it(self):
        """Le dossier n'est clos qu'une fois le courriel parti."""
        followup = self._followup(Appreciation.VERT)
        self.assertTrue(self.chantier.is_compliant)
        self.assertFalse(self.chantier.is_closed)
        self.assertFalse(followup.is_locked)  # donc encore modifiable

    def test_sending_the_email_closes_the_dossier(self):
        followup = self._followup(Appreciation.VERT)
        followup.is_locked = True  # ce que fait l'envoi
        followup.save(update_fields=["is_locked"])
        self.assertTrue(self.chantier.is_closed)

    def test_correcting_a_compliant_report_reopens_the_cycle(self):
        """L'inspecteur s'est trompé : la mesure repasse ouverte."""
        followup = self._followup(Appreciation.VERT)
        self.assertTrue(self.chantier.is_compliant)

        row = followup.measure_followups.get()
        row.status = FollowUpStatus.OPEN
        row.new_deadline = TODAY + timedelta(days=10)
        row.save()
        followup.global_appreciation = Appreciation.JAUNE
        followup.save(update_fields=["global_appreciation"])

        self.assertFalse(self.chantier.is_compliant)
        response = self.client.post(
            reverse(
                "sene_chantiers:corrective_measure_report_create", args=[999500]
            ),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.chantier.corrective_measure_reports.count(), 2)

    def test_compliance_follows_the_most_recent_visit(self):
        """Un ancien contrôle conforme ne clôt rien si un suivi l'a rouvert."""
        self._followup(Appreciation.VERT, follow_up_date=TODAY - timedelta(days=10))
        self._followup(Appreciation.ROUGE, follow_up_date=TODAY)
        self.assertFalse(self.chantier.is_compliant)

    def test_landing_distinguishes_compliant_from_closed(self):
        followup = self._followup(Appreciation.VERT)
        url = reverse("sene_chantiers:chantier_landing", args=[999500])

        response = self.client.get(url)
        self.assertContains(response, "courriel à envoyer")
        self.assertNotContains(response, "Nouveau suivi")

        followup.is_locked = True
        followup.save(update_fields=["is_locked"])
        response = self.client.get(url)
        self.assertContains(response, "Dossier clos")

    def test_creating_a_follow_up_on_a_compliant_dossier_is_refused(self):
        self._followup(Appreciation.VERT)
        before = self.chantier.corrective_measure_reports.count()

        response = self.client.post(
            reverse(
                "sene_chantiers:corrective_measure_report_create", args=[999500]
            ),
            follow=True,
        )

        self.assertEqual(
            self.chantier.corrective_measure_reports.count(), before
        )
        self.assertContains(response, "aucun nouveau suivi")

    def test_the_email_remains_available_once_compliant(self):
        """Le courriel de levée reste la dernière action possible."""
        followup = self._followup(Appreciation.VERT)
        response = self.client.get(
            reverse("sene_chantiers:email_manager", args=["suivi", followup.pk])
        )
        self.assertEqual(response.status_code, 200)


class CourrielsListTest(MemberClientMixin, TestCase):
    """La liste des courriels ouvre le gestionnaire du rapport concerné."""

    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999510)
        self.report = make_control_report(self.chantier)

    def test_each_courriel_links_to_its_report(self):
        EmailRecord.objects.create(
            chantier=self.chantier,
            control_report=self.report,
            template_used=EmailTemplate.CONFORME,
            recipient_email="destinataire@example.ch",
            subject="Objet",
            body="Corps",
            status=EmailStatus.SENT,
            sent_at=timezone.now(),
        )
        response = self.client.get(
            reverse("sene_chantiers:chantier_landing", args=[999510])
        )
        self.assertContains(
            response,
            reverse(
                "sene_chantiers:email_manager", args=["controle", self.report.pk]
            ),
        )
        # Plus de bouton désactivé « étape à venir » dans cette colonne.
        self.assertNotContains(response, "étape à venir")


class SituationMapTest(MemberClientMixin, TestCase):
    """Le plan de situation n'apparaît que lorsqu'il y a une géométrie."""

    def setUp(self):
        super().setUp()
        from django.contrib.gis.geos import Point

        self.chantier = make_chantier(
            satac_number=999320,
            geom=Point(2558956, 1210120, srid=settings.DEFAULT_SRID),
        )

    def test_map_is_rendered_when_the_dossier_is_located(self):
        response = self.client.get(
            reverse("sene_chantiers:chantier_landing", args=[999320])
        )
        self.assertContains(response, "situation-map-config")
        self.assertContains(response, "Coordonnées CH")
        # Le fond est le plan de ville, pas le plan cadastral global.
        self.assertContains(response, "plan_ville")
        # La couche des permis vient du géoportail, symbologie comprise.
        self.assertContains(response, "at034_autorisation_construire")

    def test_no_map_block_at_all_without_geometry(self):
        self.chantier.geom = None
        self.chantier.save()
        response = self.client.get(
            reverse("sene_chantiers:chantier_landing", args=[999320])
        )
        # Ni carte, ni cadre vide : le texte prend toute la largeur.
        self.assertNotContains(response, "situation-map-config")
        self.assertNotContains(response, "sc-situation-map")
        self.assertContains(response, "col-12")

    def test_coordinates_use_the_swiss_separator(self):
        from ..templatetags.sene_chantiers_extras import coord_ch

        self.assertEqual(coord_ch(2558956), "2\u2019558\u2019956")
        self.assertEqual(coord_ch(1210120.4), "1\u2019210\u2019120")
        self.assertEqual(coord_ch(None), "")


class ScriptPrefixTest(MemberClientMixin, TestCase):
    """L'application doit fonctionner sous un préfixe de script.

    Les instances déployées tournent sous ROOTURL (« /apps_inter »).
    Tout chemin écrit à la main ignore ce préfixe : la panne n'apparaît
    que sur les serveurs, jamais en local, ce qui la rend coûteuse à
    diagnostiquer. Deux régressions de ce type ont déjà eu lieu — le
    téléversement de photos et ce bandeau.
    """

    def test_banner_does_not_depend_on_a_hardcoded_path(self):
        """Le bandeau se décide sur le résolveur, pas sur request.path."""
        source = (
            settings.BASE_DIR / "sene_chantiers/context_processors.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('request.path.startswith("/sene_chantiers/")', source)
        self.assertIn("resolver_match", source)

    def test_banner_is_shown_inside_the_app(self):
        make_chantier(satac_number=999330)
        response = self.client.get(
            reverse("sene_chantiers:chantier_landing", args=[999330])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sc_overdue_count", response.context)

    def test_banner_is_absent_outside_the_app(self):
        response = self.client.get("/admin/login/", follow=True)
        self.assertNotIn("sc_overdue_count", response.context or {})

    def test_no_template_writes_an_application_path_by_hand(self):
        """Tout lien doit passer par {% url %} ou {% static %}."""
        import re

        root = settings.BASE_DIR / "sene_chantiers/templates"
        offenders = []
        for path in root.rglob("*.html"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if re.search(r'(href|src|action)="/(sene_chantiers|assets)', line):
                    offenders.append(f"{path.name}: {line.strip()[:60]}")
        self.assertEqual(offenders, [])


class ControlReportRoundTripTest(MemberClientMixin, TestCase):
    """Remplir le formulaire comme un navigateur, enregistrer, relire.

    Les autres tests construisent la charge utile à la main et passent
    donc à côté d'un champ obligatoire que le gabarit ne rend pas : le
    rapport ne pouvait alors jamais être enregistré, la page se
    réaffichait sans message, et l'inspecteur retrouvait son rapport vide
    et « Conforme ». Ici la charge utile est extraite du formulaire rendu.
    """

    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999340)
        self.url = reverse(
            "sene_chantiers:control_report_edit", args=[999340]
        )
        self.client.post(
            reverse("sene_chantiers:control_report_create", args=[999340])
        )
        self.report = ControlReport.objects.get(chantier=self.chantier)

    def _payload_from_rendered_form(self):
        html = self.client.get(self.url).content.decode()
        data = {}
        for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*>', html):
            tag, name = m.group(0), m.group(1)
            if 'type="radio"' in tag or 'type="checkbox"' in tag:
                if "checked" in tag:
                    v = re.search(r'value="([^"]*)"', tag)
                    data[name] = v.group(1) if v else "on"
                else:
                    data.setdefault(name, "")
                continue
            v = re.search(r'value="([^"]*)"', tag)
            data[name] = v.group(1) if v else ""
        for m in re.finditer(
                r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
            name, body = m.group(1), m.group(2)
            sel = (re.search(r'<option value="([^"]*)"[^>]*selected', body)
                   or re.search(r'<option value="([^"]+)"', body))
            data[name] = sel.group(1) if sel else ""
        for m in re.finditer(
                r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', html, re.S):
            data[m.group(1)] = m.group(2).strip()
        return data

    def test_every_required_field_is_actually_rendered(self):
        """Un champ obligatoire absent du gabarit rend le formulaire insoluble."""
        data = self._payload_from_rendered_form()
        for theme_index in range(Theme.objects.count()):
            self.assertIn(f"themes-{theme_index}-synthesis_remarks", data)
            self.assertIn(f"themes-{theme_index}-detail_observations", data)

    def test_filling_the_form_saves_and_computes_the_appreciation(self):
        data = self._payload_from_rendered_form()
        answers = [k for k in data
                   if k.startswith("answers-") and k.endswith("-conformity")]
        for i, key in enumerate(answers):
            data[key] = Conformity.NO if i == 0 else Conformity.YES
        for key in list(data):
            if key.startswith("themes-") and (
                    key.endswith("-synthesis_remarks")
                    or key.endswith("-detail_observations")):
                data[key] = "Constat"
        data["observations_generales"] = "Observation"
        data["procedure_controle"] = "Procédure"

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)

        self.report.refresh_from_db()
        self.assertEqual(
            self.report.control_point_answers.exclude(conformity="").count(),
            self.report.control_point_answers.count(),
        )
        self.assertEqual(self.report.observations_generales, "Observation")
        # Un « Non » : le rapport ne peut pas rester Conforme.
        self.assertNotEqual(self.report.global_appreciation, Appreciation.VERT)

    def test_a_rejected_save_says_so(self):
        """L'échec doit être visible, quel que soit l'onglet fautif."""
        data = self._payload_from_rendered_form()
        for key in list(data):
            if key.endswith("-detail_observations"):
                data[key] = ""          # champ obligatoire laissé vide
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pas été enregistré")


class RequiredFieldsAreRenderedTest(MemberClientMixin, TestCase):
    """Tout champ obligatoire doit exister dans le gabarit.

    Un champ obligatoire que le gabarit ne rend pas rend le formulaire
    insoluble : l'inspecteur ne peut pas le remplir, la validation échoue
    à chaque envoi, et l'erreur n'a aucun élément où s'afficher. C'est
    exactement ce qui bloquait le rapport de contrôle
    (`ThemeAssessment.detail_observations`). Les tests qui construisent
    leur charge utile à la main ne peuvent pas voir ce défaut.
    """

    @staticmethod
    def _rendered_names(html):
        names = set()
        for pattern in (r'<input[^>]*name="([^"]+)"',
                        r'<select[^>]*name="([^"]+)"',
                        r'<textarea[^>]*name="([^"]+)"'):
            names |= set(re.findall(pattern, html))
        return names

    def _assert_all_required_rendered(self, url, form, formsets):
        html = self.client.get(url).content.decode()
        present = self._rendered_names(html)
        missing = []
        for name, field in form.fields.items():
            if field.required and form.add_prefix(name) not in present:
                missing.append(f"{form.__class__.__name__}.{name}")
        for label, formset in formsets.items():
            for index, subform in enumerate(formset.forms):
                for name, field in subform.fields.items():
                    if field.required and subform.add_prefix(name) not in present:
                        missing.append(f"{label}[{index}].{name}")
        self.assertEqual(missing, [], f"champs obligatoires non rendus : {missing}")

    def test_control_report_renders_every_required_field(self):
        from ..forms import (ControlReportForm, ThemeAssessmentFormSet,
                             ControlPointAnswerFormSet, CorrectiveMeasureFormSet)

        chantier = make_chantier(satac_number=999350)
        self.client.post(
            reverse("sene_chantiers:control_report_create", args=[999350])
        )
        report = ControlReport.objects.get(chantier=chantier)
        self._assert_all_required_rendered(
            reverse("sene_chantiers:control_report_edit", args=[999350]),
            ControlReportForm(instance=report),
            {
                "themes": ThemeAssessmentFormSet(instance=report, prefix="themes"),
                "answers": ControlPointAnswerFormSet(instance=report, prefix="answers"),
                "measures": CorrectiveMeasureFormSet(instance=report, prefix="measures"),
            },
        )

    def test_followup_report_renders_every_required_field(self):
        from ..forms import CorrectiveMeasureReportForm, MeasureFollowUpFormSet

        chantier = make_chantier(satac_number=999351)
        report = make_control_report(
            chantier=chantier, global_appreciation=Appreciation.ROUGE
        )
        make_measure(report, order=1)
        self.client.post(
            reverse("sene_chantiers:corrective_measure_report_create",
                    args=[999351])
        )
        followup = CorrectiveMeasureReport.objects.get(chantier=chantier)
        self._assert_all_required_rendered(
            reverse("sene_chantiers:corrective_measure_report_edit",
                    args=[followup.pk]),
            CorrectiveMeasureReportForm(instance=followup),
            {"followups": MeasureFollowUpFormSet(instance=followup,
                                                 prefix="followups")},
        )
