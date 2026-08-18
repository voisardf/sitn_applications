"""Views for sene_chantiers.

Every view is gated on SSO authentication plus membership of the
sene_chantiers_admin group.
"""

import os

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Max
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .auth import sene_chantiers_admin_required
from .forms import (
    ChantierForm,
    ControlPointAnswerFormSet,
    ControlReportForm,
    CorrectiveMeasureFormSet,
    CorrectiveMeasureReportForm,
    EmailRecordForm,
    MeasureFollowUpFormSet,
    ThemeAssessmentFormSet,
)
from .labels import (
    appreciation_label,
    email_status_appreciation,
    email_status_label,
    followup_conclusion_lines,
)
from .models import (
    Appreciation,
    Chantier,
    ConstructionPhase,
    ControlPoint,
    ControlPointAnswer,
    ControlReport,
    CorrectiveMeasureReport,
    EmailRecord,
    EmailStatus,
    EmailTemplate,
    FollowUpStatus,
    MeasureFollowUp,
    MeasureStatus,
    Photo,
    PhotoStatus,
    Theme,
    ThemeAssessment,
    WeatherCondition,
)
from .services import appreciation as appreciation_service
from .services import deadlines as deadlines_service
from .services import emails as email_service
from .services import excel as excel_service
from .services import pdf as pdf_service
from .services import satac

RECENT_DOSSIERS_LIMIT = 5


