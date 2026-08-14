"""Views for sene_chantiers.

Every view is gated on SSO authentication plus membership of the
sene_chantiers_admin group.
"""

from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import render

from .auth import sene_chantiers_admin_required
from .models import Appreciation, Chantier
from .services import satac

RECENT_DOSSIERS_LIMIT = 5

# The landing list shows one pill per dossier; the wording matches the
# Courriels column of the mockups.
APPRECIATION_LABELS = {
    Appreciation.VERT: "Conforme",
    Appreciation.JAUNE: "Mesures à prendre",
    Appreciation.ROUGE: "Non conforme",
}


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
    chantier.appreciation_label = APPRECIATION_LABELS.get(appreciation, "Sans rapport")
    return chantier


@sene_chantiers_admin_required
def home(request):
    """Search block plus the most recently modified dossiers."""
    recent = (
        Chantier.objects.select_related("commune")
        .annotate(
            last_touched=Max("control_report__updated_at"),
            last_followup=Max("corrective_measure_reports__updated_at"),
        )
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
