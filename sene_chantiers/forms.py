"""Forms for sene_chantiers.

Two base classes carry what every form here needs, rather than each form
repeating it: `BootstrapModelForm` for the widget styling and the two
adjustments the models cannot express, `DraftableModelForm` for the
"Enregistrer le brouillon" button. Before them, six near-identical
`__init__` loops said the same thing six times over.
"""

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
    EmailRecord,
    FollowUpStatus,
    MeasureFollowUp,
    ThemeAssessment,
)


def date_input(**attrs):
    """A native date picker.

    A function rather than one shared widget instance: `Meta.widgets`
    values are not copied per field, so a single instance listed for three
    date fields would have them share one attribute dictionary.
    """
    return forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", **attrs})


class BootstrapModelForm(forms.ModelForm):
    """Widget classes, plus the two things the models cannot say.

    `required_anyway` names fields the model lets be blank but a finished
    report may not leave empty. The column has to accept '' so that an
    interrupted entry can be stored as a draft; the obligation is
    therefore the form's to state, not the database's.

    `never_required` names fields that must not be demanded at all. In
    practice the hidden override flags: a model BooleanField yields a
    *required* form field, so leaving the box unchecked would fail
    validation.

    `widget_css` gives the CSS class per field — `None` to leave a widget
    bare; anything unlisted gets `default_widget_css`.
    """

    required_anyway = ()
    never_required = ()
    widget_css = {}
    default_widget_css = "form-control"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.required_anyway:
            self.fields[name].required = True
        for name in self.never_required:
            self.fields[name].required = False
        for name, field in self.fields.items():
            css = self.widget_css.get(name, self.default_widget_css)
            if css:
                field.widget.attrs.setdefault("class", css)


class DraftableModelForm(BootstrapModelForm):
    """A form the inspector may save half-filled.

    `draft=True` relaxes every field *and* tells the instance to stand its
    own completeness rules down — see `BaseReport.is_draft`. Both halves
    are needed. Without the first, one empty field discards the whole form
    and the inspector loses exactly what the button promised to keep;
    without the second, `ModelForm._post_clean()` re-imposes through the
    model what the form has just relaxed, and the save fails in silence.

    Setting `is_draft` is harmless on the child models that carry no
    completeness rule of their own: a uniform contract rather than a
    per-model special case.
    """

    def __init__(self, *args, draft=False, **kwargs):
        self.draft = draft
        super().__init__(*args, **kwargs)
        self.instance.is_draft = draft
        if draft:
            for field in self.fields.values():
                field.required = False


class CommuneChoiceField(forms.ModelChoiceField):
    """cadastre.Commune has no __str__, so give it a readable label here."""

    def label_from_instance(self, obj):
        return obj.comnom


