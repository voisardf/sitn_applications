from django.urls import path
from django.contrib import admin
from . import views

app_name = "sene_chantier"
urlpatterns = [    
    path("", views.IndexView.as_view(), name="index"),
    ]
