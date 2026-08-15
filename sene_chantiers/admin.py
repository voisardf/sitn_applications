"""Admin for the reference data, plus a superuser-only correction path.

Day-to-day, the reports are edited through the application's own tabbed
views: the section 01-04 layout, photo upload and cascade calculations
have no sensible admin equivalent. The admin registrations below exist
for one purpose only — letting a superuser repair a report that the
application itself refuses to reopen, typically because its notification
email has already gone out and locked it.

Two consequences of adding this second entry point, both deliberate:

Cross-row rules. `models.py` notes that three rules span a parent and its
child rows and therefore live in the view, not in `Model.clean()`. Two of
them — one ThemeAssessment per Theme, one ControlPointAnswer per
ControlPoint — are also database constraints, so the admin inherits them.
The third is not, and is re-implemented here in
`CorrectiveMeasureInline`: a report that is not Vert must keep at least
one mesure à prendre.

Cascades. The admin saves exactly what is typed. It does not recompute
the Vert/Jaune/Rouge cascade, which is what the application's own view
does on every save. A superuser correcting a conformity answer must
therefore set the resulting appreciation themselves.
"""

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    Appreciation,
    Chantier,
    ConstructionPhase,
    ControlPoint,
    ControlPointAnswer,
    ControlReport,
    CorrectiveMeasure,
    CorrectiveMeasureReport,
    MeasureFollowUp,
    Photo,
    Theme,
    ThemeAssessment,
    WeatherCondition,
)


@admin.register(WeatherCondition)
class WeatherConditionAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("label",)


@admin.register(ConstructionPhase)
class ConstructionPhaseAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("label",)


class ControlPointInline(admin.TabularInline):
    model = ControlPoint
    extra = 0


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "order")
    list_editable = ("order",)
    search_fields = ("label", "code")
    inlines = [ControlPointInline]


@admin.register(ControlPoint)
class ControlPointAdmin(admin.ModelAdmin):
    list_display = ("label", "theme", "order")
    list_editable = ("order",)
    list_filter = ("theme",)
    search_fields = ("label",)


@admin.register(Chantier)
class ChantierAdmin(SimpleHistoryAdmin):
    """Read-mostly: dossiers are created through the application."""

    list_display = ("satac_number", "site_name", "commune", "maitre_ouvrage",
                    "created_at")
    search_fields = ("satac_number", "site_name", "maitre_ouvrage",
                     "entreprise_generale")
    list_filter = ("created_at",)


# ---------------------------------------------------------------------------
# Superuser-only correction path for the reports themselves
# ---------------------------------------------------------------------------


class ReportAdminMixin:
    """Restricts a report to superusers and honours the two freeze rules.

    A report is editable here when it is unlocked (the application allows
    that too), and also when it is locked but the dossier has never
    escalated towards a denunciation — that is the break-glass case this
    admin exists for. Once the dossier has entered the denunciation
    track, the file may end up before the Ministère public and is frozen:
    visible, never editable.
    """

    def _is_frozen(self, obj):
        if obj is None:
            return False
        return obj.is_locked and obj.chantier.has_entered_denunciation_track

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request, obj=None):
        # Reports are opened by the application, which sets up the child
        # rows from the reference data; an empty admin-made report would
        # be missing all of them.
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        if not self.has_module_permission(request):
            return False
        return not self._is_frozen(obj)

    def get_readonly_fields(self, request, obj=None):
        if self._is_frozen(obj):
            return [f.name for f in self.model._meta.fields]
        return super().get_readonly_fields(request, obj)


class CorrectiveMeasureFormSet(BaseInlineFormSet):
    """A non-Vert report must keep at least one mesure à prendre.

    The same rule as `views._cross_row_errors`. It cannot live on the
    model: it asks whether a *set* of child rows is empty, which is only
    knowable once the formset has been processed.
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        live = [
            form for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        appreciation = getattr(self.instance, "global_appreciation", None)
        if appreciation and appreciation != Appreciation.VERT and not live:
            raise ValidationError(
                _("Au moins une mesure à prendre est requise lorsque le "
                  "chantier n'est pas conforme.")
            )


class CorrectiveMeasureInline(admin.TabularInline):
    model = CorrectiveMeasure
    formset = CorrectiveMeasureFormSet
    extra = 0


class ThemeAssessmentInline(admin.TabularInline):
    model = ThemeAssessment
    extra = 0


class ControlPointAnswerInline(admin.TabularInline):
    model = ControlPointAnswer
    extra = 0


class MeasureFollowUpInline(admin.TabularInline):
    model = MeasureFollowUp
    extra = 0


class ControlReportPhotoInline(admin.TabularInline):
    model = Photo
    fk_name = "control_report"
    extra = 0


class CorrectiveMeasureReportPhotoInline(admin.TabularInline):
    model = Photo
    fk_name = "corrective_measure_report"
    extra = 0


@admin.register(ControlReport)
class ControlReportAdmin(ReportAdminMixin, SimpleHistoryAdmin):
    list_display = ("chantier", "control_date", "global_appreciation",
                    "inspector", "is_locked")
    search_fields = ("chantier__satac_number", "chantier__site_name")
    list_filter = ("global_appreciation", "control_date")
    autocomplete_fields = ("chantier",)
    inlines = [
        ThemeAssessmentInline,
        ControlPointAnswerInline,
        CorrectiveMeasureInline,
        ControlReportPhotoInline,
    ]


@admin.register(CorrectiveMeasureReport)
class CorrectiveMeasureReportAdmin(ReportAdminMixin, SimpleHistoryAdmin):
    list_display = ("chantier", "follow_up_date", "global_appreciation",
                    "inspector", "is_denunciation_escalation", "is_locked")
    search_fields = ("chantier__satac_number", "chantier__site_name")
    list_filter = ("global_appreciation", "is_denunciation_escalation",
                   "follow_up_date")
    autocomplete_fields = ("chantier",)
    inlines = [MeasureFollowUpInline, CorrectiveMeasureReportPhotoInline]
