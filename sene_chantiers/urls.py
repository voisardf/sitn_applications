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
    path(
        "chantier/<int:satac_number>/rapport-suivi/nouveau/",
        views.corrective_measure_report_create,
        name="corrective_measure_report_create",
    ),
    path(
        "rapport-suivi/<int:pk>/",
        views.corrective_measure_report_edit,
        name="corrective_measure_report_edit",
    ),
    path(
        "rapport/<str:kind>/<int:pk>/photos/",
        views.photo_upload,
        name="photo_upload",
    ),
    path(
        "rapport/<str:kind>/<int:pk>/photos/etat/",
        views.photo_status,
        name="photo_status",
    ),
    path(
        "rapport/<str:kind>/<int:pk>/courriel/",
        views.email_manager,
        name="email_manager",
    ),
    path(
        "rapport/<str:kind>/<int:pk>/pdf/",
        views.pdf_export,
        name="pdf_export",
    ),
    path(
        "chantier/<int:satac_number>/excel/",
        views.excel_export,
        name="excel_export",
    ),
    path("photos/<int:pk>/fichier/", views.photo_file, name="photo_file"),
    path("photos/<int:pk>/remarques/", views.photo_caption, name="photo_caption"),
    path("photos/<int:pk>/supprimer/", views.photo_delete, name="photo_delete"),
]
