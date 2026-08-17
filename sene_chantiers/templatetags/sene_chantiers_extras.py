"""Template helpers for sene_chantiers."""

from django import template

register = template.Library()


@register.filter
def initials(user):
    """Two-letter avatar initials, falling back to the username."""
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first or last:
        return f"{first[:1]}{last[:1]}".upper()
    return (user.get_username() or "?")[:2].upper()


@register.filter
def display_name(user):
    """Full name when the SSO profile provides one, else the username."""
    return user.get_full_name() or user.get_username()


@register.filter
def coord_ch(value):
    """Swiss coordinate formatting: 2558956 -> 2'558'956.

    The apostrophe is the Swiss thousands separator; `intcomma` would
    give 2,558,956 and `floatformat` a space, neither of which is how
    coordinates are written here.
    """
    try:
        return f"{int(round(float(value))):,}".replace(",", "\u2019")
    except (TypeError, ValueError):
        return ""


@register.inclusion_tag("sene_chantiers/_situation_map.html")
def situation_map(geom, ratio="3-2", sticky=False, offset=False):
    """Render the situation map, or nothing at all without a geometry.

    Returning an empty context makes the partial render nothing, so a
    dossier with no localisation shows no empty map frame — the text
    simply takes the full width.
    """
    from ..maps import situation_map_config

    if geom is None:
        return {"geom": None}
    return {
        "geom": geom,
        "ratio": ratio,
        "sticky": sticky,
        "offset": offset,
        "config": situation_map_config(geom),
    }
