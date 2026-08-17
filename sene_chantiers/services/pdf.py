"""PDF rendering through the SITN WeasyPrint microservice.

The service takes fully-rendered HTML and returns the PDF; there is no
in-process weasyprint import. sene_chantiers is its first consumer in
this monorepo, so the client lives here.

The report PDF carries no photographs. Photos travel with the
notification email as their own attachments, alongside the PDF, and stay
in /data for consultation. Nothing image-related is therefore sent to the
service, which keeps the POST body small and needs no filesystem or
network access back to the application.
"""

import base64
import functools
import logging
from pathlib import Path

import requests
from django.conf import settings
from django.template.loader import render_to_string

from ..labels import appreciation_scale
from ..models import Conformity

logger = logging.getLogger(__name__)

TIMEOUT = 60

LOGO_PATH = Path(settings.BASE_DIR) / "static" / "images" / "logo_ne.png"


# --- Temporary: prototype watermark ---------------------------------------
# Marks these PDFs as not coming from the productive version, like the
# ribbon on the web pages. Delete this function, its context entries and
# the @page rule in pdf/_base.html once the app goes into real service.
#
# Drawn as an SVG page background rather than a rotated element in the
# flow: a `position: fixed` div wide enough to carry the word sticks out
# of the page box once rotated, and WeasyPrint crops it, so the word came
# out cut at both corners. A background covers the page box exactly.
_WATERMARK_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 210 297'>"
    "<text x='105' y='150' fill='#e7ebf0' text-anchor='middle'"
    " font-family='Helvetica, Arial, sans-serif' font-size='26'"
    " font-weight='bold' letter-spacing='2'"
    " transform='rotate(-45 105 150)'>PROTOTYPE</text></svg>"
)


@functools.lru_cache(maxsize=1)
def watermark_data_uri():
    encoded = base64.b64encode(_WATERMARK_SVG.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


@functools.lru_cache(maxsize=1)
def logo_data_uri():
    """The cantonal logo, inlined.

    The service resolves no URLs, so a `{% static %}` path would silently
    render as a missing image. Cached because the file never changes
    within a process.
    """
    try:
        encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    except OSError:
        logger.warning("PDF logo missing at %s", LOGO_PATH)
        return ""
    return f"data:image/png;base64,{encoded}"


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
            # Section 04 repeats the per-theme pill alongside the detail.
            "assessment": assessment,
        })
    return {
        "report": report,
        "chantier": report.chantier,
        "theme_rows": theme_rows,
        "detail_blocks": detail_blocks,
        "report_date": report.control_date,
        "appreciation_scale": appreciation_scale("control"),
        "logo_data_uri": logo_data_uri(),
        "watermark_data_uri": watermark_data_uri(),
    }


def control_report_pdf(report):
    html = render_html(
        "sene_chantiers/pdf/control_report.html",
        _control_report_context(report),
    )
    return html_to_pdf(html)


def corrective_measure_report_pdf(report):
    from ..views import followup_observations

    scale = appreciation_scale("followup")
    conclusion = next(
        (l["description"] for l in scale
         if l["value"] == report.global_appreciation),
        "",
    )
    html = render_html(
        "sene_chantiers/pdf/corrective_measure_report.html",
        {
            "report": report,
            "chantier": report.chantier,
            "first_control_date": report.chantier.control_report.control_date,
            "observations": followup_observations(report),
            "report_date": report.follow_up_date,
            "appreciation_scale": scale,
            "conclusion_text": conclusion,
            "logo_data_uri": logo_data_uri(),
            "watermark_data_uri": watermark_data_uri(),
        },
    )
    return html_to_pdf(html)


def report_pdf(report):
    """Dispatch on the report type."""
    from ..models import ControlReport

    if isinstance(report, ControlReport):
        return control_report_pdf(report)
    return corrective_measure_report_pdf(report)
