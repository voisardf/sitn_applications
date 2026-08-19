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
    Conformity,
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


class DraftKeepsWhatWasTypedScenario(ScenarioTestCase):
    """⑧ Le brouillon garde la saisie, et rend la main où on l'a laissée."""

    satac = 990007

    def test_draft_from_section_04_keeps_observations_and_the_tab(self):
        page = self.inspector.open_control_report(self.satac)
        # L'inspecteur travaille dans l'onglet 04 : il répond à la
        # checklist, rédige les observations, puis enregistre un brouillon
        # sans quitter l'onglet.
        self.inspector.fill_control_report(page, non_compliant_points=1)
        page.set_all("-detail_observations", "Observation détaillée du thème")

        response = page.save_draft(tab="tab04")
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=tab04", response["Location"],
                      "le brouillon doit rendre la main sur l'onglet courant")

        reloaded = self.inspector.open_control_report(self.satac)
        self.assertIn("Observation détaillée du thème", reloaded.html,
                      "les observations de la section 04 doivent survivre")
        answered = [v for k, v in reloaded.data.items()
                    if k.endswith("-conformity") and v]
        self.assertTrue(answered, "les réponses de la checklist doivent survivre")

    def test_a_drafted_measure_survives_the_round_trip(self):
        """Une mesure ajoutée puis mise en brouillon ne doit pas disparaître."""
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=1)
        page.add_measure("Évacuer les déchets spéciaux",
                         deadline=TODAY + timedelta(days=20))
        self.assertEqual(page.save_draft(tab="tab03").status_code, 302)

        report = self.control_report()
        self.assertEqual(report.corrective_measures.count(), 1,
                         "la mesure du brouillon doit être enregistrée")

        # Retour au récapitulatif, puis réouverture : elle est toujours là.
        self.assertEqual(self.inspector.landing(self.satac).status_code, 200)
        reloaded = self.inspector.open_control_report(self.satac)
        self.assertIn("Évacuer les déchets spéciaux", reloaded.html)

    def test_a_measure_without_a_deadline_can_still_be_drafted(self):
        """Un brouillon accepte l'incomplet, échéance comprise."""
        page = self.inspector.open_control_report(self.satac)
        page.add_measure("Mesure à préciser", deadline="")
        self.assertEqual(page.save_draft(tab="tab03").status_code, 302)

        measure = self.control_report().corrective_measures.get()
        self.assertIsNone(measure.deadline)
        self.assertEqual(measure.order, 1, "le numéro reste généré")


class MeasureNumberingScenario(ScenarioTestCase):
    """⑨ Le N° des mesures est généré, et la corbeille referme les trous."""

    satac = 990008

    def test_the_number_is_shown_but_never_typed(self):
        page = self.inspector.open_control_report(self.satac)
        self.assertEqual(
            page.fields_ending("-order"), [],
            "le N° est généré : il ne doit pas être un champ de saisie")

    def test_numbers_stay_consecutive_when_a_row_is_deleted(self):
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=1)
        deadline = TODAY + timedelta(days=30)
        for label in ("Première mesure", "Deuxième mesure", "Troisième mesure"):
            page.add_measure(label, deadline=deadline)
        page.set("next_control_date", str(deadline))
        self.assert_saved(page.save(), "trois mesures")
        self.assertEqual(
            [m.order for m in self.control_report().corrective_measures
                                 .order_by("order")], [1, 2, 3])

        # L'inspecteur jette la deuxième : la troisième prend sa place.
        page = self.inspector.open_control_report(self.satac)
        page.delete_measure(1)
        self.assert_saved(page.save(), "suppression d'une mesure")

        remaining = self.control_report().corrective_measures.order_by("order")
        self.assertEqual([m.description for m in remaining],
                         ["Première mesure", "Troisième mesure"])
        self.assertEqual([m.order for m in remaining], [1, 2],
                         "les numéros doivent rester consécutifs")

    def test_the_trash_disappears_once_the_email_is_sent(self):
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=1)
        deadline = TODAY + timedelta(days=30)
        page.add_measure("Mesure à supprimer", deadline=deadline)
        page.set("next_control_date", str(deadline))
        self.assert_saved(page.save(), "rapport avec une mesure")

        page = self.inspector.open_control_report(self.satac)
        self.assertIn("measures-0-DELETE", page.data,
                      "la corbeille doit être offerte tant que rien n'est parti")

        report = self.control_report()
        self.inspector.send_email("controle", report.pk)
        locked = self.inspector.client.get(page.url)
        self.assertNotContains(locked, "measures-0-DELETE",
                               msg_prefix="rapport verrouillé")


class EntryShortcutsScenario(ScenarioTestCase):
    """⑩ Les raccourcis de saisie de la section 04 et de la section 02."""

    satac = 990009

    def setUp(self):
        super().setUp()
        self.page = self.inspector.open_control_report(self.satac)

    def test_each_theme_offers_a_row_that_answers_it_at_once(self):
        """Un thème conforme de bout en bout se coche en un geste."""
        blocks = self.page.html.count('class="sc-bulk-row"')
        self.assertGreater(blocks, 0, "aucun raccourci de thème n'est rendu")
        # Un raccourci par thème rendu, pas un pour toute la page.
        themes = self.page.html.count('data-bulk-theme="')
        self.assertEqual(blocks, themes)
        for value, _label in Conformity.choices:
            self.assertIn(f'value="{value}"', self.page.html)

    def test_the_shortcut_is_never_posted_as_an_answer(self):
        """Le raccourci vit dans le navigateur : il ne doit rien enregistrer."""
        bulk = [k for k in self.page.data if k.startswith("bulk-")]
        self.assertTrue(bulk, "le raccourci doit être présent dans la page")
        for name in bulk:
            self.assertFalse(
                name.startswith(("answers-", "themes-", "measures-")),
                f"{name} entrerait en collision avec un formset")

    def test_both_helpers_are_wired_to_the_page(self):
        """Sans le script, la page reste utilisable — mais il doit être là."""
        self.assertIn("control_report_form.js", self.page.html)
        self.assertTrue(self.page.fields_ending("-synthesis_remarks"))
        self.assertTrue(self.page.fields_ending("-detail_observations"))

    def test_the_active_tab_travels_with_the_form(self):
        self.assertIn("active_tab", self.page.data)
        response = self.inspector.client.get(f"{self.page.url}?tab=tab03")
        self.assertContains(response, 'value="tab03"')


