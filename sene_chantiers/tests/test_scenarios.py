"""Parcours complets, joués à travers les pages comme un inspecteur.

Chaque scénario suit une trajectoire métier de bout en bout et vérifie
l'état du dossier après chaque étape. Ils tiennent volontairement en peu
de lignes : la mécanique de remplissage vit dans `inspector.py`, et les
mêmes étapes sont reproductibles à la main — voir
`doc/bookstack/10_scenarios_de_test.md`.

Ce qui distingue ces tests des autres : la charge utile est extraite du
formulaire **rendu**, jamais construite depuis l'ORM. Un champ obligatoire
absent du gabarit rend le formulaire insoluble pour une personne tout en
laissant passer un test construit à la main — c'est précisément ce qui
avait échappé à la suite.
"""
from datetime import timedelta

from django.test import TestCase

from ..models import (
    Appreciation,
    Chantier,
    ControlReport,
    CorrectiveMeasureReport,
    EmailStatus,
    FinalClosureState,
    FollowUpStatus,
)
from .factories import TODAY, make_chantier
from .inspector import Inspector


class ScenarioTestCase(TestCase):
    """Outillage commun aux parcours."""

    satac = 990000

    def setUp(self):
        super().setUp()
        self.inspector = Inspector()
        self.chantier = make_chantier(satac_number=self.satac)

    # -- raccourcis de lecture ----------------------------------------
    def refreshed(self):
        return Chantier.objects.get(pk=self.chantier.pk)

    def control_report(self):
        return ControlReport.objects.get(chantier=self.chantier)

    def followups(self):
        return list(CorrectiveMeasureReport.objects
                    .filter(chantier=self.chantier).order_by("pk"))

    def assert_saved(self, response, step):
        self.assertEqual(
            response.status_code, 302,
            f"{step} : le formulaire a été refusé au lieu d'être enregistré")


class CompliantFirstVisitScenario(ScenarioTestCase):
    """① Une seule visite, chantier conforme, dossier clos."""

    satac = 990001

    def test_single_compliant_visit_closes_the_dossier(self):
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=0)
        self.assert_saved(page.save(), "contrôle initial conforme")

        report = self.control_report()
        self.assertEqual(report.global_appreciation, Appreciation.VERT)
        self.assertEqual(report.corrective_measures.count(), 0)

        # Conforme mais pas encore clos : le courriel n'est pas parti.
        self.assertTrue(self.refreshed().is_compliant)
        self.assertFalse(self.refreshed().is_closed)

        self.inspector.send_email("controle", report.pk)
        report.refresh_from_db()
        self.assertTrue(report.is_locked, "l'envoi doit verrouiller le rapport")
        self.assertTrue(self.refreshed().is_closed)

        # Plus aucun suivi possible sur un dossier conforme.
        self.assertEqual(self.followups(), [])


class MinorIssuesTwoVisitsScenario(ScenarioTestCase):
    """② Deux écarts mineurs, un suivi partiel, une troisième visite conforme."""

    satac = 990002

    def test_two_measures_resolved_over_two_followups(self):
        deadline = TODAY + timedelta(days=20)
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(
            page, non_compliant_points=1, measures=2, deadline=deadline)
        self.assert_saved(page.save(), "contrôle initial avec deux mesures")

        report = self.control_report()
        self.assertEqual(report.corrective_measures.count(), 2)
        self.assertNotEqual(report.global_appreciation, Appreciation.VERT)
        self.inspector.send_email("controle", report.pk)

        # Suivi 1 : une mesure fermée, une encore ouverte.
        page = self.inspector.open_followup(self.satac)
        self.inspector.fill_followup(
            page,
            statuses=[FollowUpStatus.CLOSED, FollowUpStatus.OPEN],
            next_control_date=TODAY + timedelta(days=40),
        )
        self.assert_saved(page.save(), "premier suivi partiel")

        first = self.followups()[0]
        self.assertEqual(first.global_appreciation, Appreciation.JAUNE)
        self.assertFalse(self.refreshed().is_compliant)
        self.inspector.send_email("suivi", first.pk)

        # Suivi 2 : tout est conforme, la chaîne s'arrête.
        page = self.inspector.open_followup(self.satac)
        self.inspector.fill_followup(
            page, statuses=[FollowUpStatus.CLOSED, FollowUpStatus.CLOSED])
        self.assert_saved(page.save(), "second suivi conforme")

        second = self.followups()[-1]
        self.assertEqual(second.global_appreciation, Appreciation.VERT)
        self.assertTrue(self.refreshed().is_compliant)
        self.assertFalse(self.refreshed().is_closed)

        self.inspector.send_email("suivi", second.pk)
        self.assertTrue(self.refreshed().is_closed)


