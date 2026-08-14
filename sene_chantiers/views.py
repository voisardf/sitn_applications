"""Views for sene_chantiers.

Every view is gated on SSO authentication plus membership of the
sene_chantiers_admin group.
"""

from django.contrib import messages
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .auth import sene_chantiers_admin_required
from .forms import ChantierForm
from .labels import (
    appreciation_label,
    email_status_appreciation,
    email_status_label,
)
from .models import Chantier, EmailStatus
from .services import satac

RECENT_DOSSIERS_LIMIT = 5


def _latest_appreciation(chantier):
    """Appreciation of the most recent report, initial or follow-up."""
    latest_followup = chantier.corrective_measure_reports.order_by(
        "-follow_up_date"
    ).first()
    if latest_followup:
        return latest_followup.global_appreciation
    control_report = getattr(chantier, "control_report", None)
    return control_report.global_appreciation if control_report else None


def _decorate(chantier):
    appreciation = _latest_appreciation(chantier)
    chantier.appreciation = appreciation
    chantier.appreciation_label = appreciation_label(appreciation)
    return chantier


def _dossier_reports(chantier):
    """The dossier's reports, initial first then follow-ups by date."""
    rows = []
    control_report = getattr(chantier, "control_report", None)
    if control_report:
        rows.append(
            {
                "kind": "control",
                "pk": control_report.pk,
                "label": "Contrôle environnemental",
                "date": control_report.control_date,
                "appreciation": control_report.global_appreciation,
                "appreciation_label": appreciation_label(
                    control_report.global_appreciation
                ),
                "is_locked": control_report.is_locked,
            }
        )
    for index, followup in enumerate(
        chantier.corrective_measure_reports.order_by("follow_up_date"), start=1
    ):
        rows.append(
            {
                "kind": "followup",
                "pk": followup.pk,
                "label": f"Suivi des mesures correctives {index}",
                "date": followup.follow_up_date,
                "appreciation": followup.global_appreciation,
                "appreciation_label": appreciation_label(
                    followup.global_appreciation
                ),
                "is_locked": followup.is_locked,
            }
        )
    return rows


def _dossier_emails(chantier):
    rows = []
    for record in chantier.email_records.all():
        rows.append(
            {
                "pk": record.pk,
                "date": record.display_date,
                "status_label": email_status_label(record.template_used),
                "appreciation": email_status_appreciation(record.template_used),
                "subject": record.subject,
                "is_sent": record.status == EmailStatus.SENT,
            }
        )
    return rows


@sene_chantiers_admin_required
def home(request):
    """Search block plus the most recently modified dossiers."""
    recent = (
        Chantier.objects.select_related("commune")
        .annotate(last_touched=Max("corrective_measure_reports__updated_at"))
        .order_by("-created_at")[:RECENT_DOSSIERS_LIMIT]
    )
    return render(
        request,
        "sene_chantiers/home.html",
        {"recent_dossiers": [_decorate(c) for c in recent]},
    )


@sene_chantiers_admin_required
def satac_lookup(request):
    """Autocomplete endpoint backing the search block."""
    term = request.GET.get("query", "")
    results = satac.search(term, limit=8)
    existing = set(
        Chantier.objects.filter(
            satac_number__in=[r.satac_number for r in results]
        ).values_list("satac_number", flat=True)
    )
    return JsonResponse(
        {
            "results": [
                {
                    "satac_number": r.satac_number,
                    "label": r.label or f"N° SATAC: {r.satac_number}",
                    "has_dossier": r.satac_number in existing,
                }
                for r in results
            ]
        }
    )


@sene_chantiers_admin_required
def chantier_landing(request, satac_number):
    """Récapitulatif for one SATAC number.

    Renders either the "open a dossier" state or the dossier's reports and
    emails, depending on whether the dossier already exists. This is also
    the route the geoportal links to with a SATAC number.
    """
    chantier = (
        Chantier.objects.select_related("commune")
        .filter(satac_number=satac_number)
        .first()
    )

    if chantier is None:
        # Show what the permit lookup knows, so the inspector can confirm
        # they are opening a dossier for the right site.
        return render(
            request,
            "sene_chantiers/chantier_absent.html",
            {
                "satac_number": satac_number,
                "satac_result": satac.resolve(satac_number),
            },
        )

    return render(
        request,
        "sene_chantiers/chantier_landing.html",
        {
            "chantier": _decorate(chantier),
            "reports": _dossier_reports(chantier),
            "emails": _dossier_emails(chantier),
        },
    )


@sene_chantiers_admin_required
def chantier_create(request, satac_number):
    """Open a dossier for a SATAC number that does not have one yet."""
    existing = Chantier.objects.filter(satac_number=satac_number).first()
    if existing:
        messages.info(request, "Un dossier existe déjà pour ce numéro SATAC.")
        return redirect("sene_chantiers:chantier_landing", satac_number=satac_number)

    result = satac.resolve(satac_number)

    if request.method == "POST":
        form = ChantierForm(request.POST, satac_result=result)
        if form.is_valid():
            chantier = form.save(commit=False)
            chantier.satac_number = satac_number
            # Geometry is only ever taken from the permit lookup; it drives
            # the nearest-weather-station suggestion and nothing else.
            if result and result.geom is not None:
                chantier.geom = result.geom
            chantier.save()
            messages.success(request, "Dossier créé.")
            return redirect(
                "sene_chantiers:chantier_landing", satac_number=satac_number
            )
    else:
        form = ChantierForm(satac_result=result)

    return render(
        request,
        "sene_chantiers/chantier_create.html",
        {"form": form, "satac_number": satac_number, "satac_result": result},
    )