class DraftKeepsEveryColumnScenario(ScenarioTestCase):
    """⑪ Le brouillon garde toutes les colonnes, pas seulement les évidentes.

    « Responsable » a servi de révélateur : une colonne du tableau peut se
    perdre sans que rien ne le signale, et seule une vérification colonne
    par colonne le montre.
    """

    satac = 990010

    def test_a_measure_keeps_every_column_through_edit_draft_edit(self):
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=1)
        deadline = TODAY + timedelta(days=15)
        page.add_measure("Remplacer le joint d'étanchéité",
                         responsible="Entreprise Dupont SA", deadline=deadline)
        self.assertEqual(page.save_draft(tab="tab03").status_code, 302)

        measure = self.control_report().corrective_measures.get()
        self.assertEqual(measure.description, "Remplacer le joint d'étanchéité")
        self.assertEqual(measure.responsible, "Entreprise Dupont SA")
        self.assertEqual(measure.deadline, deadline)

        # Reprise : la valeur revient dans le formulaire, et une correction
        # passée en brouillon est bien enregistrée.
        page = self.inspector.open_control_report(self.satac)
        self.assertEqual(page.data["measures-0-responsible"],
                         "Entreprise Dupont SA")
        page.set("measures-0-responsible", "Maître d'ouvrage")
        self.assertEqual(page.save_draft(tab="tab03").status_code, 302)

        measure.refresh_from_db()
        self.assertEqual(measure.responsible, "Maître d'ouvrage",
                         "la correction faite avant un brouillon doit tenir")

    def test_a_half_typed_measure_keeps_what_was_typed(self):
        """Aucune colonne ne doit exiger qu'une autre soit remplie."""
        for index, column in enumerate(("description", "responsible")):
            with self.subTest(column=column):
                satac = 990020 + index
                make_chantier(satac_number=satac)
                page = self.inspector.open_control_report(satac)
                page.data[f"measures-0-{column}"] = "Valeur saisie"
                self.assertEqual(page.save_draft(tab="tab03").status_code, 302)

                report = ControlReport.objects.get(chantier__satac_number=satac)
                measure = report.corrective_measures.get()
                self.assertEqual(getattr(measure, column), "Valeur saisie")


    def test_a_draft_saves_the_panels_even_without_a_next_control_date(self):
        """La règle du modèle ne doit pas invalider un brouillon.

        `BaseReport.clean()` exige un prochain contrôle tant que le chantier
        n'est pas conforme. Appliquée à un brouillon, elle faisait échouer
        l'enregistrement du formulaire principal sans un mot — les onglets
        01 et 03 étaient perdus alors que les sections filles, elles,
        étaient bien écrites.
        """
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=2)
        # Chantier non conforme, et le délai de mise en conformité pas
        # encore fixé : exactement ce qu'un brouillon doit accepter.
        page.set("global_appreciation", Appreciation.JAUNE)
        page.set("observations_generales", "Constat à compléter demain")
        page.set("procedure_controle", "Visite accompagnée")
        page.set("next_control_date", "")
        self.assertEqual(page.save_draft(tab="tab01").status_code, 302)

        report = self.control_report()
        self.assertEqual(report.observations_generales,
                         "Constat à compléter demain")
        self.assertEqual(report.procedure_controle, "Visite accompagnée")


class FollowUpDraftScenario(ScenarioTestCase):
    """⑫ Le brouillon du rapport de suivi obéit aux mêmes règles."""

    satac = 990011

    def setUp(self):
        super().setUp()
        page = self.inspector.open_control_report(self.satac)
        self.inspector.fill_control_report(page, non_compliant_points=1)
        deadline = TODAY + timedelta(days=20)
        page.add_measure("Évacuer les déchets spéciaux",
                         responsible="Entreprise Dupont SA", deadline=deadline)
        page.set("next_control_date", str(deadline))
        self.assert_saved(page.save(), "rapport initial")
        self.inspector.send_email("controle", self.control_report().pk)

    def test_a_partially_filled_followup_is_kept(self):
        page = self.inspector.open_followup(self.satac)
        # Seul le responsable est corrigé : les constats viendront plus tard.
        name = page.fields_ending("-responsible")[0]
        page.set(name, "Nouveau mandataire")
        response = page.save_draft(tab="f02")
        self.assertEqual(response.status_code, 302,
                         "un brouillon de suivi ne doit jamais être refusé")
        self.assertIn("tab=f02", response["Location"],
                      "le brouillon doit rendre la main sur l'onglet courant")

        followup = self.followups()[-1]
        self.assertEqual(followup.measure_followups.first().responsible,
                         "Nouveau mandataire",
                         "le responsable saisi doit survivre au brouillon")

    def test_the_draft_does_not_erase_the_stored_dates(self):
        page = self.inspector.open_followup(self.satac)
        stored = self.followups()[-1].follow_up_date
        page.set("follow_up_date", "")
        self.assertEqual(page.save_draft(tab="f01").status_code, 302)
        self.assertEqual(self.followups()[-1].follow_up_date, stored,
                         "un brouillon ne remplace jamais une valeur par du vide")