class DenunciationScenario(ScenarioTestCase):
    """③ Non-conformités majeures, escalade, dénonciation, visite finale."""

    satac = 990003

    def test_escalation_then_final_visit_closes_the_dossier(self):
        deadline = TODAY + timedelta(days=15)
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(
            page, non_compliant_points=3, measures=2, deadline=deadline)
        self.assert_saved(page.save(), "contrôle initial non conforme")

        report = self.control_report()
        self.assertEqual(report.global_appreciation, Appreciation.ROUGE)
        self.inspector.send_email("controle", report.pk)

        # Suivi 1 : rien de fait.
        page = self.inspector.open_followup(self.satac)
        self.inspector.fill_followup(
            page,
            statuses=[FollowUpStatus.NOT_DONE, FollowUpStatus.NOT_DONE],
            next_control_date=TODAY + timedelta(days=30),
        )
        self.assert_saved(page.save(), "premier suivi sans progrès")
        self.assertEqual(self.followups()[0].global_appreciation,
                         Appreciation.ROUGE)
        self.inspector.send_email("suivi", self.followups()[0].pk)

        # Suivi 2 : toujours insuffisant, l'inspecteur escalade.
        page = self.inspector.open_followup(self.satac)
        self.inspector.fill_followup(
            page,
            statuses=[FollowUpStatus.NOT_DONE, FollowUpStatus.OPEN],
            next_control_date=TODAY + timedelta(days=45),
            escalate=True,
        )
        self.assert_saved(page.save(), "second suivi avec escalade")

        second = self.followups()[1]
        self.assertTrue(second.is_denunciation_escalation)
        # Le dossier est désormais engagé : l'admin ne pourra plus le rouvrir.
        self.assertTrue(self.refreshed().has_entered_denunciation_track)
        self.inspector.send_email("suivi", second.pk)

        # Visite finale obligatoire après la dénonciation : tout est conforme.
        page = self.inspector.open_followup(self.satac)
        self.inspector.fill_followup(
            page,
            statuses=[FollowUpStatus.CLOSED, FollowUpStatus.CLOSED],
            closure_state=FinalClosureState.AUTHORITY_ENFORCED,
        )
        self.assert_saved(page.save(), "visite finale")

        final = self.followups()[-1]
        self.assertEqual(final.global_appreciation, Appreciation.VERT)
        self.assertEqual(final.final_closure_state,
                         FinalClosureState.AUTHORITY_ENFORCED)
        self.inspector.send_email("suivi", final.pk)
        self.assertTrue(self.refreshed().is_closed)
        self.assertTrue(self.refreshed().has_entered_denunciation_track)


class DraftThenResumeScenario(ScenarioTestCase):
    """⑤ Deux façons de travailler : d'un trait, ou en brouillon puis reprise."""

    satac = 990004

    def test_interrupted_entry_survives_as_a_draft(self):
        page = self.inspector.open_control_report(self.satac)
        # L'inspecteur est interrompu : rien n'est rempli, il enregistre un
        # brouillon. Un brouillon accepte l'incomplet, par définition.
        page.set("observations_generales", "Début de saisie, à compléter")
        response = page.save_draft()
        self.assertEqual(response.status_code, 302,
                         "un brouillon ne doit jamais être refusé")

        report = self.control_report()
        self.assertEqual(report.observations_generales,
                         "Début de saisie, à compléter")
        self.assertFalse(report.is_locked)

        # Après la pause, il reprend la même page et termine.
        page = self.inspector.open_control_report(self.satac)
        self.assertIn("Début de saisie", page.html,
                      "le brouillon doit être rechargé tel quel")
        self.inspector.fill_control_report(page, non_compliant_points=0)
        self.assert_saved(page.save(), "reprise après brouillon")
        self.assertTrue(self.refreshed().is_compliant)

    def test_incomplete_save_is_refused_and_names_the_section(self):
        """Le refus doit dire *où* il manque quelque chose."""
        page = self.inspector.open_control_report(self.satac)
        # Tout est rempli sauf les observations de la section 03.
        self.inspector.fill_control_report(page, non_compliant_points=0)
        page.set("observations_generales", "")

        response = page.save()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pas été enregistré")
        # Le bandeau doit nommer la section fautive : « 03 — Mesures à
        # prendre ». Le nom seul ne suffit pas comme preuve, il figure aussi
        # dans les onglets.
        self.assertContains(response, "03 — Mesures à prendre")


