import django_filters
from django import forms

from .models import DossierPPE, Zipfile

DERNIER_ZIP_STATUT_CHOICES = list(Zipfile.FileStatut.choices) + [("NONE", "Aucun")]


class DossierPPEFilter(django_filters.FilterSet):
    """ Colonnes filtrables de la liste des dossiers PPE (ppe:index).
    `dernier_zip_statut` s'appuie sur l'annotation posée par IndexView.get_queryset
    (statut du dernier zip soumis, trié par date de chargement), pas sur un simple
    "a un zip avec ce statut" qui inclurait les zips plus anciens. """

    cadastre = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Cadastre",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    nummai = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Bien-fonds",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    type_dossier = django_filters.ChoiceFilter(
        choices=DossierPPE.TypeDossier.choices,
        label="Type dossier",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    statut = django_filters.ChoiceFilter(
        choices=DossierPPE.DossierStatut.choices,
        label="Statut dossier",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    contact_principal__nom = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Contact principal",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    dernier_zip_statut = django_filters.ChoiceFilter(
        choices=DERNIER_ZIP_STATUT_CHOICES,
        label="Statut dernier zip",
        method="filter_dernier_zip_statut",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    login_code = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Code",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
    ordering = django_filters.OrderingFilter(
        fields=(
            ("id", "id"),
            ("cadastre", "cadastre"),
            ("nummai", "nummai"),
            ("date_creation", "date_creation"),
            ("type_dossier", "type_dossier"),
            ("statut", "statut"),
            ("contact_principal__nom", "contact_principal__nom"),
            ("dernier_zip_date", "dernier_zip_date"),
            ("dernier_zip_statut", "dernier_zip_statut"),
            ("aff_infolica", "aff_infolica"),
            ("login_code", "login_code"),
        ),
    )

    class Meta:
        model = DossierPPE
        fields = []

    def filter_dernier_zip_statut(self, queryset, name, value):
        if value == "NONE":
            return queryset.filter(dernier_zip_statut__isnull=True)
        return queryset.filter(dernier_zip_statut=value)
