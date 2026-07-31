from django.contrib import admin
from django_extended_ol.admin import WMTSGISModelAdmin

from .models import PanoramaItem, Sequence


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    search_fields = ["id", "site", "version", "title"]
    list_display = ["id", "site", "version", "title", "item_count"]

    def item_count(self, obj):
        return obj.items.count()

    item_count.short_description = "Nb photos"


@admin.register(PanoramaItem)
class PanoramaItemAdmin(WMTSGISModelAdmin):
    search_fields = ["id", "image_name"]
    list_filter = ["sequence"]
    list_display = ["id", "sequence", "rank", "captured_at", "azimuth"]
    autocomplete_fields = ["sequence"]