class ComplianceCorrectedScenario(ScenarioTestCase):
    """⑥ Conforme mais pas clos : une correction rouvre le cycle."""

    satac = 990005

    def test_a_report_stays_editable_until_the_email_goes_out(self):
        deadline = TODAY + timedelta(days=20)
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(
            page, non_compliant_points=1, measures=1, deadline=deadline)
        self.assert_saved(page.save(), "contrôle initial")
        report = self.control_report()
        self.inspector.send_email("controle", report.pk)

        # Suivi conclu conforme, courriel pas encore envoyé.
        page = self.inspector.open_followup(self.satac)
        self.inspector.fill_followup(page, statuses=[FollowUpStatus.CLOSED])
        self.assert_saved(page.save(), "suivi conforme")
        followup = self.followups()[-1]
        self.assertTrue(self.refreshed().is_compliant)
        self.assertFalse(self.refreshed().is_closed)
        self.assertFalse(followup.is_locked)

        # L'inspecteur s'est trompé : il rouvre la mesure sur le même rapport.
        page = self.inspector.open_followup(self.satac)
        self.assertEqual(len(self.followups()), 1,
                         "aucun nouveau suivi ne doit être créé tant que le "
                         "dossier est conforme")
        self.inspector.fill_followup(
            page,
            statuses=[FollowUpStatus.OPEN],
            next_control_date=TODAY + timedelta(days=30),
        )
        self.assert_saved(page.save(), "correction du constat")

        self.assertFalse(self.refreshed().is_compliant,
                         "corriger la mesure doit rouvrir le cycle")
        self.assertEqual(self.followups()[-1].global_appreciation,
                         Appreciation.JAUNE)


class EmailLifecycleScenario(ScenarioTestCase):
    """⑦ Le courriel : brouillon réécrit en place, envoi verrouillant."""

    satac = 990006

    def test_sending_locks_the_report_and_records_the_email(self):
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=0)
        self.assert_saved(page.save(), "contrôle initial")
        report = self.control_report()

        self.inspector.send_email("controle", report.pk)
        report.refresh_from_db()

        record = report.email_records.order_by("-pk").first()
        self.assertIsNotNone(record, "l'envoi doit laisser une trace")
        self.assertEqual(record.status, EmailStatus.SENT)
        self.assertTrue(report.is_locked)

        # Un rapport verrouillé n'est plus modifiable par l'application :
        # les champs restent rendus mais dans un fieldset désactivé, et le
        # bouton d'enregistrement disparaît.
        page = self.inspector.open_control_report(self.satac)
        self.assertIn("<fieldset disabled>", page.html)
        self.assertNotIn("Enregistrer le rapport", page.html)


class CompletenessWarningScenario(ScenarioTestCase):
    """Le cas décrit par le métier : sections 01, 02, 04 remplies, 03 non.

    L'inspecteur enregistre depuis un onglet complet et ne peut pas voir
    que quelque chose manque ailleurs. L'avertissement doit nommer la
    section fautive quel que soit l'onglet d'où l'on enregistre.
    """

    satac = 990007

    def test_missing_section_is_named_even_when_saving_from_another_tab(self):
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=1,
                                           measures=0)
        # Section 03 laissée incomplète : pas de mesure alors que le chantier
        # n'est pas conforme, et la procédure de contrôle vide.
        page.set("procedure_controle", "")

        response = page.save()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pas été enregistré")
        self.assertContains(response, "03 — Mesures à prendre")
        # Et le brouillon reste proposé comme échappatoire.
        self.assertContains(response, "Enregistrer le brouillon")

    def test_the_guard_is_wired_into_both_report_forms(self):
        """Le garde-fou côté navigateur doit être branché, pas seulement écrit."""
        page = self.inspector.open_control_report(self.satac)
        self.assertIn("data-completeness-guard", page.html)
        self.assertIn("report_completeness.js", page.html)
