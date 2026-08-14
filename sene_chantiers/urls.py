from django.urls import path

from . import views

app_name = "sene_chantiers"

urlpatterns = [
    path("", views.home, name="home"),
    path("api/satac-lookup/", views.satac_lookup, name="satac_lookup"),
]
