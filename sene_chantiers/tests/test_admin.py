"""Accès admin aux rapports : réservé aux superutilisateurs, et gelé après
une escalade vers la dénonciation.

L'admin n'est pas le chemin d'édition normal — c'est une issue de secours
pour corriger un rapport que l'application refuse de rouvrir, typiquement
parce que son courriel est parti et l'a verrouillé. Deux garde-fous :
seuls les superutilisateurs y accèdent, et un dossier engagé vers le
Ministère public devient définitivement consultable seulement.
"""

from django.contrib.admin.sites import site
from django.test import RequestFactory, TestCase

from ..models import ControlReport, CorrectiveMeasureReport
from .factories import (
    make_chantier,
    make_control_report,
    make_followup,
    make_user,
)


class ReportAdminPermissionTest(TestCase):
    def setUp(self):
        self.admin = site._registry[ControlReport]
        self.factory = RequestFactory()
        self.chantier = make_chantier(satac_number=999501)
        self.report = make_control_report(chantier=self.chantier)

    def _request(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_non_superuser_group_member_has_no_access(self):
        request = self._request(make_user("inspecteur"))
        self.assertFalse(self.admin.has_module_permission(request))
        self.assertFalse(self.admin.has_view_permission(request, self.report))
        self.assertFalse(self.admin.has_change_permission(request, self.report))

    def test_superuser_may_edit_an_unlocked_report(self):
        request = self._request(
            make_user("root", in_group=False, is_superuser=True, is_staff=True)
        )
        self.assertTrue(self.admin.has_change_permission(request, self.report))

    def test_superuser_may_edit_a_locked_report_without_denunciation(self):
        """Le cas qui justifie l'existence de cette porte."""
        self.report.is_locked = True
        self.report.save()
        request = self._request(
            make_user("root", in_group=False, is_superuser=True, is_staff=True)
        )
        self.assertTrue(self.admin.has_change_permission(request, self.report))

    def test_locked_report_is_frozen_once_denunciation_is_engaged(self):
        self.report.is_locked = True
        self.report.save()
        make_followup(self.chantier, is_denunciation_escalation=True)

        request = self._request(
            make_user("root", in_group=False, is_superuser=True, is_staff=True)
        )
        self.assertFalse(self.admin.has_change_permission(request, self.report))
        # Gelé veut dire consultable, pas invisible.
        self.assertTrue(self.admin.has_view_permission(request, self.report))
        self.assertIn(
            "global_appreciation",
            self.admin.get_readonly_fields(request, self.report),
        )

    def test_escalation_alone_does_not_freeze_an_unlocked_report(self):
        """La dénonciation ne gèle que la levée du verrou.

        Un rapport non verrouillé reste modifiable dans l'application
        elle-même ; le bloquer ici serait incohérent.
        """
        make_followup(self.chantier, is_denunciation_escalation=True)
        request = self._request(
            make_user("root", in_group=False, is_superuser=True, is_staff=True)
        )
        self.assertTrue(self.admin.has_change_permission(request, self.report))

    def test_reports_can_never_be_added_or_deleted_here(self):
        request = self._request(
            make_user("root", in_group=False, is_superuser=True, is_staff=True)
        )
        self.assertFalse(self.admin.has_add_permission(request))
        self.assertFalse(self.admin.has_delete_permission(request, self.report))


class DenunciationTrackTest(TestCase):
    def test_false_when_no_followup_escalated(self):
        chantier = make_chantier(satac_number=999502)
        make_followup(chantier)
        self.assertFalse(chantier.has_entered_denunciation_track)

    def test_true_from_the_escalation_flag(self):
        chantier = make_chantier(satac_number=999503)
        make_followup(chantier, is_denunciation_escalation=True)
        self.assertTrue(chantier.has_entered_denunciation_track)

    def test_true_from_a_recorded_final_closure_state(self):
        chantier = make_chantier(satac_number=999504)
        make_followup(chantier, final_closure_state="authority_enforced")
        self.assertTrue(chantier.has_entered_denunciation_track)

    def test_stays_true_on_later_visits(self):
        """Le gel ne doit pas se lever parce qu'une visite ultérieure est
        redevenue ordinaire."""
        chantier = make_chantier(satac_number=999505)
        inspector = make_user("inspecteur999505")
        make_followup(chantier, user=inspector, is_denunciation_escalation=True)
        make_followup(chantier, user=inspector)
        self.assertTrue(chantier.has_entered_denunciation_track)


class CorrectiveMeasureInlineRuleTest(TestCase):
    """La règle inter-lignes doit accompagner ce second point d'entrée."""

    def test_admin_reimplements_the_at_least_one_measure_rule(self):
        from ..admin import CorrectiveMeasureFormSet

        admin_instance = site._registry[ControlReport]
        inline = next(
            i for i in admin_instance.inlines
            if getattr(i, "formset", None) is CorrectiveMeasureFormSet
        )
        self.assertIsNotNone(inline)


class ReportAdminRenderingTest(TestCase):
    """Les permissions peuvent être justes et la page ne pas s'afficher."""

    def setUp(self):
        self.chantier = make_chantier(satac_number=999506)
        self.report = make_control_report(chantier=self.chantier)
        self.client.force_login(
            make_user("root", in_group=False, is_superuser=True, is_staff=True)
        )

    def test_changelist_renders(self):
        response = self.client.get(
            "/admin/sene_chantiers/controlreport/", follow=True
        )
        self.assertEqual(response.status_code, 200)

    def test_change_form_renders_with_its_inlines(self):
        response = self.client.get(
            f"/admin/sene_chantiers/controlreport/{self.report.pk}/change/",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mesures à prendre")

    def test_frozen_report_renders_without_a_save_button(self):
        self.report.is_locked = True
        self.report.save()
        make_followup(self.chantier, is_denunciation_escalation=True)

        response = self.client.get(
            f"/admin/sene_chantiers/controlreport/{self.report.pk}/change/",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_save"')


class CorrectiveMeasureReportAdminTest(TestCase):
    def test_followup_reports_are_registered_with_the_same_guards(self):
        admin_instance = site._registry[CorrectiveMeasureReport]
        factory = RequestFactory()
        request = factory.get("/admin/")
        request.user = make_user("inspecteur")
        self.assertFalse(admin_instance.has_module_permission(request))
