"""Views for sene_chantiers.

Every view is gated on SSO authentication plus membership of the
sene_chantiers_admin group.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .auth import sene_chantiers_admin_required
from .forms import (
    ChantierForm,
    ControlPointAnswerFormSet,
    ControlReportForm,
    CorrectiveMeasureFormSet,
    ThemeAssessmentFormSet,
)
from .labels import (
    appreciation_label,
    email_status_appreciation,
    email_status_label,
)
from .models import (
    Appreciation,
    Chantier,
    ConstructionPhase,
    ControlPoint,
    ControlPointAnswer,
    ControlReport,
    EmailStatus,
    Theme,
    ThemeAssessment,
    WeatherCondition,
)
from .services import appreciation as appreciation_service
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


def _build_report_skeleton(chantier, user):
    """Create the initial report with its fixed section 02 and 04 rows.

    Section 02 and 04 have a known shape taken from the paper form, so the
    rows are materialised up front and the inspector only fills them in.
    Answers start empty: an unanswered checklist point is not the same as
    an N.A. one, which is a deliberate, complete answer.
    """
    report = ControlReport.objects.create(
        chantier=chantier,
        control_date=timezone.localdate(),
        weather_condition=WeatherCondition.objects.filter(is_active=True).first(),
        construction_phase=ConstructionPhase.objects.filter(is_active=True).first(),
        inspector=user,
    )
    ThemeAssessment.objects.bulk_create(
        [ThemeAssessment(control_report=report, theme=theme)
         for theme in Theme.objects.all()]
    )
    ControlPointAnswer.objects.bulk_create(
        [ControlPointAnswer(control_report=report, control_point=point, conformity="")
         for point in ControlPoint.objects.select_related("theme")]
    )
    return report


@sene_chantiers_admin_required
def control_report_create(request, satac_number):
    """Open the initial report for a dossier that has none yet."""
    chantier = get_object_or_404(Chantier, satac_number=satac_number)
    if getattr(chantier, "control_report", None):
        return redirect("sene_chantiers:control_report_edit", satac_number=satac_number)
    if request.method != "POST":
        return redirect("sene_chantiers:chantier_landing", satac_number=satac_number)

    _build_report_skeleton(chantier, request.user)
    messages.success(request, "Rapport de contrôle créé.")
    return redirect("sene_chantiers:control_report_edit", satac_number=satac_number)


@sene_chantiers_admin_required
def control_report_edit(request, satac_number):
    """Sections 01 to 04 of the initial report.

    Cross-row rules that no Model.clean() can enforce are checked here,
    where the parent form and every formset are validated but unsaved.
    """
    chantier = get_object_or_404(Chantier, satac_number=satac_number)
    report = get_object_or_404(ControlReport, chantier=chantier)
    read_only = report.is_locked

    if request.method == "POST" and not read_only:
        # Tab isolation: the posted SATAC must match the report being saved.
        posted_satac = request.POST.get("satac_number")
        if posted_satac and str(posted_satac) != str(satac_number):
            raise PermissionDenied("Le rapport soumis ne correspond pas au dossier.")

        form = ControlReportForm(request.POST, instance=report)
        themes = ThemeAssessmentFormSet(request.POST, instance=report, prefix="themes")
        answers = ControlPointAnswerFormSet(
            request.POST, instance=report, prefix="answers"
        )
        measures = CorrectiveMeasureFormSet(
            request.POST, instance=report, prefix="measures"
        )
        is_draft = "save_draft" in request.POST

        if is_draft:
            # A draft may be incomplete; persist whatever validates.
            form.is_valid()
            _save_draft(report, request, form, themes, answers, measures)
            messages.info(request, "Brouillon enregistré.")
            return redirect(
                "sene_chantiers:control_report_edit", satac_number=satac_number
            )

        all_valid = all([form.is_valid(), themes.is_valid(),
                         answers.is_valid(), measures.is_valid()])
        cross_errors = _cross_row_errors(form, measures) if all_valid else []

        if all_valid and not cross_errors:
            report = form.save()
            themes.save()
            answers.save()
            measures.save()
            _apply_cascades(report, form)
            messages.success(request, "Rapport enregistré.")
            return redirect(
                "sene_chantiers:chantier_landing", satac_number=satac_number
            )

        for error in cross_errors:
            messages.error(request, error)
    else:
        form = ControlReportForm(instance=report)
        themes = ThemeAssessmentFormSet(instance=report, prefix="themes")
        answers = ControlPointAnswerFormSet(instance=report, prefix="answers")
        measures = CorrectiveMeasureFormSet(instance=report, prefix="measures")

    return render(
        request,
        "sene_chantiers/control_report.html",
        {
            "chantier": chantier,
            "report": report,
            "form": form,
            "theme_formset": themes,
            "answer_formset": answers,
            "measure_formset": measures,
            "answers_by_theme": _group_answers(answers),
            "read_only": read_only,
        },
    )


def _cross_row_errors(form, measures):
    """Rules spanning the parent and its children (spec module docstring)."""
    errors = []
    appreciation = form.cleaned_data.get("global_appreciation")
    live = [
        f for f in measures.forms
        if f.cleaned_data and not f.cleaned_data.get("DELETE")
    ]
    if appreciation and appreciation != Appreciation.VERT and not live:
        errors.append(
            "Au moins une mesure à prendre est requise lorsque le chantier "
            "n'est pas conforme."
        )
    return errors


def _apply_cascades(report, form):
    """Recompute theme and global appreciations unless overridden."""
    suggested = appreciation_service.recompute_control_report(report)
    if not form.cleaned_data.get("global_appreciation_is_manual_override"):
        if report.global_appreciation != suggested:
            report.global_appreciation = suggested
            report.save(update_fields=["global_appreciation"])


def _save_draft(report, request, form, themes, answers, measures):
    """Persist a partially filled report without enforcing completeness."""
    if form.is_valid():
        form.save()
    for formset in (themes, answers, measures):
        if formset.is_valid():
            formset.save()


def _group_answers(answer_formset):
    """Section 04 renders one block per theme."""
    grouped = {}
    for subform in answer_formset.forms:
        point = subform.instance.control_point
        grouped.setdefault(point.theme, []).append(subform)
    return [{"theme": theme, "forms": forms_} for theme, forms_ in grouped.items()]
