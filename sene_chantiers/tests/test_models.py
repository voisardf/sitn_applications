"""Modèles : propriétés dérivées, validations et contraintes de base."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from ..models import (
    Appreciation,
    EmailRecord,
    EmailTemplate,
    FollowUpStatus,
    MeasureFollowUp,
    Photo,
)
from .factories import (
    TODAY,
    make_chantier,
    make_control_report,
    make_followup,
    make_measure,
)


class ChantierModelTest(TestCase):
    def test_str(self):
        chantier = make_chantier()
        self.assertIn(str(chantier.satac_number), str(chantier))
        self.assertIn(chantier.site_name, str(chantier))

    def test_satac_number_is_unique(self):
        make_chantier(satac_number=999010)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_chantier(satac_number=999010)


class ReportModelTest(TestCase):
    def test_closes_the_case_only_when_vert(self):
        report = make_control_report()
        self.assertTrue(report.closes_the_case)
        report.global_appreciation = Appreciation.ROUGE
        self.assertFalse(report.closes_the_case)

    def test_future_control_date_is_refused(self):
        report = make_control_report()
        report.control_date = TODAY + timedelta(days=1)
        with self.assertRaises(ValidationError) as ctx:
            report.full_clean()
        self.assertIn("control_date", ctx.exception.message_dict)

    def test_next_control_date_required_when_not_conforme(self):
        report = make_control_report(global_appreciation=Appreciation.ROUGE)
        with self.assertRaises(ValidationError) as ctx:
            report.full_clean()
        self.assertIn("next_control_date", ctx.exception.message_dict)

    def test_next_control_date_optional_when_conforme(self):
        report = make_control_report()
        report.full_clean()  # ne lève pas

    def test_future_follow_up_date_is_refused(self):
        chantier = make_chantier(satac_number=999011)
        make_control_report(chantier=chantier)
        followup = make_followup(chantier)
        followup.follow_up_date = TODAY + timedelta(days=1)
        with self.assertRaises(ValidationError) as ctx:
            followup.full_clean()
        self.assertIn("follow_up_date", ctx.exception.message_dict)


class MeasureFollowUpModelTest(TestCase):
    def setUp(self):
        self.chantier = make_chantier(satac_number=999020)
        self.report = make_control_report(chantier=self.chantier)
        self.measure = make_measure(self.report)
        self.followup = make_followup(self.chantier)

    def _followup_row(self, status, new_deadline=None):
        return MeasureFollowUp(
            corrective_measure_report=self.followup,
            original_measure=self.measure,
            findings="Constat",
            status=status,
            new_deadline=new_deadline,
        )

    def test_open_measure_requires_a_new_deadline(self):
        row = self._followup_row(FollowUpStatus.OPEN)
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        self.assertIn("new_deadline", ctx.exception.message_dict)

    def test_closed_measure_needs_no_deadline(self):
        self._followup_row(FollowUpStatus.CLOSED).full_clean()

    def test_same_measure_cannot_be_tracked_twice_on_one_report(self):
        self._followup_row(FollowUpStatus.CLOSED).save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._followup_row(FollowUpStatus.CLOSED).save()


class PhotoModelTest(TestCase):
    def setUp(self):
        self.chantier = make_chantier(satac_number=999030)
        self.report = make_control_report(chantier=self.chantier)

    def test_photo_must_belong_to_exactly_one_report(self):
        followup = make_followup(self.chantier)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Photo.objects.create(
                    control_report=self.report, corrective_measure_report=followup
                )

    def test_photo_needs_a_report(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Photo.objects.create()

    def test_report_and_satac_are_derived(self):
        photo = Photo.objects.create(control_report=self.report)
        self.assertEqual(photo.report, self.report)
        self.assertEqual(photo.satac_number, self.chantier.satac_number)


class EmailRecordModelTest(TestCase):
    def setUp(self):
        self.chantier = make_chantier(satac_number=999040)
        self.report = make_control_report(chantier=self.chantier)

    def _record(self, **kwargs):
        defaults = {
            "chantier": self.chantier,
            "template_used": EmailTemplate.CONFORME,
            "recipient_email": "destinataire@example.ch",
            "subject": "Objet",
            "body": "Corps",
        }
        defaults.update(kwargs)
        return EmailRecord(**defaults)

    def test_email_must_belong_to_exactly_one_report(self):
        followup = make_followup(self.chantier)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._record(
                    control_report=self.report, corrective_measure_report=followup
                ).save()

    def test_display_date_is_creation_then_sending(self):
        record = self._record(control_report=self.report)
        record.save()
        self.assertEqual(record.display_date, record.created_at)
        record.sent_at = timezone.now()
        record.save()
        self.assertEqual(record.display_date, record.sent_at)


# ---------------------------------------------------------------------------
# Recherche SATAC
# ---------------------------------------------------------------------------
