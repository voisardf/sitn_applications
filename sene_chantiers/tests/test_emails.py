"""Courriels : sélection des modèles, brouillon et envoi."""

from datetime import timedelta

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import (
    Appreciation,
    EmailRecord,
    EmailStatus,
    EmailTemplate,
)
from ..services import emails
from .factories import (
    TODAY,
    make_chantier,
    make_control_report,
    make_followup,
    make_measure,
    make_user,
    seed_sections,
)


class MemberClientMixin:
    def setUp(self):
        super().setUp()
        self.user = make_user("membre")
        self.client = Client()
        self.client.force_login(self.user)


class EmailTemplateSelectionTest(TestCase):
    def setUp(self):
        self.chantier = make_chantier(satac_number=999600)
        self.report = make_control_report(chantier=self.chantier)

    def test_conforme_initial_report_uses_template_1(self):
        self.assertEqual(
            emails.select_template(self.report), EmailTemplate.CONFORME
        )

    def test_non_conforme_initial_report_uses_template_2(self):
        self.report.global_appreciation = Appreciation.ROUGE
        self.assertEqual(
            emails.select_template(self.report), EmailTemplate.NON_CONFORMITES
        )

    def test_conforme_followup_uses_template_3(self):
        followup = make_followup(self.chantier)
        self.assertEqual(emails.select_template(followup), EmailTemplate.LEVEE)

    def test_non_conforme_followup_reissues_template_2(self):
        followup = make_followup(
            self.chantier, global_appreciation=Appreciation.ROUGE
        )
        self.assertEqual(
            emails.select_template(followup), EmailTemplate.NON_CONFORMITES
        )

    def test_template_4_only_on_explicit_escalation(self):
        """Jamais automatique : c'est une décision de l'inspecteur."""
        followup = make_followup(
            self.chantier, global_appreciation=Appreciation.ROUGE
        )
        self.assertNotEqual(
            emails.select_template(followup), EmailTemplate.ULTIME_DELAI
        )
        followup.is_denunciation_escalation = True
        self.assertEqual(
            emails.select_template(followup), EmailTemplate.ULTIME_DELAI
        )

    def test_summary_is_derived_from_the_report(self):
        self.report.global_appreciation = Appreciation.ROUGE
        self.report.save()
        seed_sections(self.report)
        assessment = self.report.theme_assessments.first()
        assessment.appreciation = Appreciation.ROUGE
        assessment.synthesis_remarks = "Bennes non couvertes"
        assessment.save()
        make_measure(self.report, description="Bâcher les bennes")

        summary = emails.non_conformity_summary(self.report)

        self.assertIn("Bennes non couvertes", summary)
        self.assertIn("Bâcher les bennes", summary)

    def test_template_4_quotes_the_last_sent_notice(self):
        sent_on = timezone.now() - timedelta(days=20)
        EmailRecord.objects.create(
            chantier=self.chantier,
            control_report=self.report,
            template_used=EmailTemplate.NON_CONFORMITES,
            recipient_email="destinataire@example.ch",
            subject="Objet",
            body="Corps",
            status=EmailStatus.SENT,
            sent_at=sent_on,
        )
        followup = make_followup(
            self.chantier,
            global_appreciation=Appreciation.ROUGE,
            is_denunciation_escalation=True,
            next_control_date=TODAY + timedelta(days=10),
        )
        _subject, body = emails.render(followup)
        self.assertIn(sent_on.strftime("%d.%m.%Y"), body)


class EmailManagerViewTest(MemberClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999610)
        self.report = make_control_report(chantier=self.chantier)
        self.url = reverse(
            "sene_chantiers:email_manager", args=["controle", self.report.pk]
        )

    def test_opening_prepares_a_draft(self):
        self.client.get(self.url)
        record = self.report.email_records.get()
        self.assertEqual(record.status, EmailStatus.DRAFT)
        self.assertEqual(
            record.recipient_email, self.chantier.maitre_ouvrage_email
        )
        self.assertIn(str(self.chantier.satac_number), record.body)

    def test_draft_is_overwritten_in_place(self):
        self.client.get(self.url)
        for subject in ("Premier", "Second"):
            self.client.post(
                self.url,
                {
                    "satac_number": str(self.chantier.satac_number),
                    "action": "save",
                    "recipient_email": "destinataire@example.ch",
                    "subject": subject,
                    "body": "Corps",
                },
            )
        self.assertEqual(self.report.email_records.count(), 1)
        self.assertEqual(self.report.email_records.get().subject, "Second")


class EmailSendTest(MemberClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999620)
        self.report = make_control_report(chantier=self.chantier)
        self.url = reverse(
            "sene_chantiers:email_manager", args=["controle", self.report.pk]
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_sending_locks_the_report(self):
        self.client.get(self.url)
        mail.outbox = []
        self.client.post(
            self.url,
            {
                "satac_number": str(self.chantier.satac_number),
                "action": "send",
                "recipient_email": "destinataire@example.ch",
                "subject": "Objet",
                "body": "Corps",
            },
        )
        self.assertEqual(len(mail.outbox), 1)
        record = self.report.email_records.get()
        self.assertEqual(record.status, EmailStatus.SENT)
        self.assertIsNotNone(record.sent_at)
        self.report.refresh_from_db()
        self.assertTrue(self.report.is_locked)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_a_sent_record_cannot_be_edited(self):
        self.client.get(self.url)
        self.client.post(
            self.url,
            {
                "satac_number": str(self.chantier.satac_number),
                "action": "send",
                "recipient_email": "destinataire@example.ch",
                "subject": "Objet initial",
                "body": "Corps",
            },
        )
        self.client.post(
            self.url,
            {
                "satac_number": str(self.chantier.satac_number),
                "action": "save",
                "recipient_email": "pirate@example.ch",
                "subject": "Objet modifié",
                "body": "Corps",
            },
        )
        self.assertEqual(self.report.email_records.get().subject, "Objet initial")


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
