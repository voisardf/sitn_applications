"""Access control for sene_chantiers.

Every view requires SSO authentication AND membership of the group named
by `settings.SENE_CHANTIERS_ADMIN_GROUP` (`sene_chantiers_gestion` by
default, settable per instance). The group is created manually by an
administrator; this module only checks for it, never creates it.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def user_is_sene_chantiers_admin(user):
    """True when the user may use the application at all."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=settings.SENE_CHANTIERS_ADMIN_GROUP).exists()


def sene_chantiers_admin_required(view_func):
    """Send anonymous users to SSO login; refuse authenticated non-members."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user_is_sene_chantiers_admin(request.user):
            raise PermissionDenied(
                "Accès réservé aux membres du groupe "
                f"{settings.SENE_CHANTIERS_ADMIN_GROUP}."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


class SeneChantiersAdminRequiredMixin:
    """Class-based-view equivalent of the decorator above."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user_is_sene_chantiers_admin(request.user):
            raise PermissionDenied(
                "Accès réservé aux membres du groupe "
                f"{settings.SENE_CHANTIERS_ADMIN_GROUP}."
            )
        return super().dispatch(request, *args, **kwargs)
