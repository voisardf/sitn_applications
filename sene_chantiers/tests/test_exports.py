"""Exports PDF et Excel."""

import io
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import (
    EmailRecord,
    EmailStatus,
    EmailTemplate,
    Photo,
    PhotoStatus,
)
from ..services import excel, pdf
from .factories import (
    jpeg_bytes,
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


class PdfExportTest(MemberClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999700)
        self.report = make_control_report(chantier=self.chantier)
        seed_sections(self.report)
        make_measure(self.report)

    def test_html_carries_no_photograph(self):
        """Les photos vont au courriel, jamais dans le rapport."""
        photo = Photo(control_report=self.report, status=PhotoStatus.DONE)
        photo.image.save("p.jpg", ContentFile(jpeg_bytes()), save=True)

        html = pdf.render_html(
            "sene_chantiers/pdf/control_report.html",
            pdf._control_report_context(self.report),
        )
        self.assertNotIn("data:image", html)
        self.assertNotIn("file://", html)
        self.assertIn("Rapport de contrôle environnemental", html)
        self.assertIn("Mesures à prendre", html)

    def test_print_rules_are_present(self):
        html = pdf.render_html(
            "sene_chantiers/pdf/control_report.html",
            pdf._control_report_context(self.report),
        )
        self.assertIn("break-inside: avoid", html)
        self.assertIn("counter(page)", html)

    @patch("sene_chantiers.services.pdf.requests.post")
    def test_service_response_is_returned(self, mock_post):
        mock_post.return_value.content = b"%PDF-1.7 ..."
        mock_post.return_value.raise_for_status = lambda: None
        response = self.client.get(
            reverse(
                "sene_chantiers:pdf_export", args=["controle", self.report.pk]
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    @patch("sene_chantiers.services.pdf.requests.post")
    def test_non_pdf_response_is_rejected(self, mock_post):
        mock_post.return_value.content = b"<html>erreur</html>"
        mock_post.return_value.raise_for_status = lambda: None
        with self.assertRaises(pdf.PdfServiceError):
            pdf.report_pdf(self.report)

    @patch(
        "sene_chantiers.services.pdf.requests.post",
        side_effect=pdf.requests.RequestException("boom"),
    )
    def test_unreachable_service_degrades_gracefully(self, _post):
        response = self.client.get(
            reverse(
                "sene_chantiers:pdf_export", args=["controle", self.report.pk]
            ),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "indisponible")


class ExcelExportTest(MemberClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999800)
        self.report = make_control_report(chantier=self.chantier)
        seed_sections(self.report)
        make_measure(self.report)
        make_followup(self.chantier)

    def test_workbook_structure(self):
        from openpyxl import load_workbook

        content = excel.dossier_workbook(self.chantier)
        workbook = load_workbook(io.BytesIO(content))
        self.assertEqual(
            workbook.sheetnames,
            [
                "Informations générales",
                "Contrôle initial",
                "Suivi 1",
                "Courriels envoyés",
            ],
        )
        general = workbook["Informations générales"]
        # Le n° SATAC reste numérique dans le classeur, pas converti en texte.
        self.assertEqual(general["B1"].value, self.chantier.satac_number)

    def test_view_streams_a_workbook(self):
        response = self.client.get(
            reverse("sene_chantiers:excel_export", args=[999800])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn("dossier_999800.xlsx", response["Content-Disposition"])

    def test_lazy_labels_are_resolved(self):
        """openpyxl refuse les proxies de traduction."""
        from openpyxl import load_workbook

        EmailRecord.objects.create(
            chantier=self.chantier,
            control_report=self.report,
            template_used=EmailTemplate.NON_CONFORMITES,
            recipient_email="destinataire@example.ch",
            subject="Objet",
            body="Corps",
            status=EmailStatus.SENT,
            sent_at=timezone.now(),
        )
        workbook = load_workbook(io.BytesIO(excel.dossier_workbook(self.chantier)))
        sheet = workbook["Courriels envoyés"]
        self.assertEqual(sheet.cell(row=2, column=2).value, "Mesures à prendre")


# ---------------------------------------------------------------------------
# Échéances
# ---------------------------------------------------------------------------
