import json

from django import template

register = template.Library()


@register.filter
def jsonify(value):
    """ Serialize a dict/list to a JSON string.
    Intentionally not marked safe so it round-trips through an
    attribute value without breaking out of it. """
    return json.dumps(value)
