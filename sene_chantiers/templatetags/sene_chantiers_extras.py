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
