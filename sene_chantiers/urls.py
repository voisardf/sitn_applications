from django.urls import path

from . import views

app_name = "sene_chantiers"

urlpatterns = [
    path("", views.home, name="home"),
    path("api/satac-lookup/", views.satac_lookup, name="satac_lookup"),
    # Also the entry point used by the geoportal result table.
    path(
        "chantier/<int:satac_number>/",
        views.chantier_landing,
        name="chantier_landing",
    ),
    path(
        "chantier/<int:satac_number>/nouveau/",
        views.chantier_create,
        name="chantier_create",
    ),
    path(
        "chantier/<int:satac_number>/rapport-controle/nouveau/",
        views.control_report_create,
        name="control_report_create",
    ),
    path(
        "chantier/<int:satac_number>/rapport-controle/",
        views.control_report_edit,
        name="control_report_edit",
    ),
]
