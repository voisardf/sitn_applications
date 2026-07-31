from django.urls import path
from django.contrib import admin
from . import views

app_name = "ppe"
urlpatterns = [
    path("", views.index, name="index"),
    path("login", views.login, name="login"),
    path("login/<str:login_code>/", views.login, name="login_direct"),
    path("detail", views.detail, name="detail"),
    path("set_geolocalisation", views.set_geolocalisation, name="geolocalisation"),
    path("check_geolocalisation", views.check_geolocalisation, name="check_geolocalisation"),
    path("contact_principal", views.contact_principal, name="contact_principal"),
    path("modification", views.modification, name="modification"),
    path("edit_geolocalisation", views.edit_geolocalisation, name="edit_geolocalisation"),
    path("edit_contacts", views.edit_contacts, name="edit_contacts"),
    path("edit_ppe_type", views.edit_ppe_type, name="edit_ppe_type"),
    path("soumission", views.soumission, name="soumission"),
    path("define_ppe_type", views.define_ppe_type, name="define_ppe_type"),
    path("overview", views.overview, name="overview"),
    path("load_zipfile", views.load_zipfile, name="load_zipfile"),
    path("submit_for_validation", views.submit_for_validation, name="submit_for_validation"),
    path("admin_logout", views.admin_logout, name="admin_logout"),
    path("zip_status", views.zip_status, name="zip_status"),
    path("get_final_documents", views.get_final_documents, name="get_final_documents"),
]
