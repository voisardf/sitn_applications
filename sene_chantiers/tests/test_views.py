"""Vues : récapitulatif, rapport initial et rapport de suivi."""

from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from ..models import (
    Appreciation,
    Conformity,
    ConstructionPhase,
    ControlPoint,
    ControlReport,
    CorrectiveMeasureReport,
    FollowUpStatus,
    MeasureStatus,
    Theme,
    WeatherCondition,
)
from .factories import (
    TODAY,
    make_chantier,
    make_control_report,
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
        self.report = make_control_report(chantier=self.chantier)
        self.measure_a = make_measure(self.report, order=1)
        self.measure_b = make_measure(
            self.report, order=2, description="Bâcher les camions"
        )

    def _create_followup(self):
        self.client.post(
            reverse("sene_chantiers:corrective_measure_report_create", args=[999300])
        )
        return CorrectiveMeasureReport.objects.order_by("-pk").first()

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
