"""PDF rendering through the SITN WeasyPrint microservice.

The service takes fully-rendered HTML and returns the PDF; there is no
in-process weasyprint import. sene_chantiers is its first consumer in
this monorepo, so the client lives here.
"""

import base64
import logging

import requests
from django.conf import settings
from django.template.loader import render_to_string

from ..models import Conformity

logger = logging.getLogger(__name__)

TIMEOUT = 60


class PdfServiceError(RuntimeError):
    """The service was unreachable or refused the document."""


def _endpoint(path):
    return f"{settings.SENE_CHANTIERS_WEASYPRINT_URL.rstrip('/')}{path}"


def service_available():
    """Cheap health probe, so a view can degrade with a clear message."""
    try:
        response = requests.get(_endpoint("/health"), timeout=5)
        return response.ok
    except requests.RequestException:
        return False


def render_html(template_name, context):
    return render_to_string(template_name, context)


def html_to_pdf(html):
    """POST the rendered HTML and return the PDF bytes."""
    try:
        response = requests.post(
            _endpoint("/pdf"),
            data=html.encode("utf-8"),
            headers={"Content-Type": "text/html; charset=utf-8"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("WeasyPrint service failed: %s", exc)
        raise PdfServiceError(
            "Le service de génération PDF est indisponible."
        ) from exc

    if not response.content.startswith(b"%PDF"):
        raise PdfServiceError("Le service n'a pas renvoyé un document PDF.")
    return response.content


def _photo_rows(report, per_row=3):
    """Photos grouped into table rows, inlined as data URIs.

    The HTML must be self-contained: the service renders it in its own
    container, and may not even run on this host, so it can reach neither
    our URLs nor our filesystem. Embedding the bytes is what makes the
    document portable to any WeasyPrint instance.
    """
    photos = []
    for photo in report.photos.all():
        if not photo.image:
            continue
        try:
            photo.image.open("rb")
            payload = photo.image.read()
            photo.image.close()
        except OSError:
            logger.warning("Photo %s unreadable, skipped in the PDF", photo.pk)
            continue
        mime = "image/png" if photo.image.name.lower().endswith(".png")             else "image/jpeg"
        photo.data_uri = (
            f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"
        )
        photos.append(photo)
    return [photos[i:i + per_row] for i in range(0, len(photos), per_row)]


def _control_report_context(report):
    """Section 02 and 04 need the checklist grouped and counted."""
    answers = list(
        report.control_point_answers.select_related("control_point__theme")
    )
    by_theme = {}
    for answer in answers:
        by_theme.setdefault(answer.control_point.theme_id, []).append(answer)

    theme_rows, detail_blocks = [], []
    for assessment in report.theme_assessments.select_related("theme"):
        theme_answers = by_theme.get(assessment.theme_id, [])
        # "x / y": assessed points over the theme's total, N.A. excluded.
        checked = sum(
            1 for a in theme_answers
            if a.conformity and a.conformity != Conformity.NOT_APPLICABLE
        )
        theme_rows.append({
            "assessment": assessment,
            "checked": checked,
            "total": len(theme_answers),
        })
        detail_blocks.append({
            "theme": assessment.theme,
            "answers": theme_answers,
            "observations": assessment.detail_observations,
        })
    return {
        "report": report,
        "chantier": report.chantier,
        "theme_rows": theme_rows,
        "detail_blocks": detail_blocks,
        "photo_rows": _photo_rows(report),
    }


def control_report_pdf(report):
    html = render_html(
        "sene_chantiers/pdf/control_report.html",
        _control_report_context(report),
    )
    return html_to_pdf(html)


def corrective_measure_report_pdf(report):
    from ..views import followup_observations

    html = render_html(
        "sene_chantiers/pdf/corrective_measure_report.html",
        {
            "report": report,
            "chantier": report.chantier,
            "first_control_date": report.chantier.control_report.control_date,
            "observations": followup_observations(report),
            "photo_rows": _photo_rows(report),
        },
    )
    return html_to_pdf(html)


def report_pdf(report):
    """Dispatch on the report type."""
    from ..models import ControlReport

    if isinstance(report, ControlReport):
        return control_report_pdf(report)
    return corrective_measure_report_pdf(report)
