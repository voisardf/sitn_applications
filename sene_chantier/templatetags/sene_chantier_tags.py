from django import template
from sene_chantier import VERSION

register = template.Library()


@register.simple_tag
def app_version():
    return VERSION
