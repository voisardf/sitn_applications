from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SeneChantiersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sene_chantiers"
    verbose_name = _("Suivi environnemental de chantiers")
