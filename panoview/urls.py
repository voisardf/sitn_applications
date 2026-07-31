from django.urls import path

from . import views

urlpatterns = [
    path("catalog.json", views.catalog_view, name="panoview-catalog"),
    path("catalog.json/configuration", views.configuration_view, name="panoview-configuration"),
    path("collections", views.collections_view, name="panoview-collections"),
    path("collections/<str:seq_id>/collection.json", views.collection_view, name="panoview-collection"),
    path("collections/<str:seq_id>", views.collection_view, name="panoview-collection-alias"),
    path("collections/<str:seq_id>/items/<str:item_id>", views.item_view, name="panoview-item"),
    path("search", views.search_view, name="panoview-search"),
    path("<str:item_id>", views.panorama_view, name="panoview-panorama"),
    path("", views.panoview_base_view, name="panoview-base"),
]
