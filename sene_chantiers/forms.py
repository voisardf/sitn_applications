"""Forms for sene_chantiers."""

from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from cadastre.models import Commune

from .models import (
    Chantier,
    Conformity,
    ControlPointAnswer,
    ControlReport,
    CorrectiveMeasure,
    CorrectiveMeasureReport,
    FollowUpStatus,
    MeasureFollowUp,
    ThemeAssessment,
)


class CommuneChoiceField(forms.ModelChoiceField):
    """cadastre.Commune has no __str__, so give it a readable label here."""

    def label_from_instance(self, obj):
        return obj.comnom


class ChantierForm(forms.ModelForm):
    """Opens a dossier for one SATAC number.

    Only the commune is pre-filled from the permit lookup; the site name,
    address, maître d'ouvrage and entreprise générale are always typed by
    the inspector.
    """

    commune = CommuneChoiceField(
        queryset=Commune.objects.only("idobj", "comnom", "numcom").order_by("comnom"),
        label=_("Commune"),
        empty_label=_("— Sélectionner —"),
    )

    class Meta:
        model = Chantier
        fields = [
            "site_name",
            "adresse",
            "commune",
            "maitre_ouvrage",
            "maitre_ouvrage_email",
            "entreprise_generale",
        ]
        widgets = {
            "site_name": forms.TextInput(
                attrs={"placeholder": "Réaménagement du secteur des Cadolles"}
            ),
            "adresse": forms.TextInput(attrs={"placeholder": "Rue et numéro"}),
            "maitre_ouvrage": forms.TextInput(attrs={"placeholder": "Nom du maître d'ouvrage"}),
            "maitre_ouvrage_email": forms.EmailInput(
                attrs={"placeholder": "prenom.nom@exemple.ch"}
            ),
            "entreprise_generale": forms.TextInput(
                attrs={"placeholder": "Facultatif"}
            ),
        }

    def __init__(self, *args, satac_result=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Every field is mandatory except the general contractor.
        for name, field in self.fields.items():
            field.required = name != "entreprise_generale"
            css = "form-select" if name == "commune" else "form-control"
            field.widget.attrs.setdefault("class", css)

        # Pre-fill what the permit lookup could resolve, without overriding
        # anything the inspector has already submitted.
        if satac_result and not self.is_bound:
            if satac_result.commune:
                self.initial.setdefault("commune", satac_result.commune.pk)


DATE_INPUT = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class ControlReportForm(forms.ModelForm):
    """Header and section 01/03 free-text panels of the initial report."""

    class Meta:
        model = ControlReport
        fields = [
            "control_date",
            "weather_condition",
            "temperature",
            "construction_phase",
            "next_control_date",
            "global_appreciation",
            "global_appreciation_is_manual_override",
            "observations_generales",
            "procedure_controle",
            "signature_date",
        ]
        widgets = {
            "control_date": DATE_INPUT,
            "next_control_date": DATE_INPUT,
            "signature_date": DATE_INPUT,
            "observations_generales": forms.Textarea(attrs={"rows": 4}),
            "procedure_controle": forms.Textarea(attrs={"rows": 4}),
            "global_appreciation_is_manual_override": forms.HiddenInput(),
            "global_appreciation": forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only the temperature and the conditional next-control date may be
        # left empty; everything else is mandatory (spec 4.2).
        optional = {"temperature", "next_control_date", "signature_date",
                    "global_appreciation_is_manual_override"}
        for name, field in self.fields.items():
            field.required = name not in optional
            if name in ("weather_condition", "construction_phase"):
                field.widget.attrs.setdefault("class", "form-select")
                field.queryset = field.queryset.filter(is_active=True)
            elif name == "global_appreciation":
                field.widget.attrs.setdefault("class", "form-check-input")
            elif name != "global_appreciation_is_manual_override":
                field.widget.attrs.setdefault("class", "form-control")


class ThemeAssessmentForm(forms.ModelForm):
    """Section 02 row. The appreciation is computed, not typed."""

    class Meta:
        model = ThemeAssessment
        fields = ["appreciation", "synthesis_remarks", "detail_observations"]
        widgets = {
            "synthesis_remarks": forms.Textarea(
                attrs={"rows": 2, "class": "form-control"}
            ),
            "detail_observations": forms.Textarea(
                attrs={"rows": 2, "class": "form-control"}
            ),
            "appreciation": forms.Select(attrs={"class": "form-select sc-appr"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Free-text remarks are mandatory; "R.A.S." is an acceptable answer.
        self.fields["synthesis_remarks"].required = True
        self.fields["detail_observations"].required = True


class ControlPointAnswerForm(forms.ModelForm):
    """Section 04 checklist row: Oui / Non / N.A."""

    class Meta:
        model = ControlPointAnswer
        fields = ["conformity"]
        widgets = {"conformity": forms.RadioSelect(attrs={"class": "form-check-input"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conformity"].required = True
        self.fields["conformity"].choices = Conformity.choices


class CorrectiveMeasureForm(forms.ModelForm):
    """Section 03 row."""

    class Meta:
        model = CorrectiveMeasure
        fields = ["order", "description", "responsible", "deadline", "status"]
        widgets = {
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "description": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "responsible": forms.TextInput(attrs={"class": "form-control"}),
            "deadline": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
        }


# Section 02 and 04 have a fixed number of rows, seeded when the report is
# created, so neither may gain or lose any.
ThemeAssessmentFormSet = inlineformset_factory(
    ControlReport, ThemeAssessment, form=ThemeAssessmentForm,
    extra=0, can_delete=False,
)
ControlPointAnswerFormSet = inlineformset_factory(
    ControlReport, ControlPointAnswer, form=ControlPointAnswerForm,
    extra=0, can_delete=False,
)
# Section 03 is a variable-length list.
CorrectiveMeasureFormSet = inlineformset_factory(
    ControlReport, CorrectiveMeasure, form=CorrectiveMeasureForm,
    extra=1, can_delete=True,
)


class CorrectiveMeasureReportForm(forms.ModelForm):
    """Header, section 01 appreciation and section 03/04 of a follow-up."""

    class Meta:
        model = CorrectiveMeasureReport
        fields = [
            "follow_up_date",
            "next_control_date",
            "global_appreciation",
            "global_appreciation_is_manual_override",
            "new_anomalies_description",
            "is_denunciation_escalation",
            "final_closure_state",
            "signature_date",
        ]
        widgets = {
            "follow_up_date": DATE_INPUT,
            "next_control_date": DATE_INPUT,
            "signature_date": DATE_INPUT,
            "new_anomalies_description": forms.Textarea(attrs={"rows": 3}),
            "global_appreciation_is_manual_override": forms.HiddenInput(),
            "global_appreciation": forms.RadioSelect(),
            "final_closure_state": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional = {
            "next_control_date", "signature_date", "new_anomalies_description",
            "is_denunciation_escalation", "final_closure_state",
            "global_appreciation_is_manual_override",
        }
        for name, field in self.fields.items():
            field.required = name not in optional
            if name == "is_denunciation_escalation":
                field.widget.attrs.setdefault("class", "form-check-input")
            elif name == "global_appreciation":
                field.widget.attrs.setdefault("class", "form-check-input")
            elif name not in ("global_appreciation_is_manual_override",
                              "final_closure_state"):
                field.widget.attrs.setdefault("class", "form-control")


class MeasureFollowUpForm(forms.ModelForm):
    """Section 02 row: one measure of the initial report, re-checked."""

    class Meta:
        model = MeasureFollowUp
        fields = ["findings", "status", "responsible", "new_deadline"]
        widgets = {
            "findings": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select sc-followup-status"}),
            "responsible": forms.TextInput(attrs={"class": "form-control"}),
            "new_deadline": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["findings"].required = True
        self.fields["status"].required = True
        self.fields["new_deadline"].required = False

    def clean(self):
        cleaned = super().clean()
        # A measure that is not closed must carry a new deadline.
        if cleaned.get("status") and cleaned["status"] != FollowUpStatus.CLOSED:
            if not cleaned.get("new_deadline"):
                self.add_error(
                    "new_deadline",
                    _("Une nouvelle échéance est requise tant que la mesure "
                      "n'est pas fermée."),
                )
        return cleaned


# The rows mirror the initial report's measures, so none may be added or
# removed here.
MeasureFollowUpFormSet = inlineformset_factory(
    CorrectiveMeasureReport, MeasureFollowUp, form=MeasureFollowUpForm,
    extra=0, can_delete=False,
)
