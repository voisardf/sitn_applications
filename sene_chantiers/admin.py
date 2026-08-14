"""Admin for the reference data only.

The reports themselves are edited through the application's own tabbed
views, not the admin: the section 01-04 layout, photo upload and cascade
calculations have no sensible admin equivalent.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    Chantier,
    ConstructionPhase,
    ControlPoint,
    Theme,
    WeatherCondition,
)


@admin.register(WeatherCondition)
class WeatherConditionAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("label",)


@admin.register(ConstructionPhase)
class ConstructionPhaseAdmin(admin.ModelAdmin):
    list_display = ("label", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("label",)


class ControlPointInline(admin.TabularInline):
    model = ControlPoint
    extra = 0


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "order")
    list_editable = ("order",)
    search_fields = ("label", "code")
    inlines = [ControlPointInline]


@admin.register(ControlPoint)
class ControlPointAdmin(admin.ModelAdmin):
    list_display = ("label", "theme", "order")
    list_editable = ("order",)
    list_filter = ("theme",)
    search_fields = ("label",)


@admin.register(Chantier)
class ChantierAdmin(SimpleHistoryAdmin):
    """Read-mostly: dossiers are created through the application."""

    list_display = ("satac_number", "site_name", "commune", "maitre_ouvrage",
                    "created_at")
    search_fields = ("satac_number", "site_name", "maitre_ouvrage",
                     "entreprise_generale")
    list_filter = ("created_at",)
