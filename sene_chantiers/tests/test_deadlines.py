"""Échéances : seuils, sources multiples et digest hebdomadaire."""

from datetime import timedelta

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from ..models import FollowUpStatus, MeasureFollowUp, MeasureStatus
from ..services import deadlines
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


class DeadlineUrgencyTest(TestCase):
    def test_thresholds(self):
        cases = [
            (-5, deadlines.OVERDUE),
            (-1, deadlines.OVERDUE),
            (0, deadlines.DUE_SOON),
            (2, deadlines.DUE_SOON),
            (3, deadlines.OK),
            (30, deadlines.OK),
        ]
        for offset, expected in cases:
            with self.subTest(offset=offset):
                self.assertEqual(
                    deadlines.urgency(TODAY + timedelta(days=offset), TODAY),
                    expected,
                )

    def test_missing_deadline_is_not_urgent(self):
        self.assertEqual(deadlines.urgency(None, TODAY), deadlines.OK)


class DeadlineListTest(TestCase):
    """La base de test est un clone de la base de développement : les
    assertions portent sur le dossier créé ici, pas sur des totaux."""

    def _rows_for_this_dossier(self):
        return [
            row
            for row in deadlines.banner_counts(TODAY)["rows"]
            if row["chantier"].satac_number == self.chantier.satac_number
        ]

    def setUp(self):
        self.chantier = make_chantier(satac_number=999900)
        self.user = make_user("echeances")
        self.report = make_control_report(chantier=self.chantier, user=self.user)
        self.measure = make_measure(
            self.report, deadline=TODAY - timedelta(days=3)
        )

    def test_overdue_initial_measure_is_listed(self):
        rows = self._rows_for_this_dossier()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["urgency"], deadlines.OVERDUE)
        self.assertEqual(rows[0]["origin"], "Contrôle initial")

    def test_closed_measure_drops_out(self):
        self.measure.status = MeasureStatus.CLOSED
        self.measure.save()
        self.assertEqual(self._rows_for_this_dossier(), [])

    def test_distant_deadline_is_not_listed(self):
        self.measure.deadline = TODAY + timedelta(days=30)
        self.measure.save()
        self.assertEqual(self._rows_for_this_dossier(), [])

    def test_a_rechecked_measure_is_counted_once(self):
        """Elle est suivie sur le contrôle de suivi, plus sur l'initial."""
        followup = make_followup(self.chantier, user=self.user)
        MeasureFollowUp.objects.create(
            corrective_measure_report=followup,
            original_measure=self.measure,
            findings="Toujours pas conforme",
            status=FollowUpStatus.NOT_DONE,
            new_deadline=TODAY - timedelta(days=1),
        )
        rows = self._rows_for_this_dossier()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["origin"], "Suivi des mesures correctives")


class DeadlineDigestTest(TestCase):
    def setUp(self):
        self.user = make_user("digest")
        self.chantier = make_chantier(satac_number=999910)
        self.report = make_control_report(chantier=self.chantier, user=self.user)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_digest_lists_both_urgencies(self):
        make_measure(self.report, order=1, deadline=TODAY - timedelta(days=2))
        make_measure(
            self.report,
            order=2,
            deadline=TODAY + timedelta(days=1),
            description="Bâcher les camions",
        )
        mail.outbox = []
        deadlines.send_digest(TODAY)
        mine = [m for m in mail.outbox if m.to == [self.user.email]]
        self.assertEqual(len(mine), 1)
        message = mine[0]
        self.assertIn("ÉCHÉANCE DÉPASSÉE", message.body)
        self.assertIn("ÉCHÉANCE PROCHE", message.body)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_quiet_week_sends_nothing(self):
        make_measure(self.report, deadline=TODAY + timedelta(days=60))
        mail.outbox = []
        deadlines.send_digest(TODAY)
        self.assertEqual([m for m in mail.outbox if m.to == [self.user.email]], [])

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_dry_run_sends_nothing(self):
        make_measure(self.report, deadline=TODAY - timedelta(days=1))
        mail.outbox = []
        sent = deadlines.send_digest(TODAY, dry_run=True)
        self.assertGreaterEqual(sent, 1)  # au moins le nôtre
        self.assertEqual(len(mail.outbox), 0)


class DeadlineViewTest(MemberClientMixin, TestCase):
    def test_page_lists_the_whole_service(self):
        """La couverture des absences est la raison d'être de cette liste."""
        other_inspector = make_user("collegue")
        chantier = make_chantier(satac_number=999920)
        report = make_control_report(chantier=chantier, user=other_inspector)
        make_measure(report, deadline=TODAY - timedelta(days=1))

        response = self.client.get(reverse("sene_chantiers:deadlines"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "999920")
        self.assertContains(response, "collegue")
