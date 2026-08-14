"""Forms for sene_chantiers."""

from django import forms
from django.utils.translation import gettext_lazy as _

from cadastre.models import Commune

from .models import Chantier


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