class ChantierForm(BootstrapModelForm):
    """Opens a dossier for one SATAC number.

    Only the commune is pre-filled from the permit lookup; the site name,
    address, maître d'ouvrage and entreprise générale are always typed by
    the inspector.
    """

    widget_css = {"commune": "form-select"}

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
            "maitre_ouvrage": forms.TextInput(
                attrs={"placeholder": "Nom du maître d'ouvrage"}
            ),
            "maitre_ouvrage_email": forms.EmailInput(
                attrs={"placeholder": "prenom.nom@exemple.ch"}
            ),
            "entreprise_generale": forms.TextInput(
                attrs={"placeholder": "Facultatif"}
            ),
        }

    def __init__(self, *args, satac_result=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill what the permit lookup could resolve, without overriding
        # anything the inspector has already submitted, and say where the
        # value came from.
        if satac_result and not self.is_bound and satac_result.commune:
            self.initial.setdefault("commune", satac_result.commune.pk)
            self.fields["commune"].help_text = _(
                "Pré-renseignée depuis l'autorisation de construire."
            )


class ControlReportForm(DraftableModelForm):
    """Header and section 01/03 free-text panels of the initial report."""

    required_anyway = ("observations_generales", "procedure_controle")
    never_required = ("global_appreciation_is_manual_override",)
    widget_css = {
        "weather_condition": "form-select",
        "construction_phase": "form-select",
        "global_appreciation": "form-check-input",
        "global_appreciation_is_manual_override": None,
    }

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
            "control_date": date_input(),
            "next_control_date": date_input(),
            "signature_date": date_input(),
            "observations_generales": forms.Textarea(attrs={"rows": 4}),
            "procedure_controle": forms.Textarea(attrs={"rows": 4}),
            "global_appreciation_is_manual_override": forms.HiddenInput(),
            "global_appreciation": forms.RadioSelect(),
        }
        help_texts = {
            "next_control_date": _(
                "Délai de mise en conformité, requis si non conforme."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Retired reference rows stay readable on old reports but are no
        # longer offered for a new one.
        for name in ("weather_condition", "construction_phase"):
            field = self.fields[name]
            field.queryset = field.queryset.filter(is_active=True)


class ThemeAssessmentForm(DraftableModelForm):
    """Section 02 row. The appreciation is computed, not typed.

    Both free-text fields are mandatory; "R.A.S." is an acceptable answer.
    """

    required_anyway = ("synthesis_remarks", "detail_observations")
    widget_css = {"appreciation": "form-select sc-appr"}

    class Meta:
        model = ThemeAssessment
        fields = ["appreciation", "synthesis_remarks", "detail_observations"]
        widgets = {
            "synthesis_remarks": forms.Textarea(attrs={"rows": 2}),
            "detail_observations": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {
            "detail_observations": _(
                "Constats pour ce thème, repris dans le rapport PDF."
            ),
        }


class ControlPointAnswerForm(DraftableModelForm):
    """Section 04 checklist row: Oui / Non / N.A."""

    widget_css = {"conformity": "form-check-input"}

    class Meta:
        model = ControlPointAnswer
        fields = ["conformity"]
        widgets = {"conformity": forms.RadioSelect()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exactly the three answers, without the blank choice a ModelForm
        # adds: an unanswered point is stored as '', but that is not
        # something the inspector picks on purpose.
        self.fields["conformity"].choices = Conformity.choices


class CorrectiveMeasureForm(DraftableModelForm):
    """Section 03 row.

    `order` is deliberately absent: it is the row's position in the list,
    renumbered on every save, so asking the inspector to type it invites
    duplicates and gaps for no benefit. It is displayed as text.
    """

    widget_css = {"status": "form-select"}

    class Meta:
        model = CorrectiveMeasure
        fields = ["description", "responsible", "deadline", "status"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "deadline": date_input(),
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


class CorrectiveMeasureReportForm(DraftableModelForm):
    """Header, section 01 appreciation and section 03/04 of a follow-up."""

    never_required = (
        "global_appreciation_is_manual_override",
        "is_denunciation_escalation",
    )
    widget_css = {
        "global_appreciation": "form-check-input",
        "is_denunciation_escalation": "form-check-input",
        "final_closure_state": "form-select",
        "global_appreciation_is_manual_override": None,
    }

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
            "follow_up_date": date_input(),
            "next_control_date": date_input(),
            "signature_date": date_input(),
            "new_anomalies_description": forms.Textarea(attrs={"rows": 3}),
            "global_appreciation_is_manual_override": forms.HiddenInput(),
            "global_appreciation": forms.RadioSelect(),
        }
        labels = {
            # Plus explicite que le verbose_name du modèle, qui sert aussi
            # de titre de colonne dans l'admin.
            "is_denunciation_escalation": _(
                "Dernier contrôle avant dénonciation au Ministère public"
            ),
        }
        help_texts = {
            "next_control_date": _("Requis si une mesure reste ouverte."),
            "new_anomalies_description": _(
                "Laisser vide si aucune nouvelle anomalie n'a été constatée. "
                "Le texte ci-dessus est régénéré à l'enregistrement."
            ),
            "is_denunciation_escalation": _(
                "Décision de l'inspecteur, indépendante du nombre de mesures "
                "restantes. Possible dès la deuxième visite."
            ),
            "final_closure_state": _(
                "À renseigner lors de la visite finale qui suit une dénonciation."
            ),
        }


class MeasureFollowUpForm(DraftableModelForm):
    """Section 02 row: one measure of the initial report, re-checked."""

    widget_css = {"status": "form-select sc-followup-status"}

    class Meta:
        model = MeasureFollowUp
        fields = ["findings", "status", "responsible", "new_deadline"]
        widgets = {
            "findings": forms.Textarea(attrs={"rows": 2}),
            "new_deadline": date_input(),
        }

    def clean(self):
        cleaned = super().clean()
        if self.draft:
            return cleaned
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


class EmailRecordForm(BootstrapModelForm):
    """Subject, body and recipient, all editable before sending."""

    class Meta:
        model = EmailRecord
        fields = ["recipient_email", "subject", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 18})}
        help_texts = {
            "recipient_email": _(
                "Repris du maître d'ouvrage, modifiable avant l'envoi."
            ),
        }