def _latest_appreciation(chantier):
    """Appreciation of the most recent report, initial or follow-up."""
    report = chantier.latest_report
    return report.global_appreciation if report else None


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
                "kind_slug": "controle",
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
                "kind_slug": "suivi",
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
        report = record.report
        rows.append(
            {
                "pk": record.pk,
                "kind_slug": "controle" if record.control_report_id else "suivi",
                "report_pk": report.pk if report else None,
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
            "is_compliant": chantier.is_compliant,
            "is_closed": chantier.is_closed,
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
            # Re-bind with every field optional: validated against the
            # normal required set, a single empty field would discard the
            # whole form and lose what the inspector just typed.
            form = ControlReportForm(request.POST, instance=report, draft=True)
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
        incomplete_sections = _incomplete_control_sections(
            form, themes, answers, measures
        )
    else:
        form = ControlReportForm(instance=report)
        themes = ThemeAssessmentFormSet(instance=report, prefix="themes")
        answers = ControlPointAnswerFormSet(instance=report, prefix="answers")
        measures = CorrectiveMeasureFormSet(instance=report, prefix="measures")
        incomplete_sections = []

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
            "answers_by_theme": _group_answers(answers, themes),
            "incomplete_sections": incomplete_sections,
            "read_only": read_only,
            "photo_kind": "controle",
            "photo_max_mb": settings.SENE_CHANTIERS_PHOTO_MAX_SIZE_MB,
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
    """Persist a partially filled report without enforcing completeness.

    Only fields that carry a value are written. A draft must never erase
    what is already stored, and an empty value cannot be pushed into a
    column the database declares NOT NULL — which is what a blank control
    date would do on a report opened and immediately saved.
    """
    if form.is_valid():
        # ModelForm._post_clean() has already copied cleaned_data onto the
        # instance, so an empty value is *already* sitting on `report`.
        # Skipping the field is not enough — the stored value has to be put
        # back, or a blank control date reaches a NOT NULL column.
        stored = type(report).objects.get(pk=report.pk)
        for name, value in form.cleaned_data.items():
            if value in (None, "") and not report._meta.get_field(name).null:
                setattr(report, name, getattr(stored, name))
            else:
                setattr(report, name, value)
        report.save()
    for formset in (themes, answers, measures):
        if formset.is_valid():
            formset.save()


# Which tab each part of the initial report is filled in. Used to tell the
# inspector *where* something is missing: the failure is otherwise
# invisible when the offending field sits in a tab that is not on screen.
CONTROL_SECTIONS = {
    "01": "Informations générales",
    "02": "Synthèse par thème",
    "03": "Mesures à prendre",
    "04": "Détail des thèmes",
}


def _incomplete_control_sections(form, themes, answers, measures):
    """The sections holding a missing or invalid field, in tab order."""
    sections = set()
    tab01 = {"control_date", "weather_condition", "construction_phase",
             "global_appreciation", "signature_date", "next_control_date"}
    tab03 = {"observations_generales", "procedure_controle"}
    for name in form.errors:
        if name in tab03:
            sections.add("03")
        elif name in tab01 or name == "__all__":
            sections.add("01")
    for subform in themes.forms:
        for name in subform.errors:
            # The per-theme observations are captured in section 04, beside
            # the checklist they comment on; the rest of the assessment
            # belongs to the section 02 summary.
            sections.add("04" if name == "detail_observations" else "02")
    if themes.non_form_errors():
        sections.add("02")
    if any(sub.errors for sub in answers.forms) or answers.non_form_errors():
        sections.add("04")
    if any(sub.errors for sub in measures.forms) or measures.non_form_errors():
        sections.add("03")
    return [{"code": c, "label": CONTROL_SECTIONS[c]} for c in sorted(sections)]


def _group_answers(answer_formset, theme_formset=None):
    """Section 04 renders one block per theme.

    Each block also carries that theme's assessment form, because the
    per-theme observations live on `ThemeAssessment.detail_observations`
    and are captured in section 04 beside the checklist they comment on.
    They are a required field: without them rendered, the report cannot
    validate at all and the failure has nowhere to display.
    """
    assessment_forms = {}
    if theme_formset is not None:
        assessment_forms = {
            subform.instance.theme_id: subform
            for subform in theme_formset.forms
            if subform.instance.theme_id
        }

    grouped = {}
    for subform in answer_formset.forms:
        point = subform.instance.control_point
        grouped.setdefault(point.theme, []).append(subform)
    return [
        {
            "theme": theme,
            "forms": forms_,
            "assessment_form": assessment_forms.get(theme.pk),
        }
        for theme, forms_ in grouped.items()
    ]


# Section 03 of a follow-up is generated from the data rather than typed.
def followup_observations(report):
    """The templated 'observations générales' paragraph."""
    followups = list(report.measure_followups.all())
    total = len(followups)
    fixed = sum(1 for f in followups if f.status == FollowUpStatus.CLOSED)
    remaining = total - fixed

    parts = [
        f"Lors du contrôle de suivi du "
        f"{report.follow_up_date.strftime('%d.%m.%Y')}, les mesures "
        f"correctives prescrites dans le rapport précédent ont été "
        f"vérifiées sur place.",
        f"{fixed} mesure(s) sur {total} ont été corrigées et sont conformes.",
    ]
    if remaining:
        parts.append(
            f"{remaining} mesure(s) restent partiellement réalisées et "
            f"feront l'objet d'un nouveau contrôle."
        )
    parts.append(
        report.new_anomalies_description.strip()
        or "Aucune nouvelle anomalie n'a été constatée."
    )
    return parts


def _previous_report(chantier):
    """The most recently settled report, which a new follow-up chains from."""
    last_followup = chantier.corrective_measure_reports.order_by(
        "-follow_up_date", "-pk"
    ).first()
    if last_followup:
        return last_followup
    return getattr(chantier, "control_report", None)


# The initial report's measure statuses map onto the follow-up vocabulary.
_CARRY_OVER_STATUS = {
    MeasureStatus.CLOSED: FollowUpStatus.CLOSED,
    MeasureStatus.IN_PROGRESS: FollowUpStatus.OPEN,
    MeasureStatus.OPEN: FollowUpStatus.OPEN,
}


@sene_chantiers_admin_required
def corrective_measure_report_create(request, satac_number):
    """Open the next follow-up, chained from the most recent control."""
    chantier = get_object_or_404(Chantier, satac_number=satac_number)
    control_report = getattr(chantier, "control_report", None)
    if control_report is None:
        messages.error(
            request, "Le contrôle initial doit exister avant un suivi."
        )
        return redirect("sene_chantiers:chantier_landing", satac_number=satac_number)
    if chantier.is_compliant:
        # A compliant visit ends the cycle: only the notification email
        # remains. If that conclusion was a mistake, the inspector corrects
        # the report itself — which reopens the cycle — rather than opening
        # another follow-up on top of it.
        messages.error(
            request,
            "Le dernier contrôle conclut à la conformité du chantier : "
            "aucun nouveau suivi n'est possible. Corriger le dernier "
            "rapport si ce constat est erroné.",
        )
        return redirect("sene_chantiers:chantier_landing", satac_number=satac_number)
    if request.method != "POST":
        return redirect("sene_chantiers:chantier_landing", satac_number=satac_number)

    previous = _previous_report(chantier)
    previous_followup = (
        previous if isinstance(previous, CorrectiveMeasureReport) else None
    )

    report = CorrectiveMeasureReport.objects.create(
        chantier=chantier,
        previous_followup=previous_followup,
        follow_up_date=timezone.localdate(),
        inspector=request.user,
    )

    # Carry over every measure of the initial report, with the state it had
    # at the previous control.
    previous_states = {}
    if previous_followup:
        previous_states = {
            f.original_measure_id: f.status
            for f in previous_followup.measure_followups.all()
        }

    MeasureFollowUp.objects.bulk_create([
        MeasureFollowUp(
            corrective_measure_report=report,
            original_measure=measure,
            state_at_previous_control=previous_states.get(
                measure.pk, _CARRY_OVER_STATUS.get(measure.status, FollowUpStatus.OPEN)
            ),
            status=previous_states.get(
                measure.pk, _CARRY_OVER_STATUS.get(measure.status, FollowUpStatus.OPEN)
            ),
        )
        for measure in control_report.corrective_measures.all()
    ])

    messages.success(request, "Rapport de suivi créé.")
    return redirect(
        "sene_chantiers:corrective_measure_report_edit", pk=report.pk
    )


@sene_chantiers_admin_required
def corrective_measure_report_edit(request, pk):
    """Sections 01 to 04 of a corrective-measures follow-up report."""
    report = get_object_or_404(
        CorrectiveMeasureReport.objects.select_related("chantier"), pk=pk
    )
    chantier = report.chantier
    read_only = report.is_locked

    if request.method == "POST" and not read_only:
        posted_satac = request.POST.get("satac_number")
        if posted_satac and str(posted_satac) != str(chantier.satac_number):
            raise PermissionDenied("Le rapport soumis ne correspond pas au dossier.")

        form = CorrectiveMeasureReportForm(request.POST, instance=report)
        followups = MeasureFollowUpFormSet(
            request.POST, instance=report, prefix="followups"
        )
        is_draft = "save_draft" in request.POST

        if is_draft:
            if form.is_valid():
                form.save()
            if followups.is_valid():
                followups.save()
            messages.info(request, "Brouillon enregistré.")
            return redirect(
                "sene_chantiers:corrective_measure_report_edit", pk=report.pk
            )

        if form.is_valid() and followups.is_valid():
            report = form.save()
            followups.save()
            _apply_followup_cascade(report, form)
            messages.success(request, "Rapport de suivi enregistré.")
            return redirect(
                "sene_chantiers:chantier_landing",
                satac_number=chantier.satac_number,
            )
    else:
        form = CorrectiveMeasureReportForm(instance=report)
        followups = MeasureFollowUpFormSet(instance=report, prefix="followups")

    return render(
        request,
        "sene_chantiers/corrective_measure_report.html",
        {
            "chantier": chantier,
            "report": report,
            "form": form,
            "followup_formset": followups,
            "first_control_date": chantier.control_report.control_date,
            "observations": followup_observations(report),
            "read_only": read_only,
            "photo_kind": "suivi",
            "photo_max_mb": settings.SENE_CHANTIERS_PHOTO_MAX_SIZE_MB,
            # Served as data rather than restated in the template's JS,
            # which had already drifted from the server's wording.
            "conclusion_lines": followup_conclusion_lines(),
        },
    )


def _apply_followup_cascade(report, form):
    """Recompute the global appreciation from the measure statuses."""
    statuses = list(
        report.measure_followups.values_list("status", flat=True)
    )
    suggested = appreciation_service.followup_global_appreciation(statuses)
    if not form.cleaned_data.get("global_appreciation_is_manual_override"):
        if report.global_appreciation != suggested:
            report.global_appreciation = suggested
            report.save(update_fields=["global_appreciation"])


def _report_from_kind(kind, pk):
    """Resolve the report a photo belongs to, from the URL."""
    if kind == "controle":
        return get_object_or_404(ControlReport, pk=pk)
    if kind == "suivi":
        return get_object_or_404(CorrectiveMeasureReport, pk=pk)
    raise Http404("Type de rapport inconnu.")


def _photo_payload(photo):
    return {
        "id": photo.pk,
        "status": photo.status,
        "caption": photo.caption,
        "error": photo.error_message,
        "url": (
            reverse("sene_chantiers:photo_file", args=[photo.pk])
            if photo.image else ""
        ),
    }


@sene_chantiers_admin_required
def photo_upload(request, kind, pk):
    """Stage an uploaded photo; the worker sanitises it out of band."""
    report = _report_from_kind(kind, pk)
    if report.is_locked:
        raise PermissionDenied("Le rapport est verrouillé.")
    if request.method != "POST":
        raise Http404()

    uploaded = request.FILES.get("photo")
    if not uploaded:
        return JsonResponse({"error": "Aucun fichier reçu."}, status=400)

    photo = Photo(caption="", status=PhotoStatus.PENDING)
    if isinstance(report, ControlReport):
        photo.control_report = report
    else:
        photo.corrective_measure_report = report
    photo.raw_upload = uploaded

    try:
        # Runs the extension and size validators before anything is stored.
        photo.full_clean(exclude=["image"])
    except ValidationError as exc:
        first = next(iter(exc.message_dict.values()))[0]
        return JsonResponse({"error": first}, status=400)

    photo.save()
    return JsonResponse(_photo_payload(photo), status=201)


@sene_chantiers_admin_required
def photo_caption(request, pk):
    """Save the per-photo remark."""
    photo = get_object_or_404(Photo, pk=pk)
    if photo.report.is_locked:
        raise PermissionDenied("Le rapport est verrouillé.")
    if request.method != "POST":
        raise Http404()
    photo.caption = request.POST.get("caption", "").strip()
    photo.save(update_fields=["caption"])
    return JsonResponse(_photo_payload(photo))


@sene_chantiers_admin_required
def photo_delete(request, pk):
    """Remove a photo from a report that is still editable."""
    photo = get_object_or_404(Photo, pk=pk)
    if photo.report.is_locked:
        raise PermissionDenied("Le rapport est verrouillé.")
    if request.method != "POST":
        raise Http404()
    photo.delete()
    return JsonResponse({"deleted": True})


@sene_chantiers_admin_required
def photo_status(request, kind, pk):
    """Poll the queue so the UI can show progress while the worker runs."""
    report = _report_from_kind(kind, pk)
    return JsonResponse(
        {"photos": [_photo_payload(p) for p in report.photos.all()]}
    )


@sene_chantiers_admin_required
def photo_file(request, pk):
    """Stream a sanitised photo from the read-only data volume.

    /data is not web-served, and these are site photographs that must not
    be publicly reachable, so they go through the same access gate as
    every other view — mirroring ppe's get_final_documents.
    """
    photo = get_object_or_404(Photo, pk=pk)
    if not photo.image:
        raise Http404("Photo non disponible.")

    path = os.path.join(settings.DOWNLOAD_ROOT, photo.image.name)
    if not os.path.exists(path):
        raise Http404("Fichier introuvable.")

    return FileResponse(open(path, "rb"))


@sene_chantiers_admin_required
def email_manager(request, kind, pk):
    """Prepare, edit, save as draft and send a report's notification email.

    A draft is overwritten in place, per the specification: only a sent
    record becomes a permanent history entry.
    """
    report = _report_from_kind(kind, pk)
    chantier = report.chantier

    record = report.email_records.filter(status=EmailStatus.DRAFT).first()
    sent_record = report.email_records.filter(status=EmailStatus.SENT).first()
    is_sent = sent_record is not None
    if is_sent:
        record = sent_record

    if record is None:
        subject, body = email_service.render(report)
        record = EmailRecord(
            chantier=chantier,
            template_used=email_service.select_template(report),
            recipient_email=chantier.maitre_ouvrage_email,
            subject=subject,
            body=body,
        )
        if isinstance(report, ControlReport):
            record.control_report = report
        else:
            record.corrective_measure_report = report
        record.save()
        record.selected_photos.set(report.photos.filter(status=PhotoStatus.DONE))

    if request.method == "POST" and not is_sent:
        posted_satac = request.POST.get("satac_number")
        if posted_satac and str(posted_satac) != str(chantier.satac_number):
            raise PermissionDenied("Le courriel soumis ne correspond pas au dossier.")

        action = request.POST.get("action", "save")
        if action == "reset":
            subject, body = email_service.render(report)
            record.subject, record.body = subject, body
            record.template_used = email_service.select_template(report)
            record.save()
            messages.info(request, "Texte réinitialisé depuis le modèle.")
            return redirect("sene_chantiers:email_manager", kind=kind, pk=pk)

        form = EmailRecordForm(request.POST, instance=record)
        if form.is_valid():
            record = form.save()
            chosen = request.POST.getlist("photos")
            record.selected_photos.set(
                report.photos.filter(pk__in=chosen, status=PhotoStatus.DONE)
            )
            if action == "send":
                try:
                    email_service.send(record)
                except Exception as exc:  # SMTP is outside our control
                    messages.error(request, f"Échec de l'envoi : {exc}")
                    return redirect(
                        "sene_chantiers:email_manager", kind=kind, pk=pk
                    )
                messages.success(
                    request,
                    "Courriel envoyé. Le rapport est désormais en lecture seule.",
                )
                return redirect(
                    "sene_chantiers:chantier_landing",
                    satac_number=chantier.satac_number,
                )
            messages.info(request, "Brouillon enregistré.")
            return redirect("sene_chantiers:email_manager", kind=kind, pk=pk)
    else:
        form = EmailRecordForm(instance=record)

    return render(
        request,
        "sene_chantiers/email_manager.html",
        {
            "chantier": chantier,
            "report": report,
            "record": record,
            "form": form,
            "kind": kind,
            "is_sent": is_sent,
            "budget": email_service.attachment_budget(record),
            "available_photos": report.photos.filter(status=PhotoStatus.DONE),
            "selected_ids": set(
                record.selected_photos.values_list("pk", flat=True)
            ),
            "template_label": EmailTemplate(record.template_used).label,
        },
    )


@sene_chantiers_admin_required
def pdf_export(request, kind, pk):
    """Render one report through the WeasyPrint service and stream it."""
    report = _report_from_kind(kind, pk)
    try:
        content = pdf_service.report_pdf(report)
    except pdf_service.PdfServiceError as exc:
        messages.error(request, str(exc))
        return redirect(
            "sene_chantiers:chantier_landing",
            satac_number=report.chantier.satac_number,
        )

    prefix = "controle" if kind == "controle" else "suivi"
    filename = f"rapport_{prefix}_{report.chantier.satac_number}.pdf"
    response = HttpResponse(content, content_type="application/pdf")
    # Inline: the spec asks for the PDF to open in a new tab.
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@sene_chantiers_admin_required
def excel_export(request, satac_number):
    """Whole-dossier workbook, generated per request and never stored."""
    chantier = get_object_or_404(Chantier, satac_number=satac_number)
    content = excel_service.dossier_workbook(chantier)
    response = HttpResponse(
        content,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        f'attachment; filename="dossier_{satac_number}.xlsx"'
    )
    return response


@sene_chantiers_admin_required
def deadlines_view(request):
    """Every corrective measure approaching or past its deadline.

    Shows the whole service's workload, not just the signed-in
    inspector's, since cover during absences is the point of the list.
    """
    counts = deadlines_service.banner_counts()
    return render(
        request,
        "sene_chantiers/deadlines.html",
        {
            "rows": counts["rows"],
            "closures": counts["closures"],
            "overdue_count": counts["overdue"],
            "due_soon_count": counts["due_soon"],
            "pending_closure_count": counts["pending_closure"],
            "warning_days": deadlines_service.WARNING_DAYS,
        },
    )
